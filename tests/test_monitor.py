import io
import os
import uuid
from datetime import UTC, datetime, timedelta

import numpy as np
import psycopg
import pytest
from prometheus_client import generate_latest
from psycopg.conninfo import make_conninfo
from rasterio.crs import CRS
from rasterio.enums import ColorInterp
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from landcover import models, monitor

T = datetime(2026, 11, 26, 12, 10, 20, tzinfo=UTC)


def write_tile(path, count=4, alpha=True):
    """A 512x512 RGB(+alpha) GeoTIFF; band 4 is 0 in the top-left pixel of each quadrant."""
    data = np.full((count, 512, 512), 100, dtype=np.uint8)
    data[0, :256, 256:] = 50  # q1 has a different red
    if count == 4:
        data[3, ::256, ::256] = 0
    profile = {"driver": "GTiff", "width": 512, "height": 512, "count": count, "dtype": "uint8",
               "crs": CRS.from_epsg(2154), "transform": from_origin(700000, 6600000, 0.2, 0.2)}
    with MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(data)
            if alpha:
                dst.colorinterp = [ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha]
        path.write_bytes(memfile.read())


def write_label(path):
    label = np.zeros((1, 512, 512), dtype=np.uint8)  # FLAIR building -> 7
    label[0, 256:, :] = 6  # water -> 5
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=512, height=512, count=1, dtype="uint8") as dst:
            dst.write(label)
        path.write_bytes(memfile.read())


def mask_tiff(mask):
    with MemoryFile() as memfile:
        with memfile.open(driver="GTiff", width=mask.shape[1], height=mask.shape[0], count=1,
                          dtype="uint8") as dst:
            dst.write(mask, 1)
        return memfile.read()


def npy(array):
    buffer = io.BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


# Windows and quadrants


def test_the_window_ends_at_the_start_time_rounded_down():
    assert monitor.window(T) == (T.replace(minute=5, second=0), T.replace(minute=10, second=0))
    boundary = T.replace(minute=5, second=0)
    assert monitor.containing(boundary)[0] == boundary
    assert monitor.containing(boundary - timedelta(seconds=1))[1] == boundary


def test_quadrants_keep_the_grid_and_the_valid_pixels(tmp_path):
    import rasterio

    write_tile(tmp_path / "t.tif")
    parts = list(monitor.quadrants(tmp_path / "t.tif"))
    assert [q for q, _ in parts] == [0, 1, 2, 3]
    with MemoryFile(parts[1][1]) as memfile, memfile.open() as src:
        assert (src.width, src.height, src.count) == (256, 256, 4)
        assert src.transform == from_origin(700000 + 256 * 0.2, 6600000, 0.2, 0.2)
        assert src.read(1).max() == 50
        valid = (src.read_masks([1, 2, 3]) > 0).all(axis=0)
        assert not valid[0, 0] and valid.sum() == 256 * 256 - 1
    with rasterio.open(tmp_path / "t.tif") as src:
        assert src.read_masks(1)[256, 0] == 0  # q2's first pixel is invalid in the source too


def test_label_quadrants_are_crosswalked(tmp_path):
    write_label(tmp_path / "l.tif")
    parts = dict(monitor.label_quadrants(tmp_path / "l.tif"))
    assert set(np.unique(parts[0])) == {7} and set(np.unique(parts[3])) == {5}


def test_source_ids():
    assert monitor.source_id("replay", "D017-2021", "AA-1", 3) == "replay/D017-2021/AA-1/q3"
    assert monitor.source_id("reference", "D080-2017", "B", 0, "abc") == "reference/abc/D080-2017/B/q0"


def test_darkening_scales_the_colour_bands_and_keeps_validity(tmp_path):
    write_tile(tmp_path / "t.tif")
    _, body = list(monitor.quadrants(tmp_path / "t.tif"))[1]
    with MemoryFile(body) as a, a.open() as before, MemoryFile(monitor.darken(body, 0.5)) as b, b.open() as after:
        original, dark = before.read(), after.read()
        assert (dark[:3] == np.rint(0.5 * original[:3].astype(float))).all()
        assert (dark[3] == original[3]).all() and dark[0].max() == 25
        assert (after.read_masks() == before.read_masks()).all() and after.colorinterp == before.colorinterp


def test_the_same_seed_darkens_the_same_quadrants():
    chosen = monitor.shifted(128, 0.5, 0)
    assert len(chosen) == 64 and chosen == monitor.shifted(128, 0.5, 0) != monitor.shifted(128, 0.5, 1)


def test_darkened_quadrants_carry_shift_ids(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    write_tile(tmp_path / "images" / "AA-1.tif")
    monkeypatch.setattr(monitor, "batch_dir", lambda batch: tmp_path)
    plain = monitor.replay_items(["D017-2021"])
    items = monitor.replay_items(["D017-2021"], factor=0.5, fraction=0.5, seed=0)
    chosen = monitor.shifted(4, 0.5, 0)
    assert [s for s, _ in items] == [("shift" if q in chosen else "replay") + f"/D017-2021/AA-1/q{q}" for q in range(4)]
    assert [body == original for (_, body), (_, original) in zip(items, plain)] == [q not in chosen for q in range(4)]


def test_columns_are_the_inputs_and_the_scored_class_shares():
    assert monitor.COLUMNS == ["mean_r", "mean_g", "mean_b", "brightness", "share_bareland", "share_rangeland",
                               "share_tree", "share_water", "share_agriculture", "share_building"]


# Report pieces


def test_insufficient_data_reasons():
    assert monitor.insufficient(128, 0) == "no_reference"
    assert monitor.insufficient(0, 256) == "few_observations"
    assert monitor.insufficient(49, 256) == "few_observations"
    assert monitor.insufficient(50, 256) is None


def test_quality_equals_the_lab_2_scores(monkeypatch):
    monkeypatch.setattr(monitor, "MIN_OBSERVATIONS", 2)
    label = np.repeat(np.array(models.SCORED, dtype=np.uint8), 4)[None, :].repeat(3, axis=0)
    label[0, 0] = 255
    prediction = label.copy()
    prediction[1, :4] = 1  # bareland predicted as rangeland in one row
    pairs = [(npy(label), mask_tiff(prediction)), (npy(label), mask_tiff(label))]
    matrix = models.confusion(label, prediction) + models.confusion(label, label)
    expected = models.scores(matrix, 2, 2 * label.size)["miou"]
    assert monitor.quality(pairs) == (pytest.approx(expected), None)


def test_quality_without_a_scored_class_is_insufficient(monkeypatch):
    monkeypatch.setattr(monitor, "MIN_OBSERVATIONS", 1)
    label = np.zeros((4, 4), dtype=np.uint8)
    assert monitor.quality([(npy(label), mask_tiff(label))]) == (None, "incomplete_labels")
    assert monitor.quality([]) == (None, "few_observations")


def test_the_parser_reads_distances_and_the_count():
    metrics = [{"config": {"type": "evidently:metric_v2:ValueDrift", "column": c}, "value": 0.1}
               for c in monitor.COLUMNS]
    metrics.append({"config": {"type": "evidently:metric_v2:DriftedColumnsCount"},
                    "value": {"count": 1.0, "share": 0.1}})
    parsed = monitor.parse({"metrics": metrics})
    assert parsed["drifted"] == 1 and parsed["share"] == 0.1 and len(parsed["distances"]) == 10
    with pytest.raises(ValueError):
        monitor.parse({"metrics": metrics[1:]})


def test_the_registry_holds_the_report_and_nothing_else():
    results = {
        "3": {"observations": {"current": 128, "reference": 256, "labelled": 64},
              "drift": {"distances": dict.fromkeys(monitor.COLUMNS, 0.2), "drifted": 0, "share": 0.0},
              "quality": {"miou": 0.31}},
        "4": {"observations": {"current": 0, "reference": 0, "labelled": 0},
              "drift": {"insufficient": "no_reference"}, "quality": {"insufficient": "few_observations"}},
    }
    end = T.replace(minute=10, second=0)
    text = generate_latest(monitor.to_registry(results, end, T)).decode()
    assert 'landcover_drift_distance{column="brightness",model_version="3"} 0.2' in text
    assert 'landcover_quality_miou{model_version="3"} 0.31' in text
    assert 'landcover_report_observations{model_version="3",side="labelled"} 64.0' in text
    assert 'landcover_report_insufficient{model_version="4",reason="no_reference",signal="drift"} 1.0' in text
    registry = monitor.to_registry(results, end, T)
    assert registry.get_sample_value("landcover_report_window_end_seconds") == end.timestamp()
    assert registry.get_sample_value("landcover_latest_request_seconds") == T.timestamp()
    assert "landcover_drift_threshold 0.5" in text
    assert 'model_version="4"' not in "".join(line for line in text.splitlines() if "distance" in line)
    empty = generate_latest(monitor.to_registry({}, end, None)).decode()
    assert "landcover_latest_request_seconds" not in empty and "model_version" not in empty


# Evidently (group monitor)


def test_evidently_distances():
    pytest.importorskip("evidently")
    rng = np.random.default_rng(0)
    reference = rng.normal(100, 10, size=(256, len(monitor.COLUMNS)))
    same = monitor.drift(reference, reference)
    assert same["drifted"] == 0 and max(same["distances"].values()) == 0
    shifted = reference[:128].copy()
    shifted[:, monitor.COLUMNS.index("brightness")] -= 20  # two reference standard deviations
    result = monitor.drift(shifted, reference)
    assert result["distances"]["brightness"] > 0.5 and result["drifted"] == 1


# Database (TEST_DSN)


@pytest.fixture
def dsn():
    server = os.environ.get("TEST_DSN")
    if not server:
        pytest.skip("TEST_DSN is not set")
    name = f"monitor_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {name}")
    dsn = make_conninfo(server, dbname=name)
    with psycopg.connect(dsn) as conn:
        conn.execute(monitor.SCHEMA.read_text())
    yield dsn
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE {name} WITH (FORCE)")


def log(conn, version, at, source=None):
    conn.execute("INSERT INTO serving.predictions (request_id, received_at, model_name, model_version,"
                 " image_commit, outcome, source_id) VALUES (%s, %s, 'm', %s, 'c', 'ok', %s)",
                 [uuid.uuid4(), at, version, source])


def test_versions_of_the_window_and_the_latest_request(dsn):
    start, end = monitor.window(T)
    with psycopg.connect(dsn) as conn:
        log(conn, "2", start - timedelta(minutes=1))
        log(conn, "3", start + timedelta(seconds=1), "replay/D017-2021/a/q0")
        log(conn, "4", start + timedelta(seconds=2), "reference/x/D080-2017/a/q0")
        assert monitor.versions(conn, start, end) == (["3"], start + timedelta(seconds=1))
        later_start, later_end = monitor.window(T + timedelta(minutes=10))
        assert monitor.versions(conn, later_start, later_end) == (["3"], start + timedelta(seconds=1))


def test_labels_twice_give_one_row_per_quadrant(dsn, tmp_path, monkeypatch):
    for kind in ("images", "labels"):
        (tmp_path / kind).mkdir()
    write_tile(tmp_path / "images" / "AA-1.tif")
    write_label(tmp_path / "labels" / "AA-1.tif")
    monkeypatch.setattr(monitor, "batch_dir", lambda batch: tmp_path)
    monitor.labels(dsn)
    monitor.labels(dsn)
    with psycopg.connect(dsn) as conn:
        rows = conn.execute("SELECT source_id, mask FROM serving.labels ORDER BY source_id").fetchall()
    assert [r[0] for r in rows] == [f"replay/D017-2021/AA-1/q{q}" for q in range(4)]
    assert np.load(io.BytesIO(rows[3][1])).shape == (256, 256)

import os
import re

import fetch_sample
import numpy as np
import psycopg
import pytest
import rasterio
from psycopg.conninfo import make_conninfo

from landcover import pipeline


def write_tif(path, array):
    path.parent.mkdir(parents=True, exist_ok=True)
    bands, height, width = array.shape
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height, count=bands, dtype=array.dtype
    ) as dst:
        dst.write(array)


def write_pair(directory, tile_id, label, image=None):
    if image is None:
        image = np.full((4, *label.shape), 100, dtype=np.uint8)
    write_tif(directory / "images" / f"{tile_id}.tif", image)
    write_tif(directory / "labels" / f"{tile_id}.tif", label[np.newaxis].astype(np.uint8))


def test_year_selects_its_batch():
    assert pipeline.resolve_batch(None, 2019) == "D065-2019"


def test_parameter_overrides_year():
    assert pipeline.resolve_batch("bad-demo", 2019) == "bad-demo"


def test_unknown_year_is_named():
    with pytest.raises(ValueError, match="2016"):
        pipeline.resolve_batch(None, 2016)


def test_unknown_batch_is_named():
    with pytest.raises(ValueError, match="D999-2030"):
        pipeline.resolve_batch("D999-2030", 2019)


def test_empty_batch_parameter_is_rejected():
    with pytest.raises(ValueError, match="unknown batch ''"):
        pipeline.resolve_batch("", 2019)


def test_fetched_domains_are_the_registered_batches():
    assert fetch_sample.DOMAINS == list(pipeline.BATCHES)


def test_empty_batch_fails(tmp_path):
    with pytest.raises(ValueError, match="no files"):
        pipeline.extract(tmp_path)


def test_grid_mismatch_names_the_pair(tmp_path):
    write_pair(tmp_path, "ok", np.zeros((8, 8)))
    write_pair(tmp_path, "bad", np.zeros((8, 6)), image=np.zeros((4, 8, 8), dtype=np.uint8))
    with pytest.raises(ValueError, match="bad.tif.*grid sizes differ") as error:
        pipeline.validate(tmp_path, pipeline.extract(tmp_path))
    assert "ok.tif" not in str(error.value)


def test_unknown_class_names_the_label(tmp_path):
    write_pair(tmp_path, "t1", np.full((8, 8), 19))
    with pytest.raises(ValueError, match=r"labels/t1.tif: unknown class IDs \[19\]"):
        pipeline.validate(tmp_path, ["t1"])


def test_unpaired_file_is_named(tmp_path):
    write_tif(tmp_path / "images" / "lonely.tif", np.zeros((3, 8, 8), dtype=np.uint8))
    with pytest.raises(ValueError, match="lonely.tif: no label"):
        pipeline.validate(tmp_path, pipeline.extract(tmp_path))


def test_truncated_band_names_the_image(tmp_path):
    write_pair(tmp_path, "t1", np.zeros((64, 64)))
    image = tmp_path / "images" / "t1.tif"
    with rasterio.open(
        image, "w", driver="GTiff", width=64, height=64, count=4, dtype="uint8", interleave="band"
    ) as dst:
        dst.write(np.full((4, 64, 64), 100, dtype=np.uint8))
    image.write_bytes(image.read_bytes()[:-2000])  # cuts into the fourth band only
    with rasterio.open(image) as src:
        src.read([1, 2, 3])
    with pytest.raises(ValueError, match="images/t1.tif.*unreadable"):
        pipeline.validate(tmp_path, ["t1"])


def test_crosswalk_per_source_class():
    # Section 5.2 table restated per FLAIR-HUB ID 0-18, independently of pipeline.CROSSWALK.
    expected = [7, 255, 5, 255, 255, 0, 5, 255, 1, 6, 255, 6, 4, 4, 255, 255, 255, 255, 255]
    assert pipeline.LUT[:19].tolist() == expected


def test_counts_after_crosswalk(tmp_path):
    # One pixel of each FLAIR-HUB class 0-18, plus a second building pixel.
    label = np.array(list(range(19)) + [0]).reshape(4, 5)
    image = np.stack([np.full((4, 5), v, dtype=np.uint8) for v in (10, 20, 30, 40)])
    write_pair(tmp_path, "t1", label, image)
    pipeline.validate(tmp_path, ["t1"])
    [row] = pipeline.transform(tmp_path, ["t1"])
    # internal 0 bare <- 5; 1 herbaceous <- 8; 4 tree <- 12, 13; 5 water <- 2, 6;
    # 6 agriculture <- 9, 11; 7 building <- 0 (twice); road and developed space get none.
    assert row["class_px"] == [1, 1, 0, 0, 2, 2, 2, 2]
    assert row["ignored_px"] == 10
    assert (row["width"], row["height"]) == (5, 4)
    assert row["channel_mean"] == [10.0, 20.0, 30.0]


def test_gate_passes_at_the_maximum():
    assert pipeline.check_ignored_share(90, 100) == 0.9


def test_gate_fails_above_the_maximum():
    with pytest.raises(ValueError, match="1.00 exceeds the maximum 0.90"):
        pipeline.check_ignored_share(100, 100)


def test_gate_message_shows_a_small_excess():
    with pytest.raises(ValueError, match=r"0.90 exceeds the maximum 0.90 \(901 of 1000 pixels\)"):
        pipeline.check_ignored_share(901, 1000)


@pytest.fixture
def dsn():
    """A fresh database landcover_test on the server TEST_DSN names; CI provides one."""
    server = os.environ.get("TEST_DSN")
    if not server:
        pytest.skip("TEST_DSN is not set")
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute("DROP DATABASE IF EXISTS landcover_test")
        conn.execute("CREATE DATABASE landcover_test")
    dsn = make_conninfo(server, dbname="landcover_test")
    schema = (pipeline.ROOT / "sql" / "warehouse.sql").read_text()
    with psycopg.connect(dsn) as conn:
        conn.execute(re.sub(r"(?im)^[ \t]*CREATE[ \t]+DATABASE\b[^;]*;", "", schema))
    return dsn


def tile_rows(ignored_px):
    """Two 10x10 tiles; the pixels that are not ignored are internal class 0."""
    return [
        {
            "tile_id": tile_id,
            "width": 10,
            "height": 10,
            "class_px": [100 - ignored_px, 0, 0, 0, 0, 0, 0, 0],
            "ignored_px": ignored_px,
            "channel_mean": [51.0, 102.0, 153.0],
        }
        for tile_id in ("t1", "t2")
    ]


def run(dsn, batch_id, rows):
    pipeline.load(dsn, batch_id, rows)
    pipeline.build_features(dsn, batch_id)
    return pipeline.quality_check(dsn, batch_id)


def snapshot(dsn):
    with psycopg.connect(dsn) as conn:
        return [
            conn.execute(f"SELECT * FROM {table} ORDER BY batch_id, tile_id").fetchall()
            for table in ("dwh.tiles", "features.tile_features")
        ]


def test_warehouse_rerun_and_refused_batch(dsn):
    run(dsn, "D065-2019", tile_rows(ignored_px=20))
    run(dsn, "D045-2020", tile_rows(ignored_px=40))
    before = snapshot(dsn)
    tiles, features = before
    assert [row[:3] for row in tiles] == [
        ("D045-2020", "t1", 2020), ("D045-2020", "t2", 2020),
        ("D065-2019", "t1", 2019), ("D065-2019", "t2", 2019),
    ]
    batch_id, tile_id, version, class_share, ignored_share, channel_mean = features[0]
    assert (batch_id, tile_id, version) == ("D045-2020", "t1", pipeline.FEATURE_VERSION)
    assert class_share == pytest.approx([0.6, 0, 0, 0, 0, 0, 0, 0])
    assert ignored_share == pytest.approx(0.4)
    assert channel_mean == pytest.approx([0.2, 0.4, 0.6])

    run(dsn, "D065-2019", tile_rows(ignored_px=20))
    assert snapshot(dsn) == before  # the rerun replaced its rows; the other batch is untouched

    with pytest.raises(ValueError, match="exceeds the maximum"):
        run(dsn, pipeline.DEMO_BATCH, tile_rows(ignored_px=100))
    assert snapshot(dsn) == before  # the refused batch left no rows

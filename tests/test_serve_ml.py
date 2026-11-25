import base64
import os
import time
import uuid

import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from landcover import serve_ml

TRANSFORM = from_origin(700000, 6600000, 0.2, 0.2)


def image(driver="GTiff", dtype="uint8", count=3, georeferenced=True, nodata=None, width=8, height=6):
    """An image whose valid pixels are R 10, G 20, B 30; pixel (0, 0) is 0 in every band."""
    data = np.zeros((count, height, width), dtype=dtype)
    data[:3] = np.array([10, 20, 30])[:count, None, None]
    data[:, 0, 0] = 0
    profile = {"driver": driver, "width": width, "height": height, "count": count, "dtype": dtype}
    if georeferenced:
        profile.update(crs=CRS.from_epsg(2154), transform=TRANSFORM)
    if nodata is not None:
        profile["nodata"] = nodata
    with MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(data)
        return memfile.read()


def tree(rgb):
    return np.full(rgb.shape[:2], 4, dtype=np.uint8)


def wait_loaded():
    for _ in range(200):
        if serve_ml.state["predict"] is not None:
            return
        time.sleep(0.01)
    raise AssertionError("the model was not loaded")


@pytest.fixture
def rows(monkeypatch):
    """Rows written to the log; the registry and the database are replaced by fakes."""
    written = []
    monkeypatch.setattr(serve_ml, "prepare_log", lambda: None)
    monkeypatch.setattr(serve_ml, "check_log", lambda: None)
    monkeypatch.setattr(serve_ml, "write_row", lambda row: written.append(dict(row)))
    monkeypatch.setattr(serve_ml, "load_model", lambda: ("7", tree))
    return written


@pytest.fixture
def client(rows):
    with TestClient(serve_ml.app) as c:
        wait_loaded()
        yield c


def decode_mask(response):
    with MemoryFile(base64.b64decode(response.json()["mask"])) as memfile, memfile.open() as src:
        return src.read(1), src.crs, src.transform, src.nodata


def test_observe_ignores_invalid_pixels():
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[..., 0], rgb[..., 1], rgb[..., 2] = 10, 20, 30
    rgb[0, 0] = 255
    valid = np.array([[False, True], [True, True]])
    mask = np.array([[255, 4], [4, 6]], dtype=np.uint8)
    features, shares = serve_ml.observe(rgb, valid, mask)
    assert features == {"mean_r": 10.0, "mean_g": 20.0, "mean_b": 30.0, "brightness": 20.0}
    assert shares["tree"] == pytest.approx(2 / 3) and shares["agriculture"] == pytest.approx(1 / 3)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_a_geotiff_gets_a_mask_on_its_grid_and_one_log_row(client, rows):
    response = client.post("/predict", content=image(nodata=0), headers={"X-Source-Id": "D017-2021/t/q0"})
    assert response.status_code == 200
    body = response.json()
    assert (body["model_name"], body["model_version"]) == ("landcover-segmenter", "7")
    assert (body["width"], body["height"], body["valid_px"]) == (8, 6, 47)
    assert body["features"] == {"mean_r": 10.0, "mean_g": 20.0, "mean_b": 30.0, "brightness": 20.0}
    assert body["class_shares"]["tree"] == 1.0
    mask, crs, transform, nodata = decode_mask(response)
    assert mask.shape == (6, 8) and mask[0, 0] == 255 and (mask.ravel()[1:] == 4).all()
    assert crs == CRS.from_epsg(2154) and transform == TRANSFORM and nodata == 255
    [row] = rows
    assert str(row["request_id"]) == body["request_id"]
    assert (row["outcome"], row["source_id"], row["model_version"]) == ("ok", "D017-2021/t/q0", "7")
    assert row["brightness"] == 20.0 and row["share_tree"] == 1.0 and row["dark_warning"] is None


def test_a_png_gets_a_mask_without_coordinates(client):
    response = client.post("/predict", content=image(driver="PNG", georeferenced=False))
    assert response.status_code == 200
    mask, crs, _, _ = decode_mask(response)
    assert mask.shape == (6, 8) and crs is None


@pytest.mark.parametrize("content, reason", [
    (b"not an image", "cannot decode"),
    (image(dtype="uint16"), "not 8-bit"),
    (image(count=1), "not 8-bit"),
])
def test_unusable_input_is_refused_and_logged_without_features(client, rows, content, reason):
    response = client.post("/predict", content=content)
    assert response.status_code == 400 and reason in response.json()["detail"]
    [row] = rows
    assert row["outcome"] == "invalid" and reason in row["reason"] and "brightness" not in row


def test_an_image_without_valid_pixels_is_refused(client):
    response = client.post("/predict", content=image(nodata=0, width=1, height=1))
    assert response.status_code == 400 and "no valid pixel" in response.json()["detail"]


def test_limits_refuse_before_the_model_runs(client, rows, monkeypatch):
    def fail(rgb):
        raise AssertionError("the model ran")

    monkeypatch.setitem(serve_ml.state, "predict", fail)
    monkeypatch.setattr(serve_ml, "MAX_PIXELS", 47)
    response = client.post("/predict", content=image())
    assert response.status_code == 413 and "8x6 exceeds the limit of 47 pixels" in response.json()["detail"]
    monkeypatch.setattr(serve_ml, "MAX_BYTES", 10)
    response = client.post("/predict", content=image())
    assert response.status_code == 413 and "exceeds 10 bytes" in response.json()["detail"]
    assert [r["outcome"] for r in rows] == ["invalid", "invalid"]


def test_a_dark_image_is_served_with_a_warning(client, monkeypatch):
    monkeypatch.setattr(serve_ml, "DARK_BRIGHTNESS", 63.0)
    response = client.post("/predict", content=image())
    assert response.status_code == 200 and response.json()["dark_warning"] is True


def test_a_failed_log_write_fails_the_request(client, monkeypatch):
    def broken(row):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(serve_ml, "write_row", broken)
    response = client.post("/predict", content=image())
    assert response.status_code == 500 and "request log is unavailable" in response.json()["detail"]
    assert "mask" not in response.json()


def test_not_ready_until_the_model_appears(rows, monkeypatch):
    present = False

    def load():
        if not present:
            raise LookupError("Registered model alias missing not found.")
        return "1", tree

    monkeypatch.setattr(serve_ml, "load_model", load)
    monkeypatch.setattr(serve_ml, "LOAD_RETRY_SECONDS", 0.01)
    with TestClient(serve_ml.app) as c:
        time.sleep(0.05)
        assert c.get("/health/live").status_code == 200
        response = c.get("/health/ready")
        assert response.status_code == 503 and "alias missing not found" in response.json()["reason"]
        assert c.post("/predict", content=image()).status_code == 503
        assert rows == []
        present = True
        wait_loaded()
        response = c.get("/health/ready")
        assert response.status_code == 200 and response.json()["model_version"] == "1"
        assert c.post("/predict", content=image()).json()["model_version"] == "1"


def test_not_ready_while_the_log_is_unreachable(client, monkeypatch):
    def broken():
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(serve_ml, "check_log", broken)
    response = client.get("/health/ready")
    assert response.status_code == 503 and "request log is unreachable" in response.json()["reason"]


def sample(outcome):
    labels = {"endpoint": "/predict", "outcome": outcome, "model_version": "7"}
    return serve_ml.registry.get_sample_value("landcover_requests_total", labels) or 0.0


def test_metrics_count_requests_by_outcome_and_skip_health(client):
    before = {o: sample(o) for o in ("ok", "invalid")}
    latency = serve_ml.registry.get_sample_value("landcover_request_seconds_count", {"endpoint": "/predict"}) or 0.0
    client.post("/predict", content=image())
    client.post("/predict", content=image())
    client.post("/predict", content=b"not an image")
    client.get("/health/ready")
    text = client.get("/metrics").text
    assert sample("ok") - before["ok"] == 2 and sample("invalid") - before["invalid"] == 1
    assert serve_ml.registry.get_sample_value("landcover_request_seconds_count", {"endpoint": "/predict"}) - latency == 3
    assert "landcover_model_loaded 1.0" in text and 'endpoint="/health' not in text


@pytest.fixture
def log_dsn(monkeypatch):
    """A fresh database on the server TEST_DSN names, set as WAREHOUSE_DSN; dropped after."""
    server = os.environ.get("TEST_DSN")
    if not server:
        pytest.skip("TEST_DSN is not set")
    name = f"serving_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {name}")
    dsn = make_conninfo(server, dbname=name)
    monkeypatch.setenv("WAREHOUSE_DSN", dsn)
    yield dsn
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE {name} WITH (FORCE)")


def test_a_served_request_is_one_row_in_the_database(log_dsn, monkeypatch):
    serve_ml.prepare_log()  # the schema applies twice: once here, once at start-up
    monkeypatch.setattr(serve_ml, "load_model", lambda: ("7", tree))
    with TestClient(serve_ml.app) as c:
        wait_loaded()
        body = c.post("/predict", content=image(nodata=0), headers={"X-Source-Id": "s1"}).json()
        assert c.get("/health/ready").status_code == 200
    with psycopg.connect(log_dsn) as conn:
        rows = conn.execute("SELECT request_id, outcome, source_id, valid_px, brightness, share_tree,"
                            " length(mask) > 0 FROM serving.predictions").fetchall()
    assert rows == [(uuid.UUID(body["request_id"]), "ok", "s1", 47, 20.0, 1.0, True)]


def test_a_broken_database_fails_requests_and_readiness(log_dsn, monkeypatch):
    monkeypatch.setattr(serve_ml, "load_model", lambda: ("7", tree))
    with TestClient(serve_ml.app) as c:
        wait_loaded()
        monkeypatch.setenv("WAREHOUSE_DSN", make_conninfo(log_dsn, dbname="no_such_database"))
        assert c.get("/health/ready").status_code == 503
        assert c.post("/predict", content=image()).status_code == 500

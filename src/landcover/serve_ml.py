"""Lab 4 ML service: POST /predict segments one image with the registry version the alias names.

    uvicorn landcover.serve_ml:app --host 0.0.0.0 --port 8000

Configuration comes from the environment (README, "Lab 4: services"). The alias is resolved to a version
number once; a background thread retries until that version is loaded, and the service is not ready before.
Every served request is written to serving.predictions (sql/serving.sql) before the response.
"""

import base64
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import numpy as np
import psycopg
import rasterio
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    ProcessCollector,
    generate_latest,
)
from rasterio.io import MemoryFile

from landcover.models import CLASS_NAMES
from landcover.pipeline import IGNORE, ROOT

MODEL_NAME = os.environ.get("MODEL_NAME", "landcover-segmenter")
MODEL_ALIAS = os.environ.get("MODEL_ALIAS", "champion")
IMAGE_COMMIT = os.environ.get("IMAGE_COMMIT", "unknown")
DARK_BRIGHTNESS = float(os.environ["DARK_BRIGHTNESS"]) if os.environ.get("DARK_BRIGHTNESS") else None
MAX_PIXELS = int(os.environ.get("MAX_PIXELS", "1048576"))  # 1024 x 1024
MAX_BYTES = int(os.environ.get("MAX_BYTES", "16777216"))  # 16 MiB
LOAD_RETRY_SECONDS = float(os.environ.get("LOAD_RETRY_SECONDS", "10"))
SCHEMA = ROOT / "sql" / "serving.sql"

registry = CollectorRegistry()  # per service: both services share metric names
ProcessCollector(registry=registry)
REQUESTS = Counter("landcover_requests", "Requests by endpoint and outcome",
                   ["endpoint", "outcome", "model_version"], registry=registry)
LATENCY = Histogram("landcover_request_seconds", "Request latency", ["endpoint"],
                    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10), registry=registry)
MODEL_LOADED = Gauge("landcover_model_loaded", "1 once the model is loaded", registry=registry)

state = {"predict": None, "version": None, "reason": "loading"}
# ponytail: one lock serialises prediction and logging per process, the one-worker design of
# docs/design.md 6.3; scale with replicas.
LOCK = threading.Lock()


class Invalid(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status, self.reason = status, reason


# The image


def decode(body):
    """(rgb height x width x 3 uint8, valid pixels, crs, transform) of an upload; Invalid when unusable."""
    try:
        with MemoryFile(body) as memfile, memfile.open() as src:
            if src.count < 3 or any(dtype != "uint8" for dtype in src.dtypes):
                raise Invalid(400, f"not 8-bit with at least three bands ({src.count} bands, {src.dtypes[0]})")
            if src.width * src.height > MAX_PIXELS:
                raise Invalid(413, f"{src.width}x{src.height} exceeds the limit of {MAX_PIXELS} pixels")
            rgb = src.read([1, 2, 3]).transpose(1, 2, 0)
            valid = (src.read_masks([1, 2, 3]) > 0).all(axis=0)
            crs, transform = src.crs, src.transform
    except rasterio.errors.RasterioError as err:
        raise Invalid(400, f"cannot decode the image: {err}") from None
    if not valid.any():
        raise Invalid(400, "the image has no valid pixel")
    return rgb, valid, crs, transform


def observe(rgb, valid, mask):
    """docs/design.md 6.6 per image: RGB means and brightness over valid pixels (0-255), class shares of them."""
    means = rgb[valid].astype(np.float64).mean(axis=0)
    counts = np.bincount(mask[valid], minlength=256)[: len(CLASS_NAMES)]
    features = {"mean_r": float(means[0]), "mean_g": float(means[1]), "mean_b": float(means[2]),
                "brightness": float(means.mean())}
    shares = {name: float(counts[i] / valid.sum()) for i, name in enumerate(CLASS_NAMES)}
    return features, shares


def encode_mask(mask, crs, transform):
    """Single-band GeoTIFF of class IDs, 255 as nodata; georeferenced only when the input was."""
    profile = {"driver": "GTiff", "width": mask.shape[1], "height": mask.shape[0], "count": 1,
               "dtype": "uint8", "nodata": IGNORE, "compress": "deflate"}
    if crs:
        profile.update(crs=crs, transform=transform)
    with MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(mask, 1)
        return memfile.read()


# The model and the request log


def load_model():
    """(version, predict) of the version the alias names now; the image's landcover code runs it."""
    import mlflow.pyfunc
    from mlflow import MlflowClient

    version = MlflowClient().get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS).version
    return version, mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{version}").predict


def connect():
    return psycopg.connect(os.environ["WAREHOUSE_DSN"], connect_timeout=3)


def prepare_log():
    with connect() as conn:
        conn.execute(SCHEMA.read_text())


def check_log():
    with connect() as conn:
        conn.execute("SELECT 1 FROM serving.predictions LIMIT 0")


def write_row(row):
    columns = ", ".join(row)  # keys are fixed in this module
    with connect() as conn:
        conn.execute(f"INSERT INTO serving.predictions ({columns}) VALUES ({', '.join(['%s'] * len(row))})",
                     list(row.values()))


def keep_loading():
    """Create the log schema and load the model, retrying until both succeed; the version then stays fixed."""
    while True:
        try:
            prepare_log()
            version, predict = load_model()
            break
        # Registry, database, pickle or model errors of any type: report and retry, never end the thread.
        except Exception as err:  # noqa: BLE001
            state["reason"] = f"{MODEL_NAME}@{MODEL_ALIAS} not loaded: {type(err).__name__}: {err}"
            print(f"{state['reason']}; retrying in {LOAD_RETRY_SECONDS:g} s", file=sys.stderr, flush=True)
            time.sleep(LOAD_RETRY_SECONDS)
    state.update(predict=predict, version=str(version), reason=None)
    MODEL_LOADED.set(1)
    print(f"loaded {MODEL_NAME} version {version} ({MODEL_NAME}@{MODEL_ALIAS}), image {IMAGE_COMMIT}",
          file=sys.stderr, flush=True)


# Serving


def serve(row, body):
    """Predict, write the log row and return (status, content); a failed write fails the request."""
    with LOCK:
        try:
            try:
                if body is None:
                    raise Invalid(413, f"the request body exceeds {MAX_BYTES} bytes")
                rgb, valid, crs, transform = decode(body)
                mask = np.asarray(state["predict"](rgb), dtype=np.uint8).copy()
                if mask.shape != valid.shape:
                    raise ValueError(f"the model returned a {mask.shape} mask for a {valid.shape} image")
                mask[~valid] = IGNORE
                features, shares = observe(rgb, valid, mask)
                dark = None if DARK_BRIGHTNESS is None else features["brightness"] < DARK_BRIGHTNESS
                encoded = encode_mask(mask, crs, transform)
                row.update(outcome="ok", width=mask.shape[1], height=mask.shape[0], valid_px=int(valid.sum()),
                           **features, **{f"share_{name}": share for name, share in shares.items()},
                           dark_warning=dark, mask=encoded)
                status, content = 200, {
                    "model_name": row["model_name"], "model_version": row["model_version"],
                    "image_commit": row["image_commit"], "width": row["width"], "height": row["height"],
                    "valid_px": row["valid_px"], "features": features, "class_shares": shares,
                    "dark_warning": dark, "mask": base64.b64encode(encoded).decode()}
            except Invalid as err:
                row.update(outcome="invalid", reason=err.reason)
                status, content = err.status, {"detail": err.reason}
            except Exception as err:  # noqa: BLE001  any model failure is logged as an error row
                row.update(outcome="error", reason=f"prediction failed: {type(err).__name__}: {err}")
                status, content = 500, {"detail": row["reason"]}
            write_row(row)
        except (psycopg.Error, KeyError) as err:  # KeyError: WAREHOUSE_DSN is not set
            row["outcome"] = "error"
            status, content = 500, {"detail": f"the request log is unavailable: {type(err).__name__}: {err}"}
    return status, {"request_id": str(row["request_id"]), **content}


async def read_body(request):
    """The body, or None once it exceeds MAX_BYTES."""
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BYTES:
            return None
    return bytes(body)


@asynccontextmanager
async def lifespan(app):
    state.update(predict=None, version=None, reason="loading")
    MODEL_LOADED.set(0)
    threading.Thread(target=keep_loading, daemon=True).start()
    yield


app = FastAPI(title="landcover-ml", lifespan=lifespan)


@app.post("/predict")
async def predict(request: Request):
    start = time.perf_counter()
    if state["predict"] is None:
        status, content, outcome = 503, {"detail": state["reason"]}, "unavailable"
    else:
        row = {"request_id": uuid.uuid4(), "received_at": datetime.now(UTC), "model_name": MODEL_NAME,
               "model_version": state["version"], "image_commit": IMAGE_COMMIT,
               "source_id": request.headers.get("x-source-id")}
        status, content = await run_in_threadpool(serve, row, await read_body(request))
        outcome = row["outcome"]
    REQUESTS.labels("/predict", outcome, state["version"] or "").inc()
    LATENCY.labels("/predict").observe(time.perf_counter() - start)
    return JSONResponse(content, status_code=status)


@app.get("/health/live")
def live():
    return {"live": True}


@app.get("/health/ready")
def ready():
    if state["predict"] is None:
        return JSONResponse({"ready": False, "reason": state["reason"]}, status_code=503)
    try:
        check_log()
    except (psycopg.Error, KeyError) as err:
        return JSONResponse({"ready": False, "reason": f"the request log is unreachable: {type(err).__name__}: {err}"},
                            status_code=503)
    return {"ready": True, "model_name": MODEL_NAME, "model_version": state["version"], "image_commit": IMAGE_COMMIT}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

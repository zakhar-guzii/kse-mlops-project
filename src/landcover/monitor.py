"""Lab 4 drift reports: the served window against the training reference (docs/design.md 6.6).

    python -m landcover.monitor replay --ml http://127.0.0.1:8000
    python -m landcover.monitor reference --ml URL --mlflow URL --dsn DSN
    python -m landcover.monitor labels --dsn DSN
    python -m landcover.monitor report      # the CronJob; configuration from the environment

The observation unit is a 256x256 quadrant sent to /predict, so the ML service computes the features of both
sides. A request's source ID (header X-Source-Id) marks what it is: `reference/<data version>/<batch>/<tile>/q<n>`
for the training reference, `replay/<batch>/<tile>/q<n>` for held-out traffic, which is also the label key.
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import numpy as np
import psycopg
import rasterio
import yaml
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
from rasterio.io import MemoryFile
from rasterio.windows import Window

from landcover.models import CLASS_NAMES, SCORED, confusion, scores
from landcover.pipeline import BATCH_ROLES, IGNORE, LUT, ROOT, batch_dir

QUADRANT = 256
WINDOW_MINUTES = int(os.environ.get("WINDOW_MINUTES", "5"))
MIN_OBSERVATIONS = int(os.environ.get("MIN_OBSERVATIONS", "50"))
DRIFT_THRESHOLD = float(os.environ.get("DRIFT_THRESHOLD", "0.5"))
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "http://pushgateway:9091")
MODEL_NAME = os.environ.get("MODEL_NAME", "landcover-segmenter")
JOB = "landcover-drift"

# Input features and the shares of the six classes the labels can score. developed and road have zero variance
# in the reference (no FLAIR label maps to them), so a normed distance on them would divide by almost nothing.
COLUMNS = ["mean_r", "mean_g", "mean_b", "brightness"] + [f"share_{CLASS_NAMES[c]}" for c in SCORED]
TRAIN = [b for b, role in BATCH_ROLES.items() if role == "train"]
HELD_OUT = [b for b, role in BATCH_ROLES.items() if role in ("dev", "final")]
LABELLED = "D017-2021"  # the development batch; nothing here opens the final batch's labels
NOT_REFERENCE = "NOT starts_with(coalesce(source_id, ''), 'reference/')"
SCHEMA = ROOT / "sql" / "serving.sql"


# Quadrants and source IDs


def tiles(batch):
    return sorted((batch_dir(batch) / "images").glob("*.tif"))


def windows(height, width):
    """Row-major 256x256 windows: q0 top-left, q1 top-right, q2 bottom-left, q3 bottom-right for 512x512."""
    return [Window(col, row, QUADRANT, QUADRANT) for row in range(0, height, QUADRANT)
            for col in range(0, width, QUADRANT)]


def quadrants(path):
    """(q, GeoTIFF bytes) per quadrant, all bands with the source's colour roles, so validity is unchanged."""
    with rasterio.open(path) as src:
        for q, window in enumerate(windows(src.height, src.width)):
            profile = src.profile | {"width": QUADRANT, "height": QUADRANT,
                                     "transform": src.window_transform(window)}
            with MemoryFile() as memfile:
                with memfile.open(**profile) as dst:
                    dst.write(src.read(window=window))
                    dst.colorinterp = src.colorinterp
                yield q, memfile.read()


def label_quadrants(path):
    """(q, crosswalked uint8 mask) per quadrant of a label raster."""
    with rasterio.open(path) as src:
        for q, window in enumerate(windows(src.height, src.width)):
            yield q, LUT[src.read(1, window=window)]


def source_id(kind, batch, tile, q, data_version=None):
    parts = [kind] + ([data_version] if data_version else []) + [batch, tile, f"q{q}"]
    return "/".join(parts)


def data_version():
    """The DVC hash of data/raw in the committed pointer file."""
    return yaml.safe_load((ROOT / "data" / "raw.dvc").read_text())["outs"][0]["md5"].removesuffix(".dir")


# Windows


def window(now, minutes=WINDOW_MINUTES):
    """[start, end) of the last complete window before `now`; `end` is `now` rounded down to `minutes`."""
    end = now.replace(second=0, microsecond=0) - timedelta(minutes=now.minute % minutes)
    return end - timedelta(minutes=minutes), end


def containing(t, minutes=WINDOW_MINUTES):
    """The window that a request received at `t` belongs to."""
    return window(t + timedelta(minutes=minutes), minutes)


# Host commands: replay, reference, labels


def post(ml, body, source):
    request = urllib.request.Request(f"{ml}/predict", data=body, headers={"X-Source-Id": source})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"{source}: /predict answered {error.code}: {error.read().decode()[:300]}")


def send(ml, items):
    """Post (source ID, bytes) pairs in order; returns the responses and the receive window of the batch."""
    responses, first = [], datetime.now(UTC)
    for source, body in items:
        responses.append(post(ml, body, source))
    last = datetime.now(UTC)
    return responses, containing(first), containing(last)


def replay(ml, batches=HELD_OUT, prefix="replay", wait=True):
    if wait:
        now = datetime.now(UTC)
        start = window(now)[1] + timedelta(minutes=WINDOW_MINUTES)
        print(f"waiting for the window that starts at {start:%H:%M} UTC", flush=True)
        time.sleep((start - now).total_seconds() + 5)
    items = ((source_id(prefix, batch, path.stem, q), body)
             for batch in batches for path in tiles(batch) for q, body in quadrants(path))
    responses, first, last = send(ml, items)
    print(f"{len(responses)} ok, window {first[0]:%H:%M}-{first[1]:%H:%M} UTC, "
          f"version {sorted({r['model_version'] for r in responses})}")
    if first != last:
        sys.exit(f"the replay crossed into the window {last[0]:%H:%M}-{last[1]:%H:%M} UTC; run it again")


def champion(mlflow):
    url = f"{mlflow}/api/2.0/mlflow/registered-models/alias?name={MODEL_NAME}&alias=champion"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)["model_version"]["version"]


def reference(ml, mlflow, dsn):
    """Send the training quadrants the champion's reference still lacks; nothing when it is complete."""
    version, dv = champion(mlflow), data_version()
    with psycopg.connect(dsn) as conn:
        done = {row[0] for row in conn.execute(
            "SELECT source_id FROM serving.predictions WHERE model_version = %s AND outcome = 'ok'"
            " AND starts_with(source_id, %s)", [version, f"reference/{dv}/"])}
    items = [(sid, body) for batch in TRAIN for path in tiles(batch) for q, body in quadrants(path)
             if (sid := source_id("reference", batch, path.stem, q, dv)) not in done]
    if not items:
        print(f"reference of version {version} exists: {len(done)} quadrants of data {dv}")
        return
    responses, _, _ = send(ml, items)
    served = {r["model_version"] for r in responses}
    if served != {version}:
        sys.exit(f"the service answered with version {sorted(served)}, champion is {version}; restart deployment/ml")
    print(f"reference of version {version}: {len(responses)} quadrants sent, {len(done) + len(responses)} in all")


def labels(dsn):
    """Store the development quadrants' crosswalked masks under their replay source IDs."""
    rows = []
    for path in tiles(LABELLED):
        for q, mask in label_quadrants(batch_dir(LABELLED) / "labels" / path.name):
            buffer = io.BytesIO()
            np.save(buffer, mask)
            rows.append((source_id("replay", LABELLED, path.stem, q), buffer.getvalue()))
    with psycopg.connect(dsn) as conn:
        conn.execute(SCHEMA.read_text())
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO serving.labels (source_id, mask) VALUES (%s, %s)"
                            " ON CONFLICT (source_id) DO NOTHING", rows)
        count = conn.execute("SELECT count(*) FROM serving.labels").fetchone()[0]
    print(f"labels: {len(rows)} quadrants of {LABELLED}, {count} in the table")


# The report


def insufficient(n_current, n_reference):
    """The reason a comparison has no value, or None."""
    if n_reference == 0:
        return "no_reference"
    if min(n_current, n_reference) < MIN_OBSERVATIONS:
        return "few_observations"
    return None


def drift(current, reference_rows):
    """Normed Wasserstein per column with Evidently's DataDriftPreset."""
    import pandas as pd
    from evidently import DataDefinition, Dataset, Report
    from evidently.presets import DataDriftPreset

    definition = DataDefinition(numerical_columns=COLUMNS)
    cur, ref = (Dataset.from_pandas(pd.DataFrame(rows, columns=COLUMNS, dtype=float), data_definition=definition)
                for rows in (current, reference_rows))
    preset = DataDriftPreset(columns=COLUMNS, method="wasserstein", threshold=DRIFT_THRESHOLD)
    return parse(Report([preset]).run(cur, ref).dict())


def parse(result):
    """{"distances": {column: value}, "drifted": count, "share": share} from a DataDriftPreset result."""
    distances, counted = {}, None
    for metric in result["metrics"]:
        kind = metric["config"]["type"]
        if kind.endswith(":ValueDrift"):
            distances[metric["config"]["column"]] = float(metric["value"])
        elif kind.endswith(":DriftedColumnsCount"):
            counted = metric["value"]
    if counted is None or set(distances) != set(COLUMNS):
        raise ValueError(f"unexpected Evidently result: columns {sorted(distances)}, count {counted}")
    return {"distances": distances, "drifted": int(counted["count"]), "share": float(counted["share"])}


def read_mask(data):
    with MemoryFile(data) as memfile, memfile.open() as src:
        return src.read(1)


def quality(pairs):
    """(mean IoU, None) over (label .npy, logged mask) pairs, or (None, reason)."""
    if len(pairs) < MIN_OBSERVATIONS:
        return None, "few_observations"
    matrix, ignored, total = 0, 0, 0
    for label_npy, mask in pairs:
        label = np.load(io.BytesIO(label_npy), allow_pickle=False)
        matrix = matrix + confusion(label, read_mask(mask))
        ignored, total = ignored + int((label == IGNORE).sum()), total + label.size
    try:
        return scores(matrix, ignored, total)["miou"], None
    except ValueError:
        return None, "incomplete_labels"


def versions(conn, start, end):
    """Versions served in the window plus the version and time of the latest served request."""
    rows = conn.execute(f"SELECT DISTINCT model_version FROM serving.predictions WHERE outcome = 'ok'"
                        f" AND {NOT_REFERENCE} AND received_at >= %s AND received_at < %s", [start, end])
    found = {row[0] for row in rows}
    latest = conn.execute(f"SELECT model_version, received_at FROM serving.predictions WHERE outcome = 'ok'"
                          f" AND {NOT_REFERENCE} ORDER BY received_at DESC LIMIT 1").fetchone()
    if latest:
        found.add(latest[0])
    return sorted(found), latest[1] if latest else None


def evaluate(conn, version, start, end):
    columns = ", ".join(COLUMNS)
    current = conn.execute(f"SELECT {columns} FROM serving.predictions WHERE model_version = %s AND outcome = 'ok'"
                           f" AND {NOT_REFERENCE} AND received_at >= %s AND received_at < %s",
                           [version, start, end]).fetchall()
    ref = conn.execute(f"SELECT {columns} FROM serving.predictions WHERE model_version = %s AND outcome = 'ok'"
                       " AND starts_with(source_id, 'reference/')", [version]).fetchall()
    pairs = conn.execute("SELECT l.mask, p.mask FROM serving.predictions p JOIN serving.labels l USING (source_id)"
                         " WHERE p.model_version = %s AND p.outcome = 'ok' AND p.received_at >= %s"
                         " AND p.received_at < %s", [version, start, end]).fetchall()
    result = {"observations": {"current": len(current), "reference": len(ref), "labelled": len(pairs)}}
    reason = insufficient(len(current), len(ref))
    result["drift"] = {"insufficient": reason} if reason else drift(current, ref)
    miou, reason = quality(pairs)
    result["quality"] = {"insufficient": reason} if reason else {"miou": miou}
    return result


def to_registry(results, window_end, latest):
    """The report as one Pushgateway group; a version or column absent from `results` has no series."""
    registry = CollectorRegistry()

    def gauge(name, doc, labels=()):
        return Gauge(name, doc, labels, registry=registry)

    distance = gauge("landcover_drift_distance", "Normed Wasserstein distance of the column",
                     ["model_version", "column"])
    drifted = gauge("landcover_drift_columns_drifted", "Columns at or above the threshold", ["model_version"])
    share = gauge("landcover_drift_columns_share", "Drifted columns over all columns", ["model_version"])
    observations = gauge("landcover_report_observations", "Observations per side", ["model_version", "side"])
    missing = gauge("landcover_report_insufficient", "1 when the signal has no value",
                    ["model_version", "signal", "reason"])
    miou = gauge("landcover_quality_miou", "Mean IoU of the six scored classes on labelled rows", ["model_version"])
    gauge("landcover_drift_threshold", "Distance at which a column counts as drifted").set(DRIFT_THRESHOLD)
    gauge("landcover_report_window_end_seconds", "End of the report window, Unix time").set(window_end.timestamp())
    if latest:
        gauge("landcover_latest_request_seconds", "Receive time of the latest served request, Unix time"
              ).set(latest.timestamp())
    for version, result in results.items():
        for side, n in result["observations"].items():
            observations.labels(version, side).set(n)
        if "insufficient" in result["drift"]:
            missing.labels(version, "drift", result["drift"]["insufficient"]).set(1)
        else:
            for column, value in result["drift"]["distances"].items():
                distance.labels(version, column).set(value)
            drifted.labels(version).set(result["drift"]["drifted"])
            share.labels(version).set(result["drift"]["share"])
        if "insufficient" in result["quality"]:
            missing.labels(version, "quality", result["quality"]["insufficient"]).set(1)
        else:
            miou.labels(version).set(result["quality"]["miou"])
    return registry


def report(dsn, now=None):
    start, end = window(now or datetime.now(UTC))
    with psycopg.connect(dsn) as conn:
        found, latest = versions(conn, start, end)
        results = {version: evaluate(conn, version, start, end) for version in found}
    push_to_gateway(PUSHGATEWAY_URL, job=JOB, registry=to_registry(results, end, latest))
    summary = {v: {"observations": r["observations"],
                   "drift": r["drift"].get("insufficient") or f"{r['drift']['drifted']} drifted",
                   "quality": r["quality"].get("insufficient") or round(r["quality"]["miou"], 4)}
               for v, r in results.items()}
    print(f"window {start:%Y-%m-%d %H:%M}-{end:%H:%M} UTC: {json.dumps(summary)}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("replay", help="send the held-out quadrants to /predict within one window")
    p.add_argument("--ml", required=True)
    p.add_argument("--no-wait", action="store_true", help="start at once instead of at the next window")
    p = sub.add_parser("reference", help="send the training quadrants the champion's reference lacks")
    p.add_argument("--ml", required=True)
    p.add_argument("--mlflow", required=True)
    p.add_argument("--dsn", required=True)
    p = sub.add_parser("labels", help="store the development quadrants' masks")
    p.add_argument("--dsn", required=True)
    sub.add_parser("report", help="compare the last window with the reference and push the result")
    args = parser.parse_args(argv)
    if args.command == "replay":
        replay(args.ml, wait=not args.no_wait)
    elif args.command == "reference":
        reference(args.ml, args.mlflow, args.dsn)
    elif args.command == "labels":
        labels(args.dsn)
    else:
        report(os.environ["WAREHOUSE_DSN"])


if __name__ == "__main__":
    main()

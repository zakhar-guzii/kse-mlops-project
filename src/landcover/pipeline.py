"""Batch ingestion: plain functions wired into Airflow by dags/landcover_ingest.py."""

from pathlib import Path

import numpy as np
import psycopg
import rasterio

ROOT = Path(__file__).resolve().parents[2]

# Batch ID -> acquisition year. One batch per year; the run's data interval picks it.
BATCHES = {
    "D080-2017": 2017,
    "D033-2018": 2018,
    "D065-2019": 2019,
    "D045-2020": 2020,
    "D017-2021": 2021,
    "D073-2022": 2022,
}
# Batch ID -> model role, by whole batch. No training or scoring code opens the final batch.
BATCH_ROLES = {
    "D080-2017": "train",
    "D033-2018": "train",
    "D065-2019": "train",
    "D045-2020": "train",
    "D017-2021": "dev",
    "D073-2022": "final",
}
DEMO_BATCH = "bad-demo"  # structurally valid, every label maps to ignore; no year

# FLAIR-HUB class ID (0-18) -> internal OEM-8 ID, crosswalk v1 (docs/design.md, Section 5.2).
SOURCE_CLASSES = range(19)
CROSSWALK = {0: 7, 5: 0, 6: 5, 2: 5, 13: 4, 12: 4, 8: 1, 9: 6, 11: 6}
IGNORE = 255
NUM_CLASSES = 8
LUT = np.full(256, IGNORE, dtype=np.uint8)
LUT[list(CROSSWALK)] = list(CROSSWALK.values())

MAX_IGNORED_SHARE = 0.90
FEATURE_VERSION = "1"  # raise when the feature derivation or the crosswalk changes


def batch_dir(batch_id):
    if batch_id == DEMO_BATCH:
        return ROOT / "tests" / "fixtures" / "bad_batch"
    return ROOT / "data" / "raw" / batch_id


def resolve_batch(batch_id, year):
    """The batch_id parameter when given, else the batch registered for the year."""
    if batch_id is not None:
        if batch_id not in BATCHES and batch_id != DEMO_BATCH:
            raise ValueError(f"unknown batch {batch_id!r}")
        return batch_id
    for candidate, batch_year in BATCHES.items():
        if batch_year == year:
            return candidate
    raise ValueError(f"no batch registered for year {year}")


def extract(directory):
    """Tile IDs found in images/ or labels/; pairing is checked by validate."""
    tile_ids = sorted({p.stem for p in Path(directory).glob("*/*.tif")})
    if not tile_ids:
        raise ValueError(f"batch directory {directory} has no files")
    return tile_ids


def _problems(image_path, label_path):
    if not image_path.exists():
        return [f"{label_path}: no image"]
    if not label_path.exists():
        return [f"{image_path}: no label"]
    try:
        with rasterio.open(image_path) as image, rasterio.open(label_path) as label:
            problems = []
            if image.count < 3 or any(dtype != "uint8" for dtype in image.dtypes):
                problems.append(f"{image_path}: not 8-bit with at least three bands")
            if (image.width, image.height) != (label.width, label.height):
                problems.append(f"{image_path}, {label_path}: grid sizes differ")
            image.read()  # every band must decode, not only the three that transform uses
            unknown = set(np.unique(label.read(1)).tolist()) - set(SOURCE_CLASSES)
            if unknown:
                problems.append(f"{label_path}: unknown class IDs {sorted(unknown)}")
            return problems
    except rasterio.RasterioIOError as error:
        return [f"{image_path}, {label_path}: unreadable: {error}"]


def validate(directory, tile_ids):
    directory = Path(directory)
    problems = []
    for tile_id in tile_ids:
        problems += _problems(
            directory / "images" / f"{tile_id}.tif", directory / "labels" / f"{tile_id}.tif"
        )
    if problems:
        raise ValueError("batch rejected:\n" + "\n".join(problems))


def transform(directory, tile_ids):
    """Per tile: grid size, pixels per internal class, ignored pixels, mean of R, G, B."""
    directory = Path(directory)
    rows = []
    for tile_id in tile_ids:
        with rasterio.open(directory / "images" / f"{tile_id}.tif") as image:
            rgb = image.read([1, 2, 3])
        with rasterio.open(directory / "labels" / f"{tile_id}.tif") as label:
            internal = LUT[label.read(1)]
        counts = np.bincount(internal.ravel(), minlength=256)
        rows.append(
            {
                "tile_id": tile_id,
                "width": internal.shape[1],
                "height": internal.shape[0],
                "class_px": counts[:NUM_CLASSES].tolist(),
                "ignored_px": int(counts[IGNORE]),
                "channel_mean": rgb.reshape(3, -1).mean(axis=1).tolist(),
            }
        )
    return rows


def check_ignored_share(ignored_px, total_px):
    """The gate rule: returns the share, or raises when it exceeds the maximum."""
    share = ignored_px / total_px
    if share > MAX_IGNORED_SHARE:
        raise ValueError(
            f"ignored-pixel share {share:.2f} exceeds the maximum {MAX_IGNORED_SHARE:.2f}"
            f" ({ignored_px} of {total_px} pixels)"
        )
    return share


def _lock_batch(conn, batch_id):
    """Concurrent writers of one batch wait for each other until the transaction ends."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [batch_id])


def load(dsn, batch_id, rows):
    """Replace the batch's tile rows in one transaction."""
    with psycopg.connect(dsn) as conn:
        _lock_batch(conn, batch_id)
        conn.execute("DELETE FROM dwh.tiles WHERE batch_id = %s", [batch_id])
        conn.cursor().executemany(
            "INSERT INTO dwh.tiles (batch_id, tile_id, year, width, height, class_px,"
            " ignored_px, channel_mean) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (batch_id, r["tile_id"], BATCHES.get(batch_id), r["width"], r["height"],
                 r["class_px"], r["ignored_px"], r["channel_mean"])
                for r in rows
            ],
        )


def build_features(dsn, batch_id):
    """Replace the batch's feature rows, derived in SQL from its tile rows."""
    with psycopg.connect(dsn) as conn:
        _lock_batch(conn, batch_id)
        conn.execute("DELETE FROM features.tile_features WHERE batch_id = %s", [batch_id])
        conn.execute(
            """
            INSERT INTO features.tile_features
                (batch_id, tile_id, feature_version, class_share, ignored_share, channel_mean)
            SELECT t.batch_id, t.tile_id, %s,
                (SELECT array_agg(c::real / (t.width * t.height) ORDER BY i)
                 FROM unnest(t.class_px) WITH ORDINALITY AS u(c, i)),
                t.ignored_px::real / (t.width * t.height),
                (SELECT array_agg(m / 255 ORDER BY i)
                 FROM unnest(t.channel_mean) WITH ORDINALITY AS u(m, i))
            FROM dwh.tiles t
            WHERE t.batch_id = %s
            """,
            [FEATURE_VERSION, batch_id],
        )


def quality_check(dsn, batch_id):
    """Apply the gate to the batch's tile rows; a refused batch leaves no rows."""
    with psycopg.connect(dsn) as conn:
        ignored_px, total_px = conn.execute(
            "SELECT sum(ignored_px), sum(width::bigint * height) FROM dwh.tiles"
            " WHERE batch_id = %s",
            [batch_id],
        ).fetchone()
        try:
            return check_ignored_share(int(ignored_px), int(total_px))
        except ValueError:
            conn.execute("DELETE FROM features.tile_features WHERE batch_id = %s", [batch_id])
            conn.execute("DELETE FROM dwh.tiles WHERE batch_id = %s", [batch_id])
            conn.commit()
            raise

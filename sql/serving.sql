-- Lab 4 request log of the ML service (src/landcover/serve_ml.py), in the database landcover.
-- The service runs this file at start-up; every statement is idempotent. The drift job reads it.
-- One row per served /predict request. Feature and share columns are null unless outcome = 'ok';
-- means are over valid pixels on 0-255, brightness is their mean, shares are of valid pixels.

CREATE SCHEMA IF NOT EXISTS serving;

CREATE TABLE IF NOT EXISTS serving.predictions (
    request_id        uuid        PRIMARY KEY,
    received_at       timestamptz NOT NULL,
    model_name        text        NOT NULL,
    model_version     text        NOT NULL,
    image_commit      text        NOT NULL,
    outcome           text        NOT NULL CHECK (outcome IN ('ok', 'invalid', 'error')),
    reason            text,
    source_id         text,
    width             integer,
    height            integer,
    valid_px          integer,
    mean_r            real,
    mean_g            real,
    mean_b            real,
    brightness        real,
    share_bareland    real,
    share_rangeland   real,
    share_developed   real,
    share_road        real,
    share_tree        real,
    share_water       real,
    share_agriculture real,
    share_building    real,
    dark_warning      boolean,
    mask              bytea
);

CREATE INDEX IF NOT EXISTS predictions_received_at ON serving.predictions (received_at);

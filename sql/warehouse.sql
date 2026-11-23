-- Runs once, on the first start of an empty PostgreSQL volume, in the database POSTGRES_DB (landcover).
-- Schema change: `make down` with volume removal, then reload the batches (design Decision 6).

CREATE DATABASE airflow;
CREATE DATABASE mlflow;

CREATE SCHEMA dwh;
CREATE SCHEMA features;

-- One typed row per image–label pair. class_px holds the internal classes 0–7 in order;
-- PostgreSQL arrays start at 1, so internal class k is class_px[k + 1].
CREATE TABLE dwh.tiles (
    batch_id     text     NOT NULL,
    tile_id      text     NOT NULL,
    year         smallint,          -- acquisition year; null for the demonstration batch
    width        integer  NOT NULL,
    height       integer  NOT NULL,
    class_px     integer[] NOT NULL,
    ignored_px   integer  NOT NULL,
    channel_mean real[]   NOT NULL,
    PRIMARY KEY (batch_id, tile_id)
);

-- Derived from dwh.tiles by build_features.
CREATE TABLE features.tile_features (
    batch_id        text   NOT NULL,
    tile_id         text   NOT NULL,
    feature_version text   NOT NULL,
    class_share     real[] NOT NULL,
    ignored_share   real   NOT NULL,
    channel_mean    real[] NOT NULL,
    PRIMARY KEY (batch_id, tile_id)
);

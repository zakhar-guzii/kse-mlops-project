# Design

## Context

See [proposal.md](proposal.md) for motivation, scope and the decisions settled with the author. The repository holds `docs/design.md`, three SVG diagrams, lint tooling and CI; `pyproject.toml` has no runtime dependencies and there is no application code.

Facts checked for this design on 2026-11-23:

- Hugging Face serves FLAIR-HUB as one ZIP per domain and modality. The six domains of the design total 4.88 GB; the image archives range from 103 MB to 1.27 GB. The host answers HTTP range requests, and Python's `zipfile` reads an archive listing and single members over a seekable range-request file object, so sampling does not need the whole archive.
- `D080-2017` has 100 patches: images are about 1.09 MB each (512×512, four bands), labels about 9 KB.
- Airflow 3 documentation: a bare cron string in `schedule=` uses `CronTriggerTimetable`, whose runs have `data_interval_start == data_interval_end == logical_date`. For manually triggered runs, the data interval "depends on the timetable and the trigger path" and may differ from the supplied logical date.
- DVC documentation: `dvc pull` recalculates the hashes of downloaded files only when the remote has `verify = true`; this is off by default for S3 remotes. Files matched by `.dvcignore` are not part of a tracked directory's hash.

Pinned versions come from the course reference table: `pgsty/silo:RELEASE.2026-09-16T00-00-00Z`, DVC 3.67.1 with dvc-s3 3.3.0, PostgreSQL 16, Airflow 3.3.1 with LocalExecutor. The project interpreter is Python 3.12.

## Goals / Non-Goals

**Goals:**

- Everything a reviewer runs is a `make` target or a command printed in the README.
- Pipeline logic lives in plain Python functions that are testable without Airflow or a database; the DAG file only wires them.
- The smallest set of services, files and checks that satisfies the specs. Where a tool already guarantees something, the project does not check it again.

**Non-Goals:**

- Anything about models: baselines, features chosen for a model, training data preparation.
- A file manifest, materialised remapped rasters, a migration tool, DVC pipeline stages, Feast, a public data remote, a configuration directory, or running the stack on Minikube (Lab 4).
- Reading raw data from the object store inside the pipeline. The store is the DVC remote; tasks read the pulled files.

## Decisions

### 1. One script fetches the sample

`scripts/fetch_sample.py` uses only the standard library. For each of the six FLAIR-HUB domains it reads the listings of the image and label archives at one pinned Hugging Face commit, keeps the patches present in both, sorts them by name and takes every k-th so that 16 pairs remain. Files are written unmodified as `data/raw/<batch_id>/images/<tile_id>.tif` and `data/raw/<batch_id>/labels/<tile_id>.tif`; a file that already exists is not downloaded again. The sample is about 105 MB.

The pinned commit and the count are constants in the script. There is no manifest and no per-file checksum: Decision 2 checks the result as a whole.

Images keep their near-infrared band; the pipeline reads the first three bands.

Alternatives considered: a committed manifest with per-file SHA-256 repeats what DVC's directory hash already proves. Downloading whole archives costs every reader 4.9 GB. A public bucket holding the sample would make the project redistribute data, against Section 6.5.

### 2. One DVC pointer; its hash is the data version

`data/raw.dvc` tracks the whole `data/raw/` directory. Its `md5` is the single data version identifier and the checksum the README states. Git history of that file is the dataset history, so the Lab 1 design's manifests, integer dataset version and watermark are not needed.

The committed `.dvc/config` defines the remote `silo`: `s3://landcover-dvc`, `endpointurl = http://localhost:9000` and `verify = true`. The endpoint is the local container; no cloud account is involved. `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are the standard variable names every S3 client reads, and here they hold the local store's user and password, exported by the Makefile from the untracked `.env`.

A committed `.dvcignore` lists `.DS_Store`, which would otherwise change the directory hash on macOS.

`make data` runs the fetch script, `dvc commit -f data/raw.dvc`, `git diff --exit-code HEAD -- data/raw.dvc` (which fails when the fetched data does not hash to the committed identifier) and `dvc push`. It seeds an empty store. Once the store holds the data, `dvc pull` is the retrieval command.

### 3. Local stack: Docker Compose

| Service | Image | Notes |
|---|---|---|
| `postgres` | `postgres:16` | Two databases: `landcover` for the pipeline's rows, `airflow` for Airflow's own bookkeeping tables, kept apart so the two do not mix |
| `silo` | `pgsty/silo:RELEASE.2026-09-16T00-00-00Z` | `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, a named volume |
| `create-bucket` | `amazon/aws-cli` | One-shot: creates `landcover-dvc` if missing, as the lab advises |
| `airflow` | Built from `docker/airflow/Dockerfile` on `apache/airflow:3.3.1-python3.12` | `airflow standalone` with `AIRFLOW__CORE__EXECUTOR=LocalExecutor` and PostgreSQL metadata |

All published ports bind to `127.0.0.1`. Every credential is a variable in `.env`, with names and placeholder values in `.env.example`. Airflow keeps the simple auth manager's generated admin password; `make airflow-password` prints it. `make up` and `make down` wrap Compose.

The Dockerfile adds the three runtime packages with pinned versions. `dags/`, `src/`, `data/` and `tests/fixtures/` are bind-mounted read-only with `PYTHONPATH` pointing at `src/`. This is a development layout: one Airflow container and code mounted from the host. It is not how the service would be deployed; images built from the repository arrive in Lab 4.

Runtime dependencies: `numpy`, `rasterio`, `psycopg[binary]`. Development dependencies: `pytest`, `dvc==3.67.1`, `dvc-s3==3.3.0`. `rasterio` is used because it reads the four-band GeoTIFFs and their grid size reliably.

### 4. Batch selection: plain `@yearly`, keyed on `data_interval_start`

`src/landcover/pipeline.py` holds a constant mapping from year to batch ID (2017 to 2022, `D080-2017` to `D073-2022`). A batch's files are in `data/raw/<batch_id>`; the demonstration batch `bad-demo` is in `tests/fixtures/bad_batch`.

The DAG `landcover_ingest` uses `schedule="@yearly"`, `start_date` 2017-01-01 UTC, `end_date` 2022-01-01 UTC and `catchup=False`, with one nullable string parameter `batch_id`. One function resolves the batch: the parameter when set, otherwise the batch for `data_interval_start.year`; no match raises an error naming the year or the batch. The function never reads the clock.

This is the first of the two options the lab allows ("key your batch on `data_interval_start` alone"), and the README says so. It is chosen because, under `CronTriggerTimetable`, runs the timetable creates carry `data_interval_start` equal to the logical date, so a reviewer who backfills 2019-01-01 gets the 2019 batch. Checked in Airflow 3.3.1: a run from `airflow dags trigger --logical-date 2019-01-01` takes its data interval from the trigger time instead, so the resolver fails naming the current year; `airflow backfill create --from-date 2019-01-01 --to-date 2019-01-01` is therefore the dated trigger, and `--reprocess-behavior completed` reruns it. With `CronDataIntervalTimetable("@yearly")`, a manual run dated 2019-01-01 can be assigned the interval that ends on that date, which is the 2018 batch.

The timeline is historical, so `end_date` stops the scheduler from creating runs for years that have no batch. Runs are created by a backfill for one date.

### 5. Six tasks

`dags/landcover_ingest.py` wraps functions from `src/landcover/pipeline.py` as TaskFlow tasks.

| Task | Work |
|---|---|
| `extract` | Resolve the batch; pair the files in `images/` and `labels/`; fail when there are none |
| `validate` | The structural rules of the spec on every pair; fail with the list of offending files |
| `transform` | Per pair: apply the crosswalk to the label in memory, count pixels per internal class and ignored pixels, take the mean of each colour channel |
| `load` | One transaction: delete the batch's tile rows, insert the new ones |
| `build_features` | One statement pair: delete the batch's feature rows, `INSERT … SELECT` from its tile rows |
| `quality_check` | Compute the batch's ignored-pixel share from its tile rows; on failure delete the batch's rows from both tables and raise |

A batch has 16 pairs, so pair lists and tile rows travel as XCom values. Tasks connect to the warehouse with `psycopg` and a `WAREHOUSE_DSN` environment variable, without an Airflow provider or connection.

The FLAIR-HUB crosswalk from Section 5.2, the gate maximum and the feature version are constants in `pipeline.py`. They change only with a code change, so a configuration file would add a loader and a mount for no benefit.

### 6. Warehouse schema and idempotent load

`sql/warehouse.sql` creates the `airflow` database, two schemas and two tables; the PostgreSQL image runs it on the first start of an empty volume.

| Table | Key | Columns |
|---|---|---|
| `dwh.tiles` | `batch_id`, `tile_id` | `year`, `width`, `height`, `class_px integer[]`, `ignored_px`, `channel_mean real[]` |
| `features.tile_features` | `batch_id`, `tile_id` | `feature_version`, `class_share real[]`, `ignored_share`, `channel_mean real[]` |

The raw layer is the DVC-tracked directory, so no table repeats file names and checksums. `load` is delete-then-insert by `batch_id` inside one transaction, which is the statement that makes a rerun harmless. No wall-clock column is stored; Airflow keeps the run history.

A schema change after the first start needs `make down` with volume removal and a reload of the batches, which takes minutes. A migration tool is added when the warehouse holds state that cannot be rebuilt.

### 7. Feature table derived in SQL

`features.tile_features` holds values derived from `dwh.tiles` and not stored there: the share of each internal class and of ignored pixels among all pixels of the tile, and the channel means scaled to 0–1. It is filled from the cleaned rows by SQL, as the lab words it, and it does not depend on any model.

`feature_version` is the constant `"1"`, raised by hand when the derivation or the crosswalk changes. The lab asks for the column; hashing a configuration or keeping several versions side by side has no reader in this change.

### 8. Quality gate and the broken batch

One rule: the batch's ignored pixels divided by all its pixels is at most 0.90. The error states both numbers.

`tests/fixtures/bad_batch/` holds two committed 64×64 image–label pairs in FLAIR-HUB format whose labels contain only a class that the crosswalk maps to ignore. The batch is structurally valid, so it reaches `quality_check`, which measures a share of 1.00, removes the batch's rows and fails. The README describes this construction and shows the red task.

Removing the rows is what makes the gate a gate: after a failed run the refused batch has no rows, so no acceptance flag or batch table is needed. Two limits are stated in Section 5.2 instead of being engineered away: the rows are visible to other readers between `load` and the end of `quality_check`, and a rerun that fails structural validation stops before `load`, so the rows of the batch's earlier successful run stay.

Dropped from the Lab 1 design: the "no new checksum" rule. Each year has its own DVC-tracked directory, so one batch cannot silently re-read another's files. A run for a year without a registered batch, or with an empty batch directory, fails, and that is the freshness check that remains.

### 9. Document revisions

| Location | Revision |
|---|---|
| Section 4, Freshness and Reproducibility rows | A run for a year with no registered batch or no files fails; rerunning a batch replaces its rows |
| Section 5.2 | Add the course sample and its rule; state that OpenEarthMap is not ingested in the course yet; name the batch grain (one acquisition year, one FLAIR-HUB domain), the zero label delay and the single data version identifier; replace the "Manifest and freshness" example with batch selection and rerun; remove the three mentions of manifests; update the storage table (pgsty/silo, the two tables, "SQL schema file in Git", crosswalk in code, remapped rasters not stored in the course); note that the course tables store only the acquisition year; state that DVC pipeline stages are not used |
| Section 6.1 | Alt text and caption of the data-flow figure |
| Section 6.2 | Object storage and data versioning rows; replace the Floci paragraphs with a short pgsty/silo paragraph; note that Lab 2 runs on Docker Compose and Minikube arrives in Lab 4; feature store row: feature table in PostgreSQL, Feast not used |
| Section 6.4 | Where credentials live in the course stack, the committed remote configuration without secrets, ports bound to localhost |
| Section 6.5 | The sample is fetched from the source and kept locally and in the local store; the project still redistributes neither dataset |
| Section 6.6, training batch gate row | Structural validation and the ignored-share rule; a refused batch leaves no rows |
| Section 6.8, OpenEarthMap and FLAIR-HUB rows | FLAIR-HUB: retrieval of pinned files and the DVC hash check; OpenEarthMap: not ingested in the course yet |
| Section 7.4, storage checks | Name pgsty/silo; report the DVC push and pull check; leave the MLflow artifact check to the second change and the upload and signed-URL checks to Lab 4 |
| `data-flow.svg` | Real component names: source, `make data`, DVC with pgsty/silo, the six Airflow tasks, the two PostgreSQL tables, the quality gate at `quality_check`. Layers 4 to 7 keep their content |
| `deployment.svg` | Storage card and `<desc>`: pgsty/silo |

The document keeps describing the full-data product; the sample is presented as the course-scale instance of the same pipeline. Section 5.3 is not edited (see the proposal's carry-over).

## Risks / Trade-offs

- Hugging Face is down during a retrieval from the source → the author's machine already holds the data in the local store, where `dvc pull` works; the script skips files it already has.
- A manually dated run does not carry `data_interval_start` equal to its logical date in Airflow 3.3.1 (confirmed during implementation: the interval is the trigger time) → real years are run with `airflow backfill create`, verified against the warehouse; a plain dated trigger fails loudly in the resolver instead of loading a wrong year.
- `airflow standalone` or the package install conflicts with the Airflow image → fall back to the official Compose services and record the reason.
- Containers exit with code 132 on Apple Silicon → update Docker Desktop, or add the `cryptography==46.0.5` line from the lab notes to the Dockerfile and say so in the README.
- `pgsty/silo` has no arm64 image → run it with `platform: linux/amd64`; the store is not on a performance path.
- A real batch exceeds the 0.90 maximum → the final clean-clone pass loads all six; raise the constant only with the measured share written next to it.
- Row counts are 16 per batch and table, which is small → accepted; the lab asks for identical counts, and a larger sample would exceed the size ceiling.
- The three package versions are pinned in the Dockerfile and in `uv.lock` separately → they are changed together; with three packages a generated file is not worth its upkeep.

## Migration Plan

There is nothing deployed to migrate. Rollback is reverting the change and running `make down` with volume removal. The Floci decision of the archived change `align-lab1-design-with-floci` is superseded in the active documents; archived artifacts are not edited.

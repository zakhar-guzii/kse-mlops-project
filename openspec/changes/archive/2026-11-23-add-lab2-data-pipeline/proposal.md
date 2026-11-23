# Proposal

## Why

Lab 2 (steps 2–4) requires the data side of the Lab 1 design to exist and be checkable: a reviewer pulls versioned raw data, runs the ingestion pipeline for one batch twice with identical row counts, and sees a quality gate refuse a deliberately bad batch. The repository currently holds only the design and lint tooling, and the design disagrees with the lab in several places that were settled with the author before this proposal.

This is the first of two consecutive Lab 2 changes. The second covers models, baselines, training, MLflow, Sections 5.3, 5.4 and 7.2, the scorecard and the `lab-2` tag. Nothing here chooses or prepares for a model.

## What Changes

- Add a versioned raw dataset: a fixed sample of unmodified FLAIR-HUB files (six domains, about 105 MB), tracked by DVC with an S3-compatible remote. One script fetches the sample from the pinned public source; DVC's content hash is the only integrity check. The project still redistributes no data.
- Add a local Docker Compose stack: PostgreSQL 16, Apache Airflow 3.3.1 with LocalExecutor, and the course-reference object store `pgsty/silo`.
- Add one Airflow DAG with the tasks `extract`, `validate`, `transform`, `load`, `build_features` and `quality_check`. A run processes exactly one batch, chosen by the year of the run's data interval start, or by a `batch_id` parameter for the demonstration batch.
- Add two PostgreSQL tables: one typed row per image–label tile, and a feature table derived from those rows with a `feature_version` column. Rerunning a batch replaces its rows.
- Add a quality gate that fails the run for a committed, deliberately broken batch and leaves none of its rows in the warehouse.
- Extend the README with the commands needed to run the above and the facts the lab requires there: how the sample was drawn, the remote type, the retrieval command, the checksum, the timetable choice, both row counts of a repeated run, how the broken batch was built, and two Airflow screenshots. Nothing else goes into the README.
- Revise `docs/design.md` so that it describes what is built: Sections 5.2, 6.2, 6.4, 6.5 and 6.8 and the data-flow diagram, plus the consistency edits these decisions force in Sections 4, 6.6 and 7.4 and in `docs/diagrams/deployment.svg`.

Decisions settled with the author, each replacing a statement of the Lab 1 design:

| Topic | Lab 1 design | This change |
|---|---|---|
| Raw data volume and retrieval | Full archives (about 14 GB) with file manifests on a local remote | A sample under 200 MB fetched by a script; no manifest; the full-data design stays as the product description |
| OpenEarthMap | Ingested as the initial batch | Not ingested yet; the second change adds it if its model needs it |
| Batch selection and rerun | Batch found from a folder and a watermark; a repeated batch fails unless `replay=true` | Batch chosen by the run's data interval or a parameter; a rerun replaces the batch's rows; the watermark, `replay=true` and the "no new checksum" rule are removed |
| Tabular layers | Rasters only; no feature table | Two PostgreSQL tables; remapped rasters are not stored; Feast is not used |
| Local object store | Floci | `pgsty/silo`, the course reference |

## Capabilities

### New Capabilities

- `raw-data-versioning`: the sampled raw dataset, its single version identifier, retrieval and the remote pull.
- `batch-ingestion-pipeline`: selecting one batch per run, the task graph, structural validation, tile rows, the feature table, idempotent reruns and the quality gate.

### Modified Capabilities

None. The project has no main specs yet.

## Impact

- New code and configuration: `scripts/fetch_sample.py`, `src/landcover/pipeline.py`, `dags/`, `sql/`, `tests/`, `docker-compose.yml`, `docker/airflow/Dockerfile`, `.env.example`, `.dvc/`, `.dvcignore`, `data/raw.dvc`.
- Changed tooling: `pyproject.toml` and `uv.lock` (runtime and development dependencies), `Makefile` (stack, data and test targets), `.gitignore`, `.github/workflows/lint.yml` (runs the unit tests).
- Changed documents: `README.md`, `docs/design.md`, `docs/diagrams/data-flow.svg`, `docs/diagrams/deployment.svg`, new `docs/screenshots/`, and the affected passages of the local, ignored `docs/design.uk.md` if it exists.
- External systems: Hugging Face is read during data retrieval. No cloud resources are created and no paid service is added.
- Out of scope: models, baselines and training, MLflow, Feast, OpenEarthMap ingestion, Sections 5.3, 5.4 and 7.2, the maturity scorecard and the `lab-2` tag.
- Known carry-over to the second change: Section 5.3 keeps one sentence that mentions the removed `replay=true` flag, and it needs a serving-source row for the feature table. Section 5.3 is outside this change by the author's decision.

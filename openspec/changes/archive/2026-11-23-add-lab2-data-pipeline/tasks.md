# Tasks

Follow [design.md](design.md) and the specs under [specs/](specs/). Section numbers refer to `docs/design.md`. Do not add anything about models, MLflow, Feast, OpenEarthMap ingestion, scorecard rows or the `lab-2` tag, and do not edit Sections 5.3, 5.4 or 7.2. README additions are limited to commands and the facts the lab requires there.

## 1. Dependencies and local stack

- [x] 1.1 Add the runtime dependencies (`numpy`, `rasterio`, `psycopg[binary]`) and development dependencies (`pytest`, `dvc==3.67.1`, `dvc-s3==3.3.0`) to `pyproject.toml`, set pytest's `pythonpath` to `src`, and refresh `uv.lock`; verify `make setup` and `make lint` pass and `uv run --locked dvc version` reports 3.67.1.
- [x] 1.2 Add `.env.example`, `sql/warehouse.sql` (the `airflow` database, two schemas and the two tables of design Decision 6) and `docker-compose.yml` with `postgres`, `silo` and `create-bucket`, all ports bound to `127.0.0.1`; verify after `docker compose up` that `\dt dwh.* features.*` lists both tables and the bucket `landcover-dvc` exists. If `pgsty/silo` has no arm64 image, set `platform: linux/amd64`.
- [x] 1.3 Add `docker/airflow/Dockerfile`, the `airflow` service of design Decision 3, the `make up`, `make down` and `make airflow-password` targets, and the stack commands in the README; verify inside the container that `airflow config get-value core executor` prints `LocalExecutor`, the metadata connection points at PostgreSQL and `import rasterio, psycopg` succeeds, and that the README commands run as written. If standalone or the install fails, apply the fallback in the design's risks and record what changed.

## 2. Raw data

- [x] 2.1 Write `scripts/fetch_sample.py` as in design Decision 1 and run it; verify `data/raw/` holds six batch directories with 16 image–label pairs each, the total is under 200 MB, and a second run downloads nothing.
- [x] 2.2 Initialise DVC, add the `silo` remote with `verify = true` to `.dvc/config`, add `.dvcignore` with `.DS_Store`, track `data/raw`, commit `data/raw.dvc` and add the `make data` target; verify that after deleting `data/raw` and `.dvc/cache`, `make data` passes its pointer check and pushes, and that after deleting them again `dvc pull` followed by `dvc status -q` succeeds.
- [x] 2.3 Add to the README the remote type, the sampling rule in one sentence, the retrieval commands and the data version identifier as the checksum of what arrives; verify `git grep` finds no credential value in tracked files and `data/raw/` is ignored by Git.

## 3. Ingestion pipeline

- [x] 3.1 Implement in `src/landcover/pipeline.py` the constants of design Decisions 4, 5 and 8, batch resolution, `extract`, `validate`, `transform` and the gate rule as plain functions, with `tests/test_pipeline.py` on small rasters written to a temporary directory; add `make test` and run it in `.github/workflows/lint.yml`. Verify the tests cover a year match, a parameter match, an unknown year, a grid mismatch, an unknown class ID, an empty batch, the per-class counts after the crosswalk, and the gate rule passing and failing.
- [x] 3.2 Implement `load`, `build_features` and `quality_check` against the warehouse and add `dags/landcover_ingest.py` with the six tasks and the schedule, dates and parameter of design Decision 4; verify `airflow dags list-import-errors` is empty.
- [x] 3.3 Trigger a run with logical date 2019-01-01; verify all six tasks succeed and both tables hold 16 rows, all for `D065-2019` and with `feature_version` set. If the run resolves a different year, apply the mitigation in the design's risks before continuing.

## 4. Evidence the lab asks for

- [x] 4.1 Commit the two-pair fixture `tests/fixtures/bad_batch/` and run the pipeline with `batch_id` `bad-demo`; verify `extract` through `build_features` succeed, `quality_check` fails with the measured share and the maximum in its message, and neither table holds a row for `bad-demo`.
- [x] 4.2 Run the 2019 interval a second time and query the row counts of both tables grouped by `batch_id` after each run; verify the counts are identical and keep both outputs.
- [x] 4.3 Add to the README the timetable choice in one sentence, the trigger command, both outputs from 4.2, how the broken batch was built and run, and two screenshots in `docs/screenshots/` (a successful run graph and the failed `quality_check` task). Ask the author for the screenshots if the UI cannot be captured; verify the commands run as written and both images render.

## 5. Design document and diagrams

- [x] 5.1 Revise Section 5.2 as listed in design Decision 9; verify it names the source, the sample rule, the batch grain, the zero label delay and the single data version identifier, that the storage table lists the two tables and pgsty/silo, and that Sections 1–5.2 no longer mention manifests, the watermark, `replay=true` or Floci.
- [x] 5.2 Revise Sections 6.2, 6.4, 6.5 and 6.8; verify the object storage and data versioning rows name pgsty/silo and the pinned DVC versions, the Floci paragraphs are replaced, the Docker Compose note is present, the feature store row says Feast is not used, 6.4 states where course credentials live, 6.5 still says the project redistributes neither dataset, and 6.8 matches the retrieval as implemented.
- [x] 5.3 Make the consistency edits in Section 4 (Freshness and Reproducibility rows), Section 6.6 (training batch gate row) and the storage checks of Section 7.4; verify they agree with the specs, that Section 7.4 reports only the DVC check actually run in task 2.2, and that no other row of those tables changed.
- [x] 5.4 Update `docs/diagrams/data-flow.svg`, its alt text and caption in Section 6.1, and the storage card and `<desc>` of `docs/diagrams/deployment.svg`; render both and verify the labels are readable and unclipped, the six task names and two tables appear, and layers 4 to 7 are unchanged.
- [x] 5.5 If the local `docs/design.uk.md` exists, synchronise only the passages changed in 5.1–5.4; verify `git check-ignore docs/design.uk.md` still succeeds. Do not create the file if it is missing.

## 6. Integration check

- [x] 6.1 On a fresh clone in a scratch directory, follow only the README: set up, start the stack, retrieve the data, load all six years, run one year twice and run the broken batch; verify each step behaves as the README says, that all six real batches pass the gate, and fix the README where it does not match.
- [x] 6.2 Run `openspec validate add-lab2-data-pipeline --strict`, `make lint`, `make test` and `git diff --check`; verify all pass and that Sections 5.3, 5.4 and 7.2 are untouched.

## 7. Review fixes

- [x] 7.1 Make `validate` read every band of each image and name both files of an unreadable pair; reject an empty `batch_id` parameter; add the pixel counts to the gate error. Verify with tests on a TIFF whose fourth band is truncated, on `batch_id` `""` and on a share of 901/1000.
- [x] 7.2 Take a per-batch advisory lock in `load` and `build_features`; verify that concurrent writers of one batch no longer fail with `UniqueViolation`.
- [x] 7.3 Add tests for the crosswalk per source class ID, for the equality of the fetched domains and the registered batches, and one warehouse test (two batches, a rerun of one, a refused batch) that runs when `TEST_DSN` names a PostgreSQL server; provide that server in `.github/workflows/lint.yml`.
- [x] 7.4 Compare the pointer with `HEAD` in `make data`; skip a domain that already holds all its pairs in `scripts/fetch_sample.py`, so that a second run makes no request; correct the `class_px` indexing comment in `sql/warehouse.sql`; state the supported password characters in `.env.example`.
- [x] 7.5 In Section 5.2 state what a failed validation and a failed gate leave in the warehouse and when rows are visible; in Section 6.2 name the GCP and Azure equivalents of the lab's reference table; in the README order the commands as run 2019, wait, count, repeat. Verify the README commands on the stack as written.

## Workflow follow-up

- Archive this change after review, then start the second Lab 2 change (models, training, MLflow, Sections 5.3, 5.4 and 7.2, scorecard, tag), including the Section 5.3 carry-over and the OpenEarthMap decision named in the proposal. Section 5.3 then needs a serving-source row for each feature column: `channel_mean` can be computed from the uploaded RGB; `class_share` and `ignored_share` need the reference mask, so they are training-data controls and must not become model inputs.

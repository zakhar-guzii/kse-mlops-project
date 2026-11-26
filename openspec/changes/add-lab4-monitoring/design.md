# Design

## Context

See proposal.md for the motivation and the decision tables, and the three specifications under `specs/` for the required behaviour. Current state that shapes the approach:

- **Request log (`add-lab4-services`).**
  - `serving.predictions` holds one row per served request. The row has `received_at`, `model_version`, `image_commit`, `outcome`, an optional client `source_id` (header `X-Source-Id`), the columns `mean_r`, `mean_g`, `mean_b`, `brightness` and `share_<class>`, and the mask as a deflate GeoTIFF.
  - The ML service runs the idempotent `sql/serving.sql` at start-up.
  - `serve_ml.observe()` defines the features.
- **Lab 2 scoring code.**
  - `models.confusion(label, prediction)` counts pixels and leaves out ignored ones.
  - `models.scores(matrix, ignored, total)` returns per-class IoU and `miou` over `SCORED = [0, 1, 4, 5, 6, 7]`. It raises `ValueError` when a scored class has no labelled pixel.
  - `pipeline.LUT` is crosswalk v1. `pipeline.BATCH_ROLES` names four training batches, `D017-2021` (dev) and `D073-2022` (final); no scoring code opens the final batch.
- **Data.** 16 tiles of 512×512 per batch in `data/raw/<batch>/images` and `labels`, fetched by `make sample`. The DVC hash of `data/raw` is `outs[0].md5` in `data/raw.dvc`.
- **Probe without a shift.** 384 quadrants: 256 training, 128 held-out. Random forest `rf-a8b3295` and U-Net `unet-c1f77a3`. Normed Wasserstein divides by the reference standard deviation.
  - Training against held-out, input features: 0.32–0.35.
  - Training against held-out, class shares: random forest bareland 0.53 and the other classes 0.14–0.25; U-Net up to 0.53 on three classes.
  - The no-shift null (training tiles split in half, stratified by batch, 300 times): worst feature median 0.23, p95 0.45.
  - One training batch against the other three: up to 1.59 (D065-2019 is 46 levels brighter).
  - `developed` and `road` have zero variance in the reference. Neither model predicts them from FLAIR training labels.
- **Evidently 0.7.23** (11.09.2026, the latest).
  - Call: `Report([DataDriftPreset(columns=…, method="wasserstein", threshold=…)]).run(current, reference)`, with current first. Datasets come from `Dataset.from_pandas(df, data_definition=DataDefinition(numerical_columns=…))`.
  - `snapshot.dict()["metrics"]` holds one `ValueDrift(column=…)` entry per column (`value` is the distance) and `DriftedColumnsCount` with `value: {count, share}`.
  - Normed Wasserstein divides by `max(std(reference), 0.001)`.
  - It fails to import with pandas 3. `mlflow==3.16.1`, `evidently==0.7.23` and `pandas<3` resolve together (pandas 2.3.3). pandas reaches the project only through mlflow.
  - Its environment is about 544 MB of site-packages: pyarrow, plotly, scipy, statsmodels, scikit-learn.
- **Pushgateway v1.11.4.**
  - PUT replaces the whole group. It adds `push_time_seconds` per group.
  - It keeps a group until deleted. It rejects client timestamps, so Prometheus stamps samples at scrape time.
  - The scrape needs `honor_labels: true`.
  - `prometheus_client.push_to_gateway` sends a PUT.
- **Prometheus v3.13.5** (LTS line 3.13, supported to 2027-07); `static_configs` needs no RBAC. **Grafana 13.3.2.** Data sources and file dashboards load from `/etc/grafana/provisioning`. `GF_AUTH_ANONYMOUS_ENABLED` and `GF_AUTH_ANONYMOUS_ORG_ROLE` enable viewing without a login.
- **Cluster (`add-lab4-cluster`).**
  - Objects in `k8s/landcover.yaml` with the placeholder `COMMIT`; generated ConfigMaps created with `create --dry-run=client -o yaml | apply`.
  - `scripts/cluster.sh` port-forwards MLflow to 5002, ML to 8000 and LLM to 8002. Its `forward()` waits for an HTTP answer.
  - Measured memory with the cluster up: the Minikube container uses 3.43 of 6 GiB. Pods: ml 583 Mi (peak 1,476 Mi on 1024×1024), llm 796 Mi, mlflow 488 Mi, postgres 133 Mi.
  - The kubelet reports 7.9 GB, more than Docker's 6 GiB cap, so the scheduler does not protect the node. Limits already sum to 5,290 Mi.
- **Tests.** `make test` syncs only the default groups. A test needing Evidently skips there and runs with `--group monitor`.

## Goals / Non-Goals

**Goals:**
- Every drift, quality and freshness number traceable to request-log rows a reviewer can query.
- The two-window demonstration in about 15 minutes after `make cluster`.
- A report job that `add-lab4-drift-alert` extends with a threshold and an alert without changing its metric names.

**Non-Goals:**
- Choosing and justifying the final threshold; alert rules; Alertmanager; the shifted replay.
- Long-term metric retention, Prometheus persistence, Grafana authentication beyond anonymous viewing on a loopback port-forward.
- Reports on the LLM service's answers.
- Evidently HTML reports or an Evidently UI.

## Decisions

### 1. One module, four commands

`src/landcover/monitor.py`, run as `python -m landcover.monitor <command>`:

| Command | Runs | Needs |
|---|---|---|
| `replay --ml URL [--batches …] [--prefix replay] [--no-wait]` | host | ML port-forward, `data/raw` |
| `reference --ml URL --mlflow URL --dsn DSN` | host | ML, MLflow and PostgreSQL port-forwards, `data/raw` |
| `labels --dsn DSN` | host | PostgreSQL port-forward, `data/raw` |
| `report` | CronJob | `WAREHOUSE_DSN`, `PUSHGATEWAY_URL` |

The host commands use only base dependencies (rasterio, numpy, psycopg, PyYAML through mlflow) and `urllib`. Evidently is imported inside `report` only, so the host and `make test` do not need the `monitor` group.

Alternative: separate scripts per command in `scripts/`. Rejected: they share the quadrant cutting, the source IDs and the column list, and a module is importable by the tests.

### 2. Quadrants and source IDs

`quadrants(path)` yields `(q, bytes)` for the four 256×256 windows in row-major order (`q0` top-left … `q3` bottom-right). Each window is written as a GeoTIFF of bands 1–3 with the window's transform, the CRS and the dataset masks. The service therefore applies the same valid-pixel rule as to any upload. `label_quadrants(path)` cuts the label raster the same way after `LUT`.

Source IDs:

| Use | Format |
|---|---|
| reference | `reference/<data version>/<batch>/<tile>/q<n>` |
| replay | `replay/<batch>/<tile>/q<n>` |
| label key | the replay ID of a development quadrant |

`add-lab4-drift-alert` sends its shifted replay under its own prefix. A non-reference row is one whose `source_id` is null or does not start with `reference/`.

### 3. Replay timing

`replay` sleeps until the next multiple of `WINDOW_MINUTES` plus 5 s, then posts the quadrants in batch and tile order, one at a time. Measured inference is 0.15 s per 512×512 tile for the random forest and 0.32 s for the U-Net, so 128 quadrants take well under a minute and fall into one window. It prints the number of `ok` responses and the window they fall in, and exits non-zero if any request fails. `--no-wait` skips the sleep.

### 4. Reference command

1. Read the champion version from MLflow (`GET /api/2.0/mlflow/registered-models/alias`, as `scripts/smoke.py` does) and the data version from `data/raw.dvc`.
2. Select the `source_id`s already logged for that version with prefix `reference/<data version>/`.
3. Post only the missing training quadrants. A complete reference sends nothing; an interrupted one resumes.
4. Fail if a response reports another `model_version`, because the pod has not been restarted after a promotion.

The reference of each version stays in the log. The report uses every reference row of the version it evaluates.

`ponytail:` a new data sample for the same model version would add a second set of reference rows; filter the report by data version if the sample ever changes.

Alternative: a separate table `serving.reference` written by a host script that loads the model. Rejected with the author (proposal): the host would need torch for the U-Net, and the loading path would be a second copy of the service's.

### 5. Labels

`sql/serving.sql` gains:

```sql
CREATE TABLE IF NOT EXISTS serving.labels (
    source_id  text PRIMARY KEY,
    mask       bytea NOT NULL,          -- numpy .npy of the 256x256 uint8 crosswalked label
    arrived_at timestamptz NOT NULL DEFAULT now()
);
```

`labels` writes the 64 development quadrants with `ON CONFLICT (source_id) DO NOTHING`. It names `D017-2021` explicitly and has no option to read another batch. A `.npy` blob carries its shape and dtype and is read with `np.load(…, allow_pickle=False)`.

The ML service creates the table when it starts with a new image. `labels` also runs the same `CREATE TABLE IF NOT EXISTS`, so the order of steps does not matter.

### 6. Report job

Configuration (environment): `WAREHOUSE_DSN`, `PUSHGATEWAY_URL=http://pushgateway:9091`, `WINDOW_MINUTES=5`, `MIN_OBSERVATIONS=50`, `DRIFT_THRESHOLD=0.5`.

1. `end = floor(now, WINDOW_MINUTES)`, `start = end - WINDOW_MINUTES`; the window is `[start, end)` on `received_at`.
2. Versions = the distinct `model_version`s of `ok` non-reference rows in the window, plus the version of the latest `ok` non-reference row ever.
3. Per version, load the current rows and the reference rows (the ten columns, `source_id`, `mask`):
   - no reference row → drift `insufficient_data`, reason `no_reference`;
   - either side below `MIN_OBSERVATIONS` → `few_observations`;
   - otherwise Evidently on the ten columns: `mean_r`, `mean_g`, `mean_b`, `brightness`, `share_bareland`, `share_rangeland`, `share_tree`, `share_water`, `share_agriculture`, `share_building`.
4. Quality per version:
   - join the current rows to `serving.labels` on `source_id`;
   - decode each prediction mask with `rasterio.MemoryFile`;
   - sum `models.confusion` over the labelled rows, then `models.scores`;
   - fewer than `MIN_OBSERVATIONS` labelled rows → `few_observations`; a `ValueError` from `scores` → `incomplete_labels`.
5. Freshness: `max(received_at)` of `ok` non-reference rows.
6. Build a fresh `CollectorRegistry` and `push_to_gateway(PUSHGATEWAY_URL, job="landcover-drift", registry=…)`. Any exception exits non-zero.

The six scored classes are the ten columns' prediction part because `developed` and `road` have zero reference variance. Their normed distance would divide by 0.001 and jump to hundreds on a single predicted pixel. The scored set is also the one quality can measure.

`DataDriftPreset`'s dataset-level flag (`drift_share` 0.5) is not published. The drifted count and share at `DRIFT_THRESHOLD` are.

Alternatives:
- Two presets, one for inputs and one for shares. Rejected: one threshold and one column list are simpler, and the per-column series already separate the two.
- Mean share difference in percentage points for prediction drift (Section 6.6 before this change). Rejected with the author: its no-shift p95 is 15.6 points against a 10-point rule.

### 7. Published metrics

One group, `job="landcover-drift"`, replaced on every run:

| Metric | Labels | Meaning |
|---|---|---|
| `landcover_drift_distance` | `model_version`, `column` | normed Wasserstein of the column |
| `landcover_drift_columns_drifted` | `model_version` | columns with distance ≥ threshold |
| `landcover_drift_columns_share` | `model_version` | that count over 10 |
| `landcover_drift_threshold` | — | `DRIFT_THRESHOLD`, for the dashboard line |
| `landcover_report_observations` | `model_version`, `side` (`current`, `reference`, `labelled`) | sample sizes |
| `landcover_report_insufficient` | `model_version`, `signal` (`drift`, `quality`), `reason` | 1 when the signal has no value |
| `landcover_quality_miou` | `model_version` | mean IoU over the six scored classes |
| `landcover_report_window_end_seconds` | — | end of the window, Unix time |
| `landcover_latest_request_seconds` | — | `received_at` of the latest served non-reference request |

The Pushgateway adds `push_time_seconds{job="landcover-drift"}`. Data age on the dashboard is `time() - landcover_latest_request_seconds` and job age is `time() - push_time_seconds`. The alert rule on data age is `add-lab4-drift-alert`'s.

Alternative: a grouping key per model version. Rejected: a version that leaves the traffic would keep its last values until someone deletes its group.

### 8. Monitoring objects

Appended to `k8s/landcover.yaml`; the three generated ConfigMaps are created in `cluster.sh` like `postgres-init`.

| Object | Image | Memory request / limit | Notes |
|---|---|---|---|
| Deployment and Service `pushgateway:9091` | `prom/pushgateway:v1.11.4` | 32 / 64 Mi | readiness `GET /-/ready`; no persistence, so a restart empties it until the next run |
| Deployment and Service `prometheus:9090` | `prom/prometheus:v3.13.5` | 256 / 512 Mi | config from ConfigMap `prometheus` (`k8s/prometheus.yml`); `--storage.tsdb.retention.time=2d`; TSDB on an `emptyDir`; readiness `GET /-/ready` |
| Deployment and Service `grafana:3000` | `grafana/grafana:13.3.2` | 128 / 256 Mi | ConfigMaps `grafana-provisioning` (data source, dashboard provider) and `grafana-dashboards` (`landcover.json`); anonymous Viewer; readiness `GET /api/health` |
| CronJob `drift-report` | `landcover-monitor:COMMIT` | 512 Mi / 1 Gi | `*/5 * * * *`, `concurrencyPolicy: Forbid`, `startingDeadlineSeconds: 120`, `backoffLimit: 0`, history limits 3 and 3; `envFrom` ConfigMap `landcover`, `WAREHOUSE_DSN` from the Secret |

`k8s/prometheus.yml`: `scrape_interval: 15s`. Jobs `ml` (`ml:8000`), `llm` (`llm:8000`) and `pushgateway` (`pushgateway:9091`, `honor_labels: true`), all with `static_configs`.

`k8s/grafana/`:
- `datasource.yml`: Prometheus at `http://prometheus:9090`, uid `prometheus`;
- `dashboards.yml`: a file provider reading `/var/lib/grafana/dashboards`, `allowUiUpdates: false`;
- `landcover.json`: uid `landcover`.

Panels:
1. ML requests per second by `outcome`.
2. ML p95 latency from `landcover_request_seconds_bucket`.
3. ML error and invalid rate.
4. `landcover_drift_distance` per column with `landcover_drift_threshold`.
5. `landcover_drift_columns_share`.
6. `landcover_report_observations` per side.
7. `landcover_report_insufficient` per signal and reason.
8. `landcover_quality_miou`.
9. Data age and job age.

Memory: new requests 928 Mi and limits 1,856 Mi; expected steady use about 0.4 GiB plus the job's peak while it runs. Measured in task 5 and recorded in the README.

Alternative: kube-prometheus-stack. Rejected: it needs Helm and adds an operator, node-exporter and kube-state-metrics to a node with about 1.7 GiB left.

### 9. Job image and dependencies

- `pyproject.toml` gains a group `monitor`: `evidently==0.7.23` and `pandas==2.3.3`, with a comment that Evidently 0.7.23 does not import with pandas 3. The universal lock therefore holds pandas 2.3.3 for every group. No conflict entry is needed: `monitor` installs no torch.
- `docker/serve/Dockerfile` splits its first stage into `base` (Python, expat, uv, environment) and `deps` (`--group serve`). A new target `monitor` starts from `base`:
  - `uv sync --locked --no-dev --group monitor`;
  - copies the tree;
  - sets `IMAGE_COMMIT` and the revision label;
  - runs as the same non-root user;
  - runs `python -m landcover.monitor report`.
- `make images` loops over `ml llm monitor`.

Alternative: the ML image with Evidently added. Rejected: a 2.9 GB image with torch for a job that loads no model, and Evidently's 0.5 GB in every serving pod.

### 10. Bring-up

`scripts/cluster.sh`:
- creates ConfigMaps `prometheus`, `grafana-provisioning` and `grafana-dashboards` next to `postgres-init`;
- after `apply`, waits for `rollout status` of `pushgateway`, `prometheus` and `grafana`;
- after the ML smoke request, port-forwards `svc/postgres` to `127.0.0.1:5433`. `forward()` gains a TCP check for this port, because PostgreSQL does not answer HTTP;
- then runs `monitor reference` and `monitor labels` with `postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:5433/landcover`;
- before `kubectl get pods,svc`, prints the port-forward commands for Grafana (`3000`, dashboard `/d/landcover`) and Prometheus (`9090`).

The Makefile gains `replay` and `reference`, which pass the default local URLs. The README's demonstration starts the port-forwards by hand, as the Lab 4 cluster section does.

### 11. Tests

`tests/test_monitor.py`, in `make test`:
- `window(now)`: 12:10:20 → `[12:05, 12:10)`; 12:05:00 is the start of its own window;
- `quadrants()` of a 512×512 GeoTIFF gives four GeoTIFFs of 256×256 with the expected transforms and source IDs; `label_quadrants()` matches;
- the insufficient-data rule for counts and missing reference;
- quality on constructed masks equals `models.scores`, and a missing scored class gives `incomplete_labels`;
- the registry built from a report has the series of the table above, and a version absent from the report has none.

With `TEST_DSN`, a fresh database gets:
- version selection: rows in the window, a reference row excluded, the latest-version fallback;
- `labels` twice gives 64 rows (on fixture tiles).

With `--group monitor` (`pytest.importorskip("evidently")`):
- identical frames give distance 0 on every column;
- brightness shifted by two reference standard deviations crosses 0.5;
- the parser reads `ValueDrift` and `DriftedColumnsCount` from `dict()`.

### 12. Documents

README section "Lab 4: monitoring":
- what runs and the port-forwards;
- the reference and labels commands, and when to re-run `make reference` (after a promotion and restart);
- the two-window demonstration (`make replay`, wait one empty window, `make replay`) with timestamps;
- the dashboard screenshot `docs/screenshots/grafana-two-windows.png`;
- one pushed report (`curl -s 127.0.0.1:9091/metrics | grep landcover_`);
- the memory table of the new pods;
- `kubectl get pods,svc` and `kubectl get cronjob,jobs` with the monitoring components.

The pods-and-services block of "Lab 4: cluster" gets the new capture.

Scorecard row "Monitoring scheduled": the CronJob, the dashboard with two windows and the screenshot.

`docs/design.md` Section 6.6, and the local `docs/design.uk.md`:
- **Signal table.** The input-drift and prediction-drift rows use normed Wasserstein per column against reference observations. Prediction drift covers the six scored class shares. Thresholds are marked provisional until the drift-alert change.
- **Reference paragraph.** Reference observations replace the frozen histogram bins, produced by the served model version on the training quadrants through the endpoint.
- **New "Lab 4 monitoring" paragraph.** The 5-minute schedule and window, the minimum of 50, `insufficient_data` and its reasons, the labels of the development batch and the final batch as declared unlabelled, the pushed metrics, the freshness signal and the probe's numbers.
- **Planned Lab 4 demonstration.** Rewritten for 5-minute windows and quadrants.

## Risks / Trade-offs

- [pandas 2.3.3 instead of 3.1.1 breaks a Lab 2 or Lab 3 path through mlflow] → Task 1 runs `make test`, `make lint` and a registry round trip (`make cluster` seed and smoke) after the lock change, before anything else is built on it.
- [The random forest's bareland share already scores 0.53 on the unchanged held-out replay, above the provisional 0.5] → Expected from the probe: the held-out batches are other years and regions. The screenshot shows it as measured. Choosing per-signal thresholds is the first decision of `add-lab4-drift-alert`.
- [Evidently's result keys differ from what the parser expects] → Task 2.2 runs the Evidently test against the installed 0.7.23 before the job is wired; the parser fails loudly on a missing metric rather than publishing nothing.
- [The job's pod starts after its window boundary, for example after a node restart] → The window comes from the start time floored to 5 minutes. `startingDeadlineSeconds: 120` skips a run that is more than 2 minutes late instead of reporting the wrong window.
- [The smoke request and `make cluster`'s reference traffic fall into a window] → Reference rows are excluded by prefix. The one smoke tile is a whole 512×512 tile in a window of its own and yields `few_observations`.
- [The node runs out of memory while the job and a 1024×1024 prediction peak together] → Limits are set from the probe and measured in task 5. If the measured headroom is below 0.5 GiB, the job's limit drops to 768 Mi, since it holds at most a few hundred rows.
- [Prometheus loses its data when its pod restarts (`emptyDir`)] → Accepted for a course cluster; the screenshot is taken while it runs, and the Pushgateway refills on the next run.
- [Evidently's normed Wasserstein divides by `max(std, 0.001)`] → The zero-variance classes are left out of the columns (Decision 6).

## Migration Plan

Nothing to migrate. The new table is created with `IF NOT EXISTS`. A running cluster gets everything from `make cluster` on the new commit: new images, the monitoring objects, the reference and the labels. `minikube delete` removes it all.

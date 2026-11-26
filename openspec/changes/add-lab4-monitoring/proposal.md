# Proposal

## Why

Lab 4 step 4 asks for three things. First, a scheduled job that compares a reference window (what the model was trained on) with the current window (what the services have seen). It must report input drift per feature, prediction drift and quality once labels arrive. Second, the drift numbers and the service metrics must reach a metrics store and a dashboard. Third, the dashboard must show two windows, captured in a screenshot. The cluster from `add-lab4-cluster` serves and logs every request, but it has no reference, no report, no Prometheus and no Grafana.

This is the third of four Lab 4 changes: `add-lab4-services` → `add-lab4-cluster` → `add-lab4-monitoring` → `add-lab4-drift-alert`. The proposal of `add-lab4-services` placed the reference in `add-lab4-drift-alert`. It moves here, because the dashboard of this change has to show a drift metric. The threshold justification, the injected shift, Alertmanager and the alert rules stay in `add-lab4-drift-alert`.

## What Changes

- **Reference through the serving path.** A host command sends the 256 training quadrants (256×256) of the four training batches to the ML service's `/predict`, each with `X-Source-Id: reference/<data version>/<batch>/<tile>/q<n>`. The rows land in `serving.predictions` with the model version and image commit that produced them. The reference therefore uses the same decoding, features, model and taxonomy as the traffic it is compared with. The command runs once per served model version and is skipped when that version already has its reference.
- **Labels for held-out quadrants.** A new table `serving.labels` holds the crosswalked masks of the 64 development quadrants (D017-2021), keyed by the source ID the replay sends. A host command fills it. The final batch (D073-2022) gets no labels, as a declared simulation of labels that have not arrived (design document Section 5.2).
- **Replay.** A host command sends the 128 held-out quadrants of the development and final batches to `/predict`, with source IDs. It starts at the next window boundary, so one replay falls into one window. `add-lab4-drift-alert` extends it with the shift.
- **Scheduled drift report.** A Kubernetes CronJob runs every 5 minutes over a 5-minute, non-overlapping window. For every model version seen in the window, or last seen in traffic, it compares the window's `ok` rows that are not reference rows with that version's reference rows. Evidently's `DataDriftPreset` with normed Wasserstein covers ten columns: the four input features and the six class shares that the labels can score. On labelled rows it computes mean IoU with the Lab 2 scoring code. A side with fewer than 50 observations, or a version without a reference, yields `insufficient_data` with its reason instead of a score.
- **Metrics to the Pushgateway.** Each run replaces one Pushgateway group with these metrics:
  - per-column drift scores and the drifted-column count and share;
  - the provisional threshold;
  - observation counts per side;
  - `insufficient_data` flags;
  - mean IoU;
  - the window end;
  - the time of the latest served request, which is the data freshness signal.
- **Monitoring stack in the cluster.** Plain manifests for Prometheus, the Pushgateway and Grafana. Prometheus scrapes `/metrics` of both services and the Pushgateway. Grafana loads its data source and one dashboard from files in Git and allows anonymous viewing.
- **Job image.** A third image target `monitor` in `docker/serve/Dockerfile`, without torch, with a new dependency group `monitor` (`evidently==0.7.23`). Evidently 0.7.23 fails to import with pandas 3, so the lock moves pandas from 3.1.1 to 2.x for the whole project. pandas is used only through mlflow.
- **Bring-up.** `make cluster` also builds the job image, deploys the monitoring stack, builds the reference for the served version and loads the labels. It prints the Grafana and Prometheus port-forwards.
- **Evidence.** The README gets a section "Lab 4: monitoring":
  - the commands;
  - the two-window demonstration: an unchanged replay, one empty window, the same replay again;
  - the dashboard screenshot;
  - one report's pushed metrics;
  - the measured memory of the new pods;
  - `kubectl get pods,svc` with the monitoring components ready.

  The scorecard row "Monitoring scheduled" is added.
- **Design document.** Section 6.6 names the metrics computed, the test, the schedule, the window, the reference and the labels. The PSI and "10 percentage points" rules give way to normed Wasserstein, for the product as well. The Section 6.1 topology diagram is redrawn once, in `add-lab4-drift-alert`, when Alertmanager completes the cluster.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| Reference | The 256 training quadrants of D080-2017, D033-2018, D065-2019 and D045-2020 go through the ML service with `reference/…` source IDs. Their log rows, grouped by model version, are the reference. Each newly served version needs the command once; until then its report says `no_reference`. `features.tile_features` is not used: it holds whole tiles on 0–1 over all pixels and label shares rather than predictions, and the cluster's warehouse does not fill it |
| Test | One `DataDriftPreset(method="wasserstein")`, scores in units of the reference standard deviation. The probe without a shift gave KS a 34–42% false-alarm rate (quadrants of one tile are correlated) and PSI above 0.25 in 65% of no-shift splits; Evidently's PSI cannot take frozen bins. Provisional threshold `DRIFT_THRESHOLD=0.5` (no-shift p95 0.45). The final value, its paragraph and the feature to alert on belong to `add-lab4-drift-alert`. Section 6.6 replaces PSI and the 10-point rule with this test |
| Quality | `serving.labels` with the 64 development quadrants. The job computes mean IoU on labelled rows of the window with `models.confusion` and `models.scores`. Final quadrants stay unlabelled as a declared simulation |
| Two windows | An unchanged replay of the 128 held-out quadrants, one empty window, then the same replay. The screenshot shows two equal drift segments with a gap, `insufficient_data` in between, two request bursts, latency, errors, mean IoU and data age |

Proposed in exploration and taken without objection:

| Topic | Default | Reason |
|---|---|---|
| Schedule and window | CronJob `*/5 * * * *`, `concurrencyPolicy: Forbid`, window = the 5 minutes before the start time floored to 5 minutes. At least 50 observations per side. The daily seven-day window stays the product rule in Section 6.6 | The lab asks for a job every few minutes; "a few hundred requests per window" fit in 5 minutes |
| Pushgateway | One group `job=landcover-drift`, replaced with PUT on every run; the model version is a metric label | A version that leaves the traffic disappears on the next push; the Pushgateway never forgets a group on its own |
| Freshness | The job pushes the time of the latest served request; the Pushgateway adds `push_time_seconds` per group | The lab's note "a green job is not a fresh table": data age and job age are separate signals. The alert rule is `add-lab4-drift-alert`'s |
| Stack | Plain manifests: `prom/prometheus:v3.13.5` (LTS) with static targets, `prom/pushgateway:v1.11.4`, `grafana/grafana:13.3.2` with provisioned data source and dashboard | No Helm on the machine. kube-prometheus-stack adds an operator, node-exporter and kube-state-metrics to a node with about 1.7 GiB left |
| Job image | Third target `monitor`, group `monitor`, no torch | The job needs Evidently but not torch or the model. The ML image is 2.9 GB |
| Specifications | New course capabilities `drift-reports` and `metrics-dashboard`. Requirements added to `cluster-bringup`. `segmentation-monitoring` keeps its product wording | Same split as the earlier Lab 4 changes |

## Capabilities

### New Capabilities

- `drift-reports`: the scheduled comparison of the served window with the training reference, which covers:
  - building the reference and loading labels;
  - the windows and the replay;
  - the drift, prediction-drift and quality signals;
  - insufficient data;
  - the pushed metrics with freshness.
- `metrics-dashboard`: Prometheus, the Pushgateway and Grafana in the cluster: what is scraped, how the dashboard is provisioned from Git, and what it shows.

### Modified Capabilities

- `cluster-bringup` (added by `add-lab4-cluster`, not yet archived): adds requirements for the monitoring components, the reference and the labels on bring-up, and the port-forwards printed at the end. Existing requirements are unchanged.

## Impact

- New files:
  - `src/landcover/monitor.py`: quadrants, replay, reference, labels and the report job;
  - `tests/test_monitor.py`;
  - `k8s/prometheus.yml`;
  - `k8s/grafana/` (data source, dashboard provider, `landcover.json`).
- Changed files:
  - `k8s/landcover.yaml` (the Prometheus, Pushgateway and Grafana Deployments and Services, the CronJob);
  - `sql/serving.sql` (table `serving.labels`);
  - `pyproject.toml` and `uv.lock` (group `monitor`, pandas below 3);
  - `docker/serve/Dockerfile` (target `monitor`);
  - `Makefile` (`images` builds three targets; `replay`, `reference`);
  - `scripts/cluster.sh`;
  - `README.md`;
  - `docs/design.md`, Section 6.6, and the local, ignored `docs/design.uk.md`.
- Database: a new table `serving.labels`. Reference and replay rows are ordinary request-log rows told apart by `source_id`.
- Not edited:
  - the service code and its request contract;
  - Sections 5.1 and 6.8, so the retrieval index version stays;
  - `features.tile_features`;
  - the registry.
- Out of scope:
  - the final threshold and its justification, the injected shift, Badgers;
  - Alertmanager, alert rules and the email channel;
  - the stretch action;
  - the Section 6.1 topology diagram, and Sections 5.5, 6.3, 6.7, 6.9 and 7.3 beyond what earlier changes wrote;
  - the scorecard row "Drift signal reaches a human";
  - the `lab-4` tag.

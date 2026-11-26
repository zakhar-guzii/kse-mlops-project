# Design

## Context

See proposal.md for the motivation and the decision tables, and the three specifications under `specs/` for the required behaviour. Current state that shapes the approach:

- **Report job (`add-lab4-monitoring`).**
  - The job replaces the Pushgateway group `job="landcover-drift"` every 5 minutes.
  - `landcover_drift_distance{model_version, column}` exists only for a version with a value. An `insufficient_data` version publishes no distance.
  - `landcover_drift_threshold` carries `DRIFT_THRESHOLD`, set to `"0.5"` in the CronJob's environment in `k8s/landcover.yaml`.
  - `landcover_latest_request_seconds` is published only once a non-reference request exists.
  - Prometheus scrapes the Pushgateway with `honor_labels: true`.
- **Replay.**
  - `monitor.replay(ml, batches, prefix, wait)` sleeps until the next 5-minute boundary plus 5 s.
  - It then posts the 128 held-out quadrants in batch, tile and quadrant order, built by `quadrants()` as 4-band GeoTIFFs. Band 4 carries colour interpretation `alpha`, so the service's valid-pixel mask comes from it.
  - Labels are keyed by `replay/D017-2021/<tile>/q<n>`.
- **ML service metrics.**
  - `landcover_requests_total{endpoint, outcome, model_version}` has outcomes `ok`, `invalid`, `error` and `unavailable`.
  - `landcover_model_loaded` is 1 once the model is loaded.
  - Prometheus scrapes the ML service through its Service, which lists only ready pods. A pod that has not loaded its model is not ready, so the series `landcover_model_loaded == 0` never reaches Prometheus. A missing model shows as `up{job="ml"} == 0`.
- **Prometheus deployment.**
  - The Deployment mounts the whole ConfigMap `prometheus` at `/etc/prometheus`.
  - It does not reload when the ConfigMap changes, and `scripts/cluster.sh` never restarts it.
- **Probe without the cluster.** The read-only probe used the service's `decode` and `observe`, the saved `rf-a8b3295` and `unet-c1f77a3`, 256 reference quadrants and 128 held-out ones. Brightness distances:

  | Traffic | Brightness distance |
  |---|---|
  | Unchanged held-out | 0.322 on both models |
  | No-shift halves of the training tiles, 2,000 splits | median 0.22, p95 0.435; P(≥ 0.5) = 1.9%, P(≥ 0.6) = 0.3% |
  | One training batch against the others | D080 0.31, D045 0.31, D033 0.70, D065 1.59 |
  | Darkening ×0.5 of 50% of held-out (50 seeds) | 0.574–0.62 |
  | Darkening ×0.7 or ×0.8 of 30% | 0.14–0.22, below the unchanged value |
  | Brightening ×1.5 of 30% | 0.62–0.66 |

  The held-out mean brightness is 132.6 against 123.0 for the reference, +0.24 standard deviations. A partial darkening first cancels that offset. Class-share columns reach 0.53 on unchanged held-out traffic: random forest bareland, and U-Net bareland, rangeland and building.
- **Versions** (Docker Hub, at least two weeks old on 2026-11-26):
  - `prom/alertmanager:v0.34.2` (2026-10-29); v0.35.0 got a patch release on 2026-11-24;
  - `axllent/mailpit:v1.33.1` (2026-11-07).
- **Alertmanager** (configuration reference):
  - `email_configs` needs `to`. `require_tls` defaults to `global.smtp_require_tls`, which is `true`. Without `auth_*` no authentication is attempted.
  - `send_resolved` defaults to `false` for email.
  - Routes default to `group_wait` 30 s, `group_interval` 5 m and `repeat_interval` 4 h.
- **Mailpit v1.33.1** (README and source):
  - SMTP on 1025, web UI and API on 8025;
  - `GET /api/v1/messages` lists messages, and `/livez` and `/readyz` are its health endpoints;
  - it keeps at most 500 messages by default;
  - without `--database` nothing is persisted across restarts.
- **Pushgateway** (README): it keeps groups without a TTL and recommends alerting on `push_time_seconds` lagging.

## Goals / Non-Goals

**Goals:**
- The shift, the crossing and the delivered email reproducible by a reviewer with `make cluster` and one demonstration command, in about 12 minutes.
- Every alert expression checked by `promtool` against synthetic series before it runs in the cluster.
- No change to the report job's metrics or to the service code.

**Non-Goals:**
- An external mailbox, a chat webhook, Grafana alerting or a latency alert.
- Silences, inhibition, more than one receiver or route.
- Persisting the mailbox or the alert state across pod restarts.
- The stretch action of Lab step 6.

## Decisions

### 1. Darkening inside the replay

`replay` gains `darken=None, fraction=0.5, seed=0`. The CLI gains `--darken FACTOR --fraction F --seed N`.

- The quadrant list keeps its fixed order. `np.random.default_rng(seed).permutation(n)[:round(fraction * n)]` picks the indices to darken, so the same seed always picks the same quadrants.
- `darken(body, factor)` reads the quadrant GeoTIFF:
  - it multiplies bands 1–3 by `factor`, rounds and clips to 0–255;
  - it leaves band 4 and the colour interpretation unchanged;
  - it writes the same profile.

  Validity therefore does not change: the service reads it from band 4.
- Darkened quadrants are sent as `shift/<batch>/<tile>/q<n>` and the rest as `replay/<batch>/<tile>/q<n>`. The output line adds `darkened 64 of 128 by 0.5 (seed 0)`.
- `make drift-demo` runs `replay`, then `replay --darken 0.5 --fraction 0.5 --seed 0`. The second waits for the next boundary, so the two fall into consecutive windows.

Alternatives:
- **Badgers.** Rejected (proposal): it covers tables only, and its scipy pin conflicts with the lock.
- **A separate shift script.** Rejected: it would duplicate the quadrants, the source IDs and the window wait.
- **`shift/` IDs for all 128 rows of the shifted run.** Rejected: the log would no longer tell which rows were darkened.

### 2. Alert rules

`k8s/alerts.yml`, one group `landcover`, evaluated every 15 s (`evaluation_interval: 15s` in `k8s/prometheus.yml`):

| Alert | Expression | `for` |
|---|---|---|
| `BrightnessDrift` | `landcover_drift_distance{job="landcover-drift",column="brightness"} >= on(job) group_left landcover_drift_threshold{job="landcover-drift"}` | 0s |
| `DataStale` | `time() - landcover_latest_request_seconds{job="landcover-drift"} > 3600` | 0s |
| `DriftReportStale` | `time() - push_time_seconds{job="landcover-drift"} > 300 or absent(push_time_seconds{job="landcover-drift"})` | 10m |
| `MLServiceUnavailable` | `up{job="ml"} == 0` | 5m |
| `PredictErrors` | `sum(c - (c offset 1h or c * 0)) >= 3`, where `c` is `landcover_requests_total{job="ml",endpoint="/predict",outcome="error"}` | 0s |

- **`BrightnessDrift` holds no state.** Its series lives exactly as long as the Pushgateway holds that window's report. The next PUT either brings a new value or none, and Prometheus marks the old series stale, so the alert resolves on its own. `for: 0s`, because a report holds one value for its 5 minutes. An `insufficient_data` version publishes no distance and cannot fire it.
- **Annotations.**
  - `BrightnessDrift`: the model version, `{{ $value }}` and the threshold. The window end comes from the template function `query "landcover_report_window_end_seconds"`.
  - The other alerts: their value.

  Every rule has the label `severity: email`.
- **`DataStale`** is not combined with job freshness: `DriftReportStale` covers a stopped job. With the job running and nothing served, only `DataStale` fires, as the spec scenario requires.
- **`DriftReportStale`.** A healthy job pushes every 5 minutes, so the lag exceeds 300 s only for seconds per cycle. `for: 10m` turns that into "no push for 15 minutes", and a missing group into "absent for 10 minutes". A Pushgateway restart empties the group for at most one cycle, below the 10 minutes.
- **`MLServiceUnavailable` on `up`.** The Service hides an unready pod, so a scrape of `landcover_model_loaded` cannot see 0 (Context). During `rollout restart` the old pod serves until the new one is ready, so `up` stays 1.
- **`PredictErrors`** counts `error` only. `invalid` and `unavailable` are the client's input and the loading state. The service creates the `error` series at its first error with the value 1 and exposes no created timestamp, so `increase()` would miss that first error and fire on the fourth. The current count minus the count an hour ago, or 0 for a newer series, counts it. A restart of the same model version within the hour undercounts; a promotion changes `model_version` and starts a new series.

Alternatives:
- **A threshold literal in the rule.** Rejected: two copies of 0.5 (spec "One threshold value").
- **Alert on `landcover_drift_columns_share`.** Rejected (proposal): the unchanged baseline already has 1–3 drifted columns.
- **`for: 5m` on `BrightnessDrift`.** Rejected: the report value is constant for the window, so `for` would only delay the email by one window.

### 3. Alertmanager and the mailbox

`k8s/alertmanager.yml`:

```yaml
route:
  receiver: operator-email
  group_by: [alertname, model_version]
receivers:
  - name: operator-email
    email_configs:
      - to: operator@landcover.local
        from: alertmanager@landcover.local
        smarthost: mailpit:1025
        require_tls: false
```

Timings and `send_resolved` keep their defaults:
- 30 s `group_wait`;
- 4 h repeat;
- no resolved email.

That gives one email per incident, as Section 6.6 already states. The default email template lists the alert's labels and annotations.

Objects appended to `k8s/landcover.yaml`:

| Object | Image | Memory request / limit | Notes |
|---|---|---|---|
| Deployment and Service `alertmanager:9093` | `prom/alertmanager:v0.34.2` | 32 / 64 Mi | ConfigMap `alertmanager` at `/etc/alertmanager`; `--storage.path` on an `emptyDir`; readiness `GET /-/ready` |
| Deployment and Service `mailpit` (ports 1025 and 8025) | `axllent/mailpit:v1.33.1` | 32 / 128 Mi | readiness `GET /readyz` on 8025; no database, so a restart empties the mailbox |

`k8s/prometheus.yml` gains:
- `evaluation_interval: 15s`;
- `rule_files: [/etc/prometheus/alerts.yml]`;
- `alerting.alertmanagers[].static_configs: [{targets: [alertmanager:9093]}]`.

`alerts.yml` goes into the same ConfigMap `prometheus` as a second key, so the existing mount picks it up.

The limits are first values. Task 3 measures `memory.peak` and adjusts them like Grafana's in `add-lab4-monitoring`.

Alternatives:
- **Grafana alerting.** Rejected: it would split the rules between Grafana's database and Prometheus. Alertmanager is the design's router (Section 6.6).
- **A chat webhook or a real SMTP server.** Rejected (proposal): either needs a secret the reviewer lacks. The `segmentation-monitoring` spec names email.

### 4. Reloading changed configuration

`scripts/cluster.sh` computes `sha256` over `k8s/prometheus.yml` and `k8s/alerts.yml`, and separately over `k8s/alertmanager.yml`. It substitutes the results for the placeholders `PROMETHEUS_CONFIG` and `ALERTMANAGER_CONFIG` in the pod template annotation `landcover/config`, as it already does for `COMMIT`.

- A changed file changes the template, and `apply` rolls out a new pod that reads the new configuration.
- An unchanged file leaves the template alone. A repeated bring-up therefore changes nothing, and the mailbox keeps its emails.

Alternative: `--web.enable-lifecycle` and `POST /-/reload` after apply. Rejected: it adds a write endpoint to Prometheus and a step that has to wait until the kubelet has synced the ConfigMap volume, which can take a minute.

### 5. Bring-up

`scripts/cluster.sh`:
- creates ConfigMap `prometheus` from both files and ConfigMap `alertmanager`;
- substitutes the two hashes;
- adds `alertmanager` and `mailpit` to the `rollout status` loop;
- prints `mailbox: minikube kubectl -- port-forward svc/mailpit 8025:8025, then http://127.0.0.1:8025`.

### 6. Checking the rules before the cluster

`k8s/alerts_test.yml` is a `promtool test rules` file with synthetic series:
- `BrightnessDrift` fires at 0.62 with threshold 0.5;
- it does not fire at 0.32, nor on a share column at 0.53;
- it resolves when the series ends;
- `DataStale` fires at 3,601 s of data age while pushes continue;
- `DriftReportStale` fires after 15 minutes without a push;
- `PredictErrors` ignores `invalid`.

It runs with the Prometheus image's own `promtool`, which needs nothing on the host:

```sh
docker run --rm -v "$PWD/k8s:/k8s" --entrypoint promtool prom/prometheus:v3.13.5 test rules /k8s/alerts_test.yml
```

`amtool check-config` from the Alertmanager image checks `k8s/alertmanager.yml` the same way. Both commands go into the README.

The darkening logic gets tests in `tests/test_monitor.py`, in `make test`:
- a darkened fixture quadrant has bands 1–3 scaled and the same `read_masks`;
- the same seed picks the same 64 indices;
- the source IDs split into `shift/` and `replay/`.

Alternative: CI runs promtool. Rejected: the lint workflow has no Docker step, and the rules change rarely.

### 7. Measurements for Section 7.3

`scripts/bench.py`, next to `scripts/smoke.py`, uses only the standard library and rasterio. It takes the port-forwarded URLs and reports four things:

- **`/predict`.** For each input size it sends 5 warm-up and 30 measured requests and records p50, p95 and throughput as completed requests per second. The three sizes:
  - a 256×256 quadrant;
  - a 512×512 tile;
  - a 1024×1024 mosaic of four development tiles built in memory.

  The method follows Section 6.3, at the course's input ceiling.
- **Concurrency.** The 512 run is repeated with 2 concurrent clients. Throughput stays one request at a time, the service lock of Section 6.3.
- **`/ask`.** It sends the first 10 questions of `eval/questions.toml` when `make llm-server` runs.
- **Memory.** `memory.peak` of each pod comes from `kubectl exec … cat /sys/fs/cgroup/memory.peak`, as the earlier memory tables were taken.

The requests carry `X-Source-Id: bench/…`. They count as served traffic, so the bench runs outside the demonstration windows. The README states that.

Alternatives:
- **Locust.** Rejected: one service with one lock; sequential timing gives the same p50 and p95 without a new dependency.
- **The Prometheus histogram alone.** Rejected: its buckets (0.05–10 s) are too coarse for p50. The bench cross-checks p95 against `histogram_quantile` and reports both.

### 8. Documents

**README, new section "Lab 4: drift alert":**
- the shift and the probe table;
- `make drift-demo` with its output;
- the report lines of both windows;
- the Grafana screenshot `docs/screenshots/grafana-drift-alert.png` showing the crossing;
- the Mailpit screenshot `docs/screenshots/mailpit-drift-alert.png` and `curl -s 127.0.0.1:8025/api/v1/messages` output;
- the timeline: replay start, window end, job finish, alert active in Prometheus, email received;
- the rule table and the `promtool` and `amtool` commands;
- the memory of the two new pods.

The scorecard gains "Drift signal reaches a human". "Monitoring scheduled" and "One command" get the alerting components and the new cold duration. The pods-and-services capture is replaced.

**`docs/design.md`**, and the local `docs/design.uk.md`:

| Section | Change |
|---|---|
| 5.5 | The course operator's mailbox. The first ten minutes after a drift email: open the report window on the dashboard, check the source mix and the shifted column, check `insufficient_data` and data age, keep the model serving, record the decision or request labelled controls. Retraining stays triggered by the operator; a schedule or a continuous trigger would need labels the system does not have (Appendix 2 questions 13 and 14) |
| 6.1 | Figure 3, the first draft, is replaced by `diagrams/lab4-cluster.svg`, the Minikube topology of Appendix 3 with this system's names. `diagrams/lab4-drift-loop.svg` is added. Both are hand-written SVGs in the style of `lab3-retrieval.svg` |
| 6.3 | The deployed measurements, with a pointer to 7.3. A switch to batch serving would change the monitoring unit from requests to batch runs (question 7) |
| 6.6 | Final threshold 0.5 on brightness and its paragraph: consumer, 1.9% accepted false alarms, cost of a false alarm against a miss, the probe numbers, new regions such as D033 firing on purpose, and the darkening blind spot. The channel and the rule table (Decision 2); readiness does not test a prediction, so `PredictErrors` catches a healthy service that fails (question 4). The injected shift is covariate shift; label shift is visible only as prediction drift; concept drift needs labels (question 8). Labels arriving late: the dashboard shows drift and `insufficient_data` for quality (question 9). A weekly pattern means the reference lacks that season or day, fixed by the reference rather than the threshold (question 10). PSI, KS and Wasserstein, and where Wasserstein fails: zero-variance classes and offsets that cancel (question 11). The demonstration as run. A sentence that the Section 6.8 example predates this rule |
| 6.7 | Alertmanager and Mailpit cost $0 and their measured memory; the cloud path keeps SES |
| 6.9 | The darkening row gets the measured detection and the blind spot |
| 7.3 | Renamed "Performance benchmarks". The bench table, pod memory, and three causes of a doubled p95 with the metric for each: CPU (`process_cpu_seconds_total`), memory pressure (`process_resident_memory_bytes`), input size or model version (request log) (question 20) |
| 7.4 | Lab 4 in the past tense |

Sections 5.1 and 6.8 stay unedited, so the retrieval index version stays `5570e99ba60e`. Appendix 2 questions 1, 2, 5 and 19 are answered from the repository at the defence and add no text.

## Risks / Trade-offs

- [Alertmanager refuses plain SMTP to a non-local host] → Task 1.1 sends a test alert through `amtool alert add` before anything else is built on the channel. Fallback: Mailpit's `--smtp-auth-accept-any` with STARTTLS. If that fails as well, a webhook receiver pointing at a small in-cluster receiver whose log is the evidence. The proposal is revisited only in that last case.
- [Mailpit loses its mailbox when its pod restarts] → The README keeps the screenshot and the API output. Decision 4 keeps a repeated bring-up from restarting it.
- [`DataStale` fires on every idle cluster after an hour, and repeats every 4 hours] → Intended: the README says so. Section 6.6 explains that the course has no steady traffic.
- [The shifted value 0.574–0.62 sits close to the threshold] → The fixed seed gives one deterministic value. The README records it, and the margin over the threshold is stated. The second replay of the same seed reproduces it.
- [On the author's U-Net, the class shares of the shifted window also cross] → Expected. The alert watches brightness only, and the email names the column.
- [A changed `prometheus.yml` restarts Prometheus and empties its `emptyDir`] → Accepted as in `add-lab4-monitoring`. The demonstration runs after the last configuration change.
- [The bench's requests enter a report window] → They carry `bench/` IDs, and the bench runs outside the demonstration windows.
- [Memory: two more pods on a node with about 1.5 GiB left] → Limits of 64 and 128 Mi, measured in task 3. Grafana's limit stays at 768 Mi.

## Migration Plan

Nothing to migrate. `make cluster` on the new commit adds the two Deployments, rolls Prometheus once for its new configuration and leaves the rest. `minikube delete` removes everything.

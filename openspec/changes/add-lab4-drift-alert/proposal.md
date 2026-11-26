# Proposal

## Why

Lab 4 step 5 requires a deliberate shift injected through the prediction endpoint, a drift metric that crosses a justified threshold, and an alert that reaches a human channel, shown as received in the README. Step 1 requires the design document to name the metrics, thresholds, schedule and channel, to show the real cluster topology and to fill Section 7.3 from the deployed services. Step 8 adds the last Lab 4 scorecard row and the `lab-4` tag. `add-lab4-monitoring` reports drift every 5 minutes with a provisional threshold of 0.5. It has no alert rules, no Alertmanager and no way to inject a shift.

This is the last of four Lab 4 changes: `add-lab4-services` → `add-lab4-cluster` → `add-lab4-monitoring` → `add-lab4-drift-alert`.

## What Changes

- **Shifted replay.** `python -m landcover.monitor replay` gains a darkening option. With a fixed seed it picks a recorded fraction of the 128 held-out quadrants. It multiplies their red, green and blue bands by a recorded factor before `/predict` and leaves the fourth band, which holds the validity mask, unchanged. Darkened quadrants are sent as `shift/<batch>/<tile>/q<n>` and the others as `replay/…`, so the request log shows which rows were shifted. `make drift-demo` sends one unchanged window and then a shifted window: 64 of 128 quadrants at factor 0.5, seed 0.
- **Alerting in the cluster.** New Deployments and Services:
  - Alertmanager, `prom/alertmanager:v0.34.2`;
  - Mailpit, `axllent/mailpit:v1.33.1`, an in-cluster SMTP server with a mailbox and a web UI, needing no secret and no external account.

  Prometheus loads alert rules from `k8s/alerts.yml` and sends alerts to Alertmanager. Alertmanager has one route and emails every alert to the operator's mailbox in Mailpit.
- **Alert rules.**

  | Rule | Fires when | Source |
  |---|---|---|
  | `BrightnessDrift` | the brightness distance ≥ the pushed threshold | Lab step 5 |
  | `DataStale` | no request served for 1 h | Lab Notes ("alert on the data") |
  | `DriftReportStale` | no report pushed for 15 min | Pushgateway README |
  | `MLServiceUnavailable` | the ML service has no ready pod for 5 min, for example because its model is missing | §6.6 service health |
  | `PredictErrors` | 3 or more prediction errors in 1 h | §6.6 job failures |

- **Threshold.** `DRIFT_THRESHOLD` stays 0.5 and becomes final. The alert watches the brightness column only; it does not use the share of drifted columns. The Section 6.6 paragraph states:
  - the consumer;
  - the accepted false-alarm rate (1.9% of no-shift reports);
  - the cost of a false alarm and of a miss;
  - the probe numbers;
  - the blind spot: darkening up to 30% of a window is not seen.
- **Bring-up.** `make cluster` also deploys Alertmanager and Mailpit, creates their ConfigMaps, waits for both and prints the mailbox port-forward.
- **Evidence in the README.** A section "Lab 4: drift alert":
  - the shift and its fraction;
  - the two windows' reports;
  - the dashboard screenshot with the crossing;
  - the received email (screenshot of Mailpit and the API output);
  - the alert timeline.

  The scorecard gains the row "Drift signal reaches a human". The rows "Monitoring scheduled" and "One command" are updated, and the cold bring-up is measured again at the final commit.
- **Section 7.3 measurements.** A new `scripts/bench.py` measures:
  - p50, p95 and throughput of `/predict` at 256, 512 and 1024 pixels;
  - 10 `/ask` requests;
  - `memory.peak` of every pod.
- **Design document.**
  - **5.5:** the course mailbox and the operator's first ten minutes; retraining stays operator-triggered.
  - **6.1:** two new diagrams. The cluster topology replaces the first-draft deployment figure; the drift-to-action loop follows Appendix 3.
  - **6.3:** the deployed measurements.
  - **6.6:**
    - the final threshold and its paragraph;
    - the channel and the rule table;
    - the shift kinds the monitoring sees and does not see;
    - the demonstration;
    - a note that the Section 6.8 example predates the Wasserstein rule.
  - **6.7:** the cost of alerting.
  - **6.9:** the measured blind spot.
  - **7.3:** filled.
  - **7.4:** Lab 4 done.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| Stretch (Lab step 6) | Not built. An alert never starts training, promotion or rollback. The drift loop diagram shows the operator's manual action |

Proposed from the Lab 4 text, the design document and the specifications, and accepted by the author without objection:

| Topic | Default | Reason |
|---|---|---|
| Shift | Darken bands 1–3 by 0.5 in 64 of 128 held-out quadrants (seed 0), with numpy in the replay | §6.9 and the earlier §6.6 plan name darkening by a recorded fraction and factor. The probe crossed on all 50 seeds (minimum 0.574) |
| Badgers | Not used | Its generators take tables only, so shifting features would bypass the service. Its pin `scipy~=1.17` conflicts with the locked 1.18.1. The lab accepts a one-line shift |
| What the alert watches | The brightness distance, not the share of drifted columns | The class-share columns already reach 0.53 on unchanged held-out traffic. Brightness does not depend on the model, so the rule behaves the same on the reviewer's random forest and on the author's U-Net |
| Threshold | 0.5 | Unchanged held-out traffic gives 0.322 and no-shift splits give p95 0.435. The chosen shift gives at least 0.574 |
| Channel | Email through Alertmanager to Mailpit in the cluster | The `segmentation-monitoring` spec names email. One command must work without a secret the reviewer lacks |
| Section 6.8 | Not edited; a sentence in 6.6 points out its PSI example | Sections 5.1 and 6.8 are in the retrieval corpus, and Lab 3's evidence uses index `5570e99ba60e` |
| Shifted window quality | `few_observations` | Darkened rows carry `shift/` IDs without labels: the spec scenario "No labels for a shifted population" |
| Appendix 2 | Gaps answered inside the revised sections, not in a separate file | The required sections already cover them |

## Capabilities

### New Capabilities

- `drift-alerting`: alert rules over the drift report, data freshness and service health; routing through Alertmanager; delivery to the operator's mailbox; the delivered alert as evidence.

### Modified Capabilities

- `drift-reports` (added by `add-lab4-monitoring`, not yet archived): adds the shifted replay. Existing requirements are unchanged.
- `cluster-bringup` (added by `add-lab4-cluster`, not yet archived): adds Alertmanager and the mailbox to the bring-up. Existing requirements are unchanged.

`segmentation-monitoring` keeps its product wording. Its scenario "Inject an input shift through the prediction endpoint" is what this change demonstrates.

## Impact

- **New files:**
  - `k8s/alerts.yml` (Prometheus rules) and `k8s/alerts_test.yml` (its `promtool` test);
  - `k8s/alertmanager.yml`;
  - `scripts/bench.py` (Section 7.3 measurements);
  - `docs/diagrams/lab4-cluster.svg`;
  - `docs/diagrams/lab4-drift-loop.svg`;
  - `docs/screenshots/` (the crossing and the received email).
- **Changed files:**
  - `src/landcover/monitor.py`: the darkening in `replay`;
  - `tests/test_monitor.py`;
  - `k8s/prometheus.yml`: `rule_files`, `alerting`;
  - `k8s/landcover.yaml`: Alertmanager and Mailpit, rules mounted in Prometheus;
  - `scripts/cluster.sh`;
  - `Makefile`: `drift-demo`;
  - `README.md`;
  - `docs/design.md`: Sections 5.5, 6.1, 6.3, 6.6, 6.7, 6.9, 7.3, 7.4;
  - the local, ignored `docs/design.uk.md`.
- **Not edited:**
  - the service code and its request contract;
  - the report job's metric names;
  - Sections 5.1 and 6.8, `retrieval.toml` and `prompts/`, so the retrieval index version stays;
  - the registry.
- **Out of scope:**
  - the stretch action;
  - a real external mailbox or chat webhook;
  - Grafana alerting;
  - a latency alert;
  - the dark-image warning threshold `DARK_BRIGHTNESS`, which stays unset;
  - archiving the four Lab 4 changes, which happens after the whole lab.

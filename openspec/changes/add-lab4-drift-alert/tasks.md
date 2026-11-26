# Tasks

Follow [design.md](design.md) and the three specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`.

Out of scope:
- the stretch action of Lab step 6;
- an external mailbox or chat webhook;
- Grafana alerting and a latency alert;
- `DARK_BRIGHTNESS`;
- edits to `serve_ml.py`, `serve_llm.py` and the report job's metric names;
- edits to Sections 5.1 and 6.8, `retrieval.toml` or `prompts/`;
- licence checks.

`make images`, `make cluster` and the `lab-4` tag need a committed tree. Before each step that runs them, ask the author to commit or approve the commit.

## 1. Alert channel

- [ ] 1.1 Prove the channel first (design Decision 3, first risk). Add:
  - `k8s/alertmanager.yml`;
  - the Alertmanager and Mailpit Deployments and Services in `k8s/landcover.yaml`;
  - ConfigMap `alertmanager`.

  Verify:
  - `docker run --rm -v "$PWD/k8s:/k8s" --entrypoint amtool prom/alertmanager:v0.34.2 check-config /k8s/alertmanager.yml` passes;
  - after apply, both pods are ready;
  - with port-forwards on 9093 and 8025, `amtool alert add test severity=email --alertmanager.url=http://127.0.0.1:9093` leads within a minute to one message in `curl -s 127.0.0.1:8025/api/v1/messages`, sent to `operator@landcover.local`.

  If plain SMTP is refused, apply the fallbacks of design Risks in order and record which one worked.
- [ ] 1.2 Add the configuration-hash annotations and the bring-up steps (design Decisions 4 and 5) to `scripts/cluster.sh` and `k8s/landcover.yaml`. Verify:
  - `make cluster` exits 0, waits for `alertmanager` and `mailpit` and prints the mailbox port-forward;
  - a second `make cluster` on the same commit leaves the Prometheus, Alertmanager and Mailpit pods with the same names and ages, and the test email from 1.1 is still in the mailbox;
  - a change to `k8s/alertmanager.yml` alone rolls only the Alertmanager pod.

## 2. Alert rules

- [ ] 2.1 Add `k8s/alerts.yml` with the five rules of design Decision 2 and `k8s/alerts_test.yml` with the cases of Decision 6. Add `evaluation_interval`, `rule_files` and `alerting` to `k8s/prometheus.yml`, and put `alerts.yml` into ConfigMap `prometheus`. Verify:
  - `docker run --rm -v "$PWD/k8s:/k8s" --entrypoint promtool prom/prometheus:v3.13.5 test rules /k8s/alerts_test.yml` passes;
  - `promtool check config` on `k8s/prometheus.yml` (mounted together with `alerts.yml`) passes;
  - after `make cluster`, `curl -s 127.0.0.1:9090/api/v1/rules` lists the five rules with health `ok`, and `/api/v1/alertmanagers` shows `alertmanager:9093` active;
  - with the unchanged replay of `add-lab4-monitoring` in a window, `/api/v1/alerts` shows no `BrightnessDrift`.
- [ ] 2.2 Document the rules in the README: a section "Lab 4: drift alert" with the rule table, the channel, the two check commands and the mailbox port-forward. State that `DataStale` fires on an idle cluster after an hour. Verify that the two check commands run as written from a clean checkout.

## 3. Shifted replay and the demonstration

- [x] 3.1 Add the darkening, the seeded selection and the `shift/` source IDs to `replay`, plus the CLI options (design Decision 1). Add the tests of Decision 6 to `tests/test_monitor.py`. Verify:
  - `make test` and `make lint` pass;
  - on a fixture quadrant, the darkened bands 1–3 equal `rint(0.5 × original)` and `read_masks` is unchanged;
  - seed 0 picks the same 64 indices twice.
- [ ] 3.2 Add `make drift-demo` and run it against the cluster (champion version 2 on a reviewer cluster, version 3 on the author's). Verify:
  - two consecutive windows hold 128 `ok` rows each. `SELECT left(source_id, 6), count(*) FROM serving.predictions WHERE received_at >= <first window start> GROUP BY 1` gives 128 `replay` in the first window, and 64 `shift/` and 64 `replay` in the second;
  - the report logs give brightness 0.322 in the first window and at least 0.5 in the second, with quality `few_observations` in the second;
  - `BrightnessDrift` is active in Prometheus after the second report, and Mailpit holds its email within 10 minutes of the second window's start, naming the version, distance and threshold;
  - the alert is no longer active after the next report;
  - `champion` and the ML service's reported version are unchanged;
  - a second shifted replay with the same seed gives the same distances.
- [ ] 3.3 Add the evidence to "Lab 4: drift alert" (design Decision 8):
  - the shift and the probe table;
  - the `make drift-demo` output;
  - both report lines;
  - the Grafana screenshot `docs/screenshots/grafana-drift-alert.png` with the crossing;
  - the Mailpit screenshot `docs/screenshots/mailpit-drift-alert.png` and the API output;
  - the timeline with times;
  - the memory of the Alertmanager and Mailpit pods (`memory.peak`), with their limits adjusted if the measurement calls for it.

  Verify that every command in the section runs as written and the images render on GitHub.

## 4. Section 7.3 measurements

- [ ] 4.1 Add `scripts/bench.py` (design Decision 7) and run it outside any demonstration window, with `make llm-server` running. Verify that it prints:
  - p50, p95 and throughput for 256, 512 and 1024 pixels;
  - the 2-client run at 512;
  - p50 and p95 for 10 `/ask` requests;
  - p95 next to `histogram_quantile(0.95, …)` from Prometheus.

  Collect `memory.peak` of every pod and add the bench command and its output to the README, with a pointer to Section 7.3.

## 5. Design document

- [ ] 5.1 Draw `docs/diagrams/lab4-cluster.svg` (Appendix 3 Minikube topology with this system's components) and `docs/diagrams/lab4-drift-loop.svg` (Appendix 3 drift-to-action loop: shift, endpoint, request log, CronJob, Pushgateway, Prometheus rule, Alertmanager, Mailpit, operator, and the operator's manual promotion or rollback), in the style of `docs/diagrams/lab3-retrieval.svg` with `<title>` and `<desc>`. Verify both render in a browser and in the GitHub preview, and that every name in them exists in `k8s/landcover.yaml` or the README.
- [ ] 5.2 Revise Sections 5.5, 6.1 (Figure 3 replaced by the topology, the loop added), 6.3, 6.6, 6.7, 6.9, 7.3 and 7.4 as listed in design Decision 8, in `docs/design.md` and the local `docs/design.uk.md`. Verify:
  - Section 6.6 names the metrics, the threshold 0.5 on brightness with its paragraph (consumer, false-alarm rate, cost of a false alarm and of a miss), the schedule, the rules and the mailbox;
  - Appendix 2 questions 4, 7–11, 13, 14, 16 and 20 each have their answer in the section the design table names;
  - `git diff` leaves Sections 5.1 and 6.8 untouched, and the retrieval index Job at the new commit reports index version `5570e99ba60e`;
  - every number in the revised sections matches the README or the probe in design Context.

## 6. Scorecard, bring-up and integration

- [ ] 6.1 Update the scorecard:
  - add "Drift signal reaches a human" (the shift, the crossing, the received email, with links);
  - extend "Monitoring scheduled" and "One command" with the alerting components;
  - replace the pods-and-services capture with one that includes `alertmanager` and `mailpit`.

  Verify that every link in the five Lab 4 rows resolves to a README section, file or image.
- [ ] 6.2 Cold bring-up on a clean clone at the final commit (`cp .env.example .env`, a new Minikube profile, no images). Verify:
  - `make cluster` exits 0, and the duration and the three slowest steps are recorded in the README's bring-up table and the "One command" row;
  - `make drift-demo` on that cluster delivers the drift email.
- [ ] 6.3 Integration check:
  - `openspec validate add-lab4-drift-alert --strict` passes;
  - `make lint` and `make test` pass;
  - the `promtool` and `amtool` checks pass;
  - the README's Lab 4 sections and Sections 5.5, 6.1, 6.3, 6.6, 6.7, 6.9, 7.3 and 7.4 agree on the threshold, the rules, the channel, the versions and the measured numbers.

  Then ask the author to approve the `lab-4` tag on that commit, and create it once approved.

## Workflow follow-up

- After the whole lab, archive the four Lab 4 changes in order: `add-lab4-services`, `add-lab4-cluster`, `add-lab4-monitoring`, `add-lab4-drift-alert`.

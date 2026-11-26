# Tasks

Follow [design.md](design.md) and the three specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`.

Out of scope for this change:
- the final threshold and its paragraph;
- the shifted replay and Badgers;
- Alertmanager, alert rules and the email channel;
- the Section 6.1 topology diagram.

These belong to `add-lab4-drift-alert`. Also out of scope:
- edits to `serve_ml.py` and `serve_llm.py`;
- edits to Sections 5.1 and 6.8, `retrieval.toml` or `prompts/`;
- archiving any change and adding licence checks.

`make images` and `make cluster` need a committed tree. Before each step that runs them, ask the author to commit or approve the commit.

## 1. Dependencies and image

- [x] 1.1 Add the group `monitor` (`evidently==0.7.23`, `pandas==2.3.3`, with the reason in a comment) to `pyproject.toml` and run `uv lock`. Verify:
  - `uv.lock` has pandas 2.3.3 and no other version change beyond Evidently's new dependencies (`git diff uv.lock`);
  - `make setup`, `make lint` and `make test` pass;
  - `uv run --locked --group monitor python -c "import evidently, pandas; print(evidently.__version__, pandas.__version__)"` prints `0.7.23 2.3.3`;
  - `uv run --locked python -m landcover.tracking seed` against the running cluster's port-forward 5002 still reports the existing champion.
- [x] 1.2 Split the first stage of `docker/serve/Dockerfile` into `base` and `deps`, add the target `monitor` (design Decision 9), and make `make images` loop over `ml llm monitor`. After a commit, with `minikube docker-env`, verify:
  - `make images` builds `landcover-monitor:<HEAD>`, and `ml` and `llm` reuse their cached layers;
  - `docker run --rm landcover-monitor:<HEAD> python -c "import evidently, torch"` fails on `torch` only;
  - `docker image inspect` shows the revision label;
  - record the image size for the README.

## 2. Monitor module

- [x] 2.1 Add `src/landcover/monitor.py` with `window()`, `quadrants()`, `label_quadrants()`, the source-ID helpers and the `replay` command (design Decisions 1–3), and `tests/test_monitor.py` with the window and quadrant tests of Decision 11. Verify `make test` passes. Against the cluster's ML port-forward, verify `python -m landcover.monitor replay --ml http://127.0.0.1:8000` waits for the boundary, prints 128 `ok`, and that `SELECT count(*), min(received_at), max(received_at) FROM serving.predictions WHERE source_id LIKE 'replay/%'` shows 128 rows inside one 5-minute window.
- [x] 2.2 Add the report core: version selection, the insufficient-data rule, the Evidently call on the ten columns and the parser of `DataDriftPreset`'s result (design Decision 6). Add the tests of Decision 11 that need Evidently, with `pytest.importorskip`. Verify:
  - `uv run --locked --group monitor pytest -q tests/test_monitor.py` passes, including identical frames giving 0 and a two-standard-deviation brightness shift crossing 0.5;
  - `make test` passes with those tests skipped.
- [x] 2.3 Add quality (design Decision 6, step 4) and the metrics registry with `push_to_gateway` (Decision 7), with the tests of Decision 11 for `models.scores` equality, `incomplete_labels`, the series set and an absent version. Verify:
  - `make test` passes;
  - with `TEST_DSN` set, the version-selection test passes: the window rows count, the reference row is excluded, and an empty window falls back to the latest version.
- [x] 2.4 Add `serving.labels` to `sql/serving.sql` and the `labels` and `reference` commands (design Decisions 4 and 5), with the `TEST_DSN` test that `labels` twice gives one row per fixture quadrant. Verify:
  - `make test` passes, and with `TEST_DSN` the new test passes;
  - against the cluster through port-forwards 8000, 5002 and 5433: `labels` gives 64 rows, none with a `D073-2022` source ID; `reference` gives 256 `reference/…` rows for the champion version; a second `reference` prints that the reference exists and sends nothing (row count unchanged);
  - after `kubectl rollout restart deployment/ml`, `sql/serving.sql` runs without error on a database that already has the table.

## 3. Monitoring stack

- [x] 3.1 Add `k8s/prometheus.yml` and the Pushgateway and Prometheus Deployments and Services to `k8s/landcover.yaml` (design Decision 8). Create ConfigMap `prometheus` and apply. Verify:
  - both pods are ready;
  - with a port-forward on 9090, `curl -s 127.0.0.1:9090/api/v1/targets` shows `ml` and `pushgateway` up, and `llm` up with `make llm-server` running or down without it;
  - `landcover_requests_total` returns series from the query API.
- [x] 3.2 Add the CronJob `drift-report` (design Decision 8) and apply it with `COMMIT` substituted. Verify:
  - a run started by the schedule completes (`kubectl get jobs` lists it with 1/1);
  - `curl -s` of the Pushgateway's `/metrics` shows the series of Decision 7 for the champion version, including `landcover_report_insufficient{reason="few_observations"}` in a window without traffic;
  - after a run with the Pushgateway scaled to 0, the Job is marked failed;
  - the next scheduled run after scaling back up succeeds.
- [x] 3.3 Add `k8s/grafana/` (data source, dashboard provider, `landcover.json` with the nine panels of design Decision 8) and the Grafana Deployment and Service. Create the two ConfigMaps and apply. With a port-forward on 3000, verify:
  - `http://127.0.0.1:3000/d/landcover` opens without a login;
  - every panel queries without an error, checked by opening each panel's query inspector, or by `GET /api/dashboards/uid/landcover` and each target through Prometheus's query API;
  - a panel edit in the browser cannot be saved over the provisioned file.

## 4. Bring-up

- [x] 4.1 Extend `scripts/cluster.sh` and the Makefile (design Decision 10): the three ConfigMaps, the rollout waits, the PostgreSQL port-forward with a TCP check, `reference` and `labels` after the smoke request, the printed port-forward commands; Makefile targets `replay` and `reference`. After a commit, verify on the running cluster:
  - `make cluster` exits 0, prints the Grafana and Prometheus commands, and its last lines list the monitoring pods as ready;
  - a second run sends no reference request, keeps 64 labels and builds no layer;
  - no port-forward process remains after it exits (`pgrep -f port-forward`).
- [x] 4.2 Clean-clone run: clone the pushed branch into the scratchpad, `cp .env.example .env`, ask the author before `minikube delete`, then `time make cluster`. Verify it exits 0 with the monitoring components ready and the reference built. Record the cold and warm durations in the README's bring-up block, replacing the earlier numbers.
- [x] 4.3 Update the README "Lab 4: cluster" bring-up list for the new steps and the port-forwards. Verify every changed command runs as written.

## 5. Evidence and documents

- [x] 5.1 Memory: with the cluster up, after one report run and a 1024×1024 `/predict`, record:
  - `docker stats --no-stream minikube`;
  - `memory.peak` of each pod, including a completed report Job (read during the run with `kubectl exec` or from its log line);
  - set the requests and limits of design Decision 8 from the measurements.

  Verify `kubectl get pods` shows 0 restarts and no `OOMKilled` in `kubectl get events`.
- [x] 5.2 Two windows: run `make replay`, let one window pass empty, run `make replay` again, and wait for the report after each window. Verify:
  - the three reports give equal distances for the two replay windows and `few_observations` with current 0 for the middle one;
  - mean IoU appears for both replay windows with 64 labelled rows.

  Save the dashboard screenshot as `docs/screenshots/grafana-two-windows.png` (time range covering the three windows; panels 1, 2, 4, 6, 7, 8 and 9 visible). Also save one pushed report (`curl -s 127.0.0.1:9091/metrics | grep '^landcover_'`).
- [x] 5.3 Add the README section "Lab 4: monitoring" (design Decision 12), with:
  - the memory table of 5.1;
  - the captured `kubectl get pods,svc` and `kubectl get cronjob,jobs` with the monitoring components;
  - the screenshot and the report of 5.2.

  Replace the pods-and-services capture of "Lab 4: cluster" and remove its sentence "The monitoring components join this list in the next part of Lab 4". Verify every command in the section runs as written on the current commit.
- [x] 5.4 Revise Section 6.6 and the same passages in the local `docs/design.uk.md` (design Decision 12). Verify:
  - `grep -n "PSI\|Population Stability\|10 percentage points\|histogram bin" docs/design.md` finds no PSI or 10-point rule and no histogram bins in Section 6.6, only the probe's comparison that names PSI as the rejected test;
  - the section names the metrics, the test, the provisional threshold, the schedule and window, the reference, the labels and the freshness signal;
  - `git check-ignore docs/design.uk.md` succeeds;
  - re-applying the manifest on the new commit leaves the retrieval index version unchanged (the index Job prints the same version).
- [x] 5.5 Add the scorecard row "Monitoring scheduled", linking the CronJob and the dashboard blocks of "Lab 4: monitoring". Verify each link resolves to an existing heading.

## 6. Integration check

- [ ] 6.1 On the final commit, run `make lint`, `make test` and `uv run --locked --group monitor pytest -q tests/test_monitor.py`. Then run `openspec validate add-lab4-monitoring --strict`. Verify all pass, and that `kubectl get pods,svc` in the README matches a fresh capture: same components, all ready.

## Workflow follow-up

- Archive this change together with the other Lab 4 changes once the whole lab is complete, in order: `add-lab4-services`, `add-lab4-cluster`, `add-lab4-monitoring`, `add-lab4-drift-alert`.

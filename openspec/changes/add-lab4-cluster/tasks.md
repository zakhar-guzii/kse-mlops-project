# Tasks

Follow [design.md](design.md) and the two specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`.

Out of scope for this change:
- Prometheus, Grafana, Pushgateway, Alertmanager configuration, a drift job, a replay script, reference statistics or alerts. They belong to `add-lab4-monitoring` and `add-lab4-drift-alert`.
- Edits to the service code (`serve_ml.py`, `serve_llm.py`), `docker/serve/Dockerfile`, `docker-compose.yml`, Sections 5.1 and 6.8, `retrieval.toml` or `prompts/`.
- Changes to the Compose registry or its volumes.
- Archiving any change and adding licence checks.

`make images` and `train` need a committed tree. Before each step that runs them, ask the author to commit or approve the commit.

## 1. Cluster and images

- [ ] 1.1 Ask the author before deleting the existing `minikube` profile, which comes from the host check and was created with 4 GB. Then start Minikube with the flags of design Decision 10 and the defaults 6144 MB and 4 CPUs, after checking that Docker Desktop's memory allows it. Verify `minikube kubectl -- version` reports server v1.30.0 and `minikube profile list` shows runtime docker. Verify `minikube kubectl -- run dns --rm -it --image=busybox:1.36 --restart=Never -- nslookup host.minikube.internal` resolves.
- [ ] 1.2 With `eval "$(minikube docker-env)"`, run `make images` and `docker build -t landcover-mlflow:3.16.1 docker/mlflow`. Verify `minikube image ls` lists `landcover-ml:<HEAD>`, `landcover-llm:<HEAD>` and `landcover-mlflow:3.16.1`, and a second `make images` reuses every layer. If BuildKit's cache mount fails against Minikube's daemon, switch design Decisions 7 and 10 to building on Docker Desktop with `minikube image load`, record why in design.md, and verify the same listing.

## 2. Data sample and registry seed

- [ ] 2.1 Split `make data` into `sample` (fetch, `dvc commit`, `git diff --exit-code`) and `data: sample` plus `dvc push`, as in design Decision 10. Verify `make sample` on the existing `data/raw` downloads nothing and succeeds, and `make data` with Compose up still pushes. Verify the README "Raw data" section still describes `make data` correctly and mentions `make sample`.
- [ ] 2.2 Add `seed` to `src/landcover/tracking.py` and make `register` return the version, as in design Decision 9. Add the test to `tests/test_training_and_tracking.py`. Verify `make test` passes, and that the test shows an existing alias trains nothing, a missing alias trains `rule` then `rf` and promotes the second version, and another registry error is raised.

## 3. Manifests

- [ ] 3.1 Write `k8s/landcover.yaml` with PostgreSQL, MLflow and the ConfigMap `landcover` (design Decisions 2, 3, 5 and 6). Create the Secret and `postgres-init` as in Decision 5, then apply. Verify `rollout status` succeeds for both, and `\l` in the PostgreSQL pod lists `landcover` and `mlflow`. With a port-forward on 5002, verify `curl -s 127.0.0.1:5002/health` answers and a request with `-H 'Host: evil:5000'` is refused. Verify `grep -r "$POSTGRES_PASSWORD" k8s/` finds nothing. If the MLflow pod exits with code 132, add `cryptography<47` to `docker/mlflow/Dockerfile`, rebuild, verify the pod runs and note it for the README.
- [ ] 3.2 Add the `ml` and `llm` Deployments and Services and the Job `retrieval-index-COMMIT` (design Decisions 4 and 8). Apply with `COMMIT` substituted. Run `seed` through the port-forward and verify it registers versions 1 and 2 with lineage tags and `champion` on 2. Verify the Job completes and prints the expected index version. Verify `ml` becomes ready and `/predict` through a port-forward on 8000 reports version 2 and `image_commit` equal to `HEAD`. With `make llm-server` up, verify `llm` becomes ready and `/ask` answers with `export-contract` among its sources. With the host server stopped, verify `/health/ready` reports 503 naming `host.minikube.internal:8081`, and the pod is not restarted.
- [ ] 3.3 Add `--cache-ram 2048` to `make llm-server`. With the cluster up, the server answering after one `/ask` and Compose stopped, record for the README:
  - `docker stats --no-stream` of the Minikube container;
  - each pod's `memory.peak`;
  - `footprint $(pgrep -x llama-server)`.

  Set every memory request and limit in `k8s/landcover.yaml` to the measured value with the margin of design Decision 4. Verify no pod has restarted (`kubectl get pods` shows 0 restarts) after a 1024×1024 `/predict` and one `/ask`.

## 4. One command

- [ ] 4.1 Add `scripts/smoke.py` as in design Decision 11. Verify `predict` passes against the running `ml` and exits 1 naming both versions when `--commit` is wrong. Verify `ask` passes with the host server up.
- [ ] 4.2 Add `scripts/cluster.sh` and the `cluster` target with `MINIKUBE_MEMORY` and `MINIKUBE_CPUS`, as in design Decision 10. Verify on the running cluster:
  - the command exits 0 and ends with `kubectl get pods,svc` and `took N s`;
  - a second run builds no layer, registers no version, creates no Job and passes the smoke request;
  - with `.env` moved aside, it stops at once naming the file;
  - with llama-server stopped, it prints the LLM reason and exits 0;
  - no port-forward process remains after it exits (`pgrep -f port-forward`).
- [ ] 4.3 Cold run from a clean clone. Clone the pushed branch into the scratchpad, `cp .env.example .env`, ask the author before running `minikube delete`, then run `time make cluster`. Verify it exits 0, and record the cold duration and the slowest steps from the script's output. Run it again and record the warm duration.
- [ ] 4.4 Add the README section "Lab 4: cluster" (design Decision 13). It covers prerequisites, `make cluster` with its captured output, the two durations, the memory table of 3.3, port-forward commands, `minikube stop` and `minikube delete`, and the code-132 note if 3.1 needed it. Verify every command in it runs as written on the current commit.

## 5. Evidence

- [ ] 5.1 Missing model in the cluster: follow design Decision 13 with `MODEL_ALIAS=missing`. Paste the captured `rollout status` failure, `get pods` (new pod 0/1), the new pod's readiness events and the EndpointSlice without the new pod's address. Create alias `missing` and show the pod becoming ready without a restart, then delete the alias and run `rollout undo`. Verify `champion` and the Deployment are back as before and the README block is pasted, not retyped.
- [ ] 5.2 Promotion without a rebuild. Import `runs/unet-c1f77a3` into the cluster registry and register it. Verify it becomes version 3 with the original lineage tags. Run `make champion VERSION=3`, `rollout restart` and `rollout status`. Verify `/predict` reports `"3"` and `kubectl get deploy ml -o wide` shows the same image before and after. Paste both into the README with the reviewer's path (`VERSION=1`, back to 2). Verify `champion` stays on 3 for the author's cluster and that the README says which state a fresh `make cluster` gives.
- [ ] 5.3 With `make llm-server` up, capture `kubectl get pods,svc` with `postgres`, `mlflow`, `ml` and `llm` ready and the completed Job, and paste it into the README.

## 6. Design document and scorecard

- [ ] 6.1 Revise Sections 5.5, 6.2, 6.4 and 6.7 as in design Decision 13, and the same passages in the local `docs/design.uk.md`. Verify:
  - `grep -n "until Lab 4\|Lab 4 adds authentication\|move to Minikube in Lab 4" docs/design.md` finds nothing;
  - `git check-ignore docs/design.uk.md` succeeds;
  - re-applying the index Job on a new commit prints the unchanged index version, which shows Sections 5.1 and 6.8 were not edited.
- [ ] 6.2 Add the three scorecard rows "Services containerized", "Services deployed with health contracts" and "One command brings the system up" to the README table, each linking its README block. Verify each link resolves to an existing heading.

## 7. Integration check

- [ ] 7.1 Run `openspec validate add-lab4-cluster --strict`, `make lint`, `make test` with `TEST_DSN` set and `git diff --check`. Verify all pass and the diff touches no file excluded in the preamble, except `docker/mlflow/Dockerfile` when 3.1 needed the code-132 line.
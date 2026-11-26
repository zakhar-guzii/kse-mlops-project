# Design

## Context

See proposal.md for the motivation and the decision tables, and the two specifications under `specs/` for the required behaviour. Current state that shapes the approach:

- **Tools on the course Mac.**
  - Minikube v1.33.1 is installed in `~/.local/bin`. Its default and newest Kubernetes version is v1.30.0.
  - A profile `minikube` already exists from the host check of `add-lab4-services`, created with the lab's 4 GB.
  - kubectl on `PATH` is v1.34.1, four minor versions from the server; the skew policy supports one. `minikube kubectl --` downloads and runs v1.30.0.
  - Helm is not installed. kustomize is built into kubectl.
- **Minikube with the docker driver on macOS.**
  - The node IP is not reachable from the host, so a NodePort needs `minikube service --url` in a held terminal; `kubectl port-forward` works on any Service.
  - Locally built images need `imagePullPolicy: IfNotPresent` or `Never`. `docker-env` needs the docker runtime, the default at 1.33.1; the flag is set explicitly because later releases default to containerd.
  - `host.minikube.internal` is injected into CoreDNS on a profile's first start. It resolves to Docker Desktop's host gateway (`192.168.65.254`). The minikube documentation says a host service bound to `127.0.0.1` "will not work", but `add-lab4-services` measured a pod reaching llama-server on `127.0.0.1:8081` three times in a row; the very first request after `minikube start` timed out.
- **MLflow 3.16.1.**
  - `mlflow server` starts uvicorn with `--workers` defaulting to 4. The Compose server measured 2.19 GiB.
  - `--allowed-hosts` replaces the default list (localhost on any port and private IPs) and accepts wildcards. The Service name `mlflow:5000` must be listed for the ML pod to be accepted.
  - The image `docker/mlflow` adds `psycopg2-binary` and `boto3` to `ghcr.io/mlflow/mlflow:v3.16.1`.
  - Exit code 132 is a SIGILL in `cryptography` ≥ 47 under hypervisors that report CPU features the chip lacks, such as old Docker Desktop releases. The Lab 2 stack did not hit it.
- **Services (`add-lab4-services`).**
  - Both images listen on 8000 and take their configuration from the environment (design Decision 8 there).
  - The ML server answers at once and loads its model in a background thread, so liveness passes during the load.
  - The LLM server loads its embedding model in the lifespan, before uvicorn accepts connections.
  - Measured ML memory: 827 MiB idle, 969 MiB at a 512×512 tile, 1,145 MiB at 1024×1024.
  - The LLM image holds `corpus/`, `docs/design.md`, `retrieval.toml`, the embedding model in `/opt/hf` and `landcover.retrieval`, whose `index` command needs no clean Git tree.
- **Clean clone.**
  - `runs/` and `models/` are ignored.
  - `make data` fetches the sample (`scripts/fetch_sample.py`, which skips present files), commits it to DVC, checks `data/raw.dvc` against `HEAD` and pushes to the Compose silo.
  - `python -m landcover.train <kind>` refuses an uncommitted tree and prints the result directory.
  - `tracking.log` verifies `data/raw`, rescores and returns the run ID. `tracking.register` loads the version back from the registry, which therefore must be reachable from the host.
  - Training takes about 1 s for the rule and 30 s for the forest.
- **Memory.**
  - The Mac has 24 GiB.
  - llama-server: physical footprint 3.0 GB fresh, up to 8.6 GB (peak 11 GB) with the default 8,192 MiB prompt cache, plus about 6 GB of clean pages of the model file that macOS can drop.
  - The Compose stack takes 3.69 GiB and is not needed by the cluster.
- **Existing specifications.** The `experiment-tracking` requirement "Tracking server in the local stack" (PostgreSQL metadata, S3 files, no file store) describes the Compose server, which stays unchanged. The cluster server is a second server, specified in `cluster-deployment`. It keeps metadata in PostgreSQL and model files on a persistent volume behind the same proxy contract.

## Goals / Non-Goals

**Goals:**
- `make cluster` from a clean clone on the course Mac, and on a reviewer's machine with Docker Desktop, Minikube, uv and the `.env` copy.
- Manifests that a reader can follow in one file, with every value that differs between commits substituted by one placeholder.
- Room in the 6 GB node for the monitoring components of `add-lab4-monitoring`.

**Non-Goals:**
- High availability, more than one replica, autoscaling, ingress, TLS, network policies.
- Migrating the Compose registry or its runs into the cluster.
- Running Airflow or the DVC remote in the cluster.
- Any change to the service code or the images.

## Decisions

### 1. Topology

```
 host (Mac)                              Minikube (6 GB, 4 CPUs, k8s 1.30.0, runtime docker)
 +-----------------------+               +----------------------------------------------+
 | make cluster          |  port-forward | Deployment ml  + Svc ml:8000      --+        |
 |  sample, seed, smoke  |<------------->| Deployment llm + Svc llm:8000     --+--> postgres
 |                       | 5002 mlflow   | Deployment mlflow + Svc :5000, PVC --+    + Svc |
 |                       | 8000 ml       | Job retrieval-index-<commit>      --+    + PVC |
 |                       | 8002 llm      | ConfigMap landcover, postgres-init; Secret     |
 | llama-server          |               |                                                |
 | 127.0.0.1:8081 <------+---------------+-- llm via host.minikube.internal:8081          |
 +-----------------------+               +----------------------------------------------+
 Compose: stopped while the cluster runs; kept for Labs 2 and 3
```

All objects go in the `default` namespace, so `kubectl get pods,svc` needs no flag; `minikube delete` removes everything. All Services are ClusterIP.

Alternative: keep MLflow's database and object store in Compose and reach them through `host.minikube.internal` (keeps the registry history). Rejected: the cluster would depend on a second stack, two MLflow servers would share one database, and the Compose memory would not be freed.

### 2. PostgreSQL

- A Deployment with one replica, strategy `Recreate`, and a 2 Gi PVC from Minikube's default storage class. `PGDATA` is a subdirectory of the mount.
- The image is `pgvector/pgvector:0.8.7-pg16-trixie`, the same as Compose.
- `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB=landcover` come from the Secret and the manifest.
- `sql/warehouse.sql` is mounted from the ConfigMap `postgres-init` into `/docker-entrypoint-initdb.d`. On the first start it creates the databases `mlflow` (and the unused `airflow`) and the Lab 2 schemas, exactly as in Compose.
- The `vector` extension and the `retrieval` schema come from the index Job; `serving` comes from the ML service.
- Readiness: `pg_isready -U $POSTGRES_USER -d landcover`.

Alternative: a StatefulSet. Rejected: one replica with one claim gains nothing from stable identities.

### 3. MLflow

The image is `landcover-mlflow:3.16.1`, built from `docker/mlflow` in Minikube's daemon. The Deployment runs one replica with strategy `Recreate` and a 2 Gi PVC on `/mlartifacts`. The command:

```sh
mlflow server --host 0.0.0.0 --port 5000 --workers 1 \
  --backend-store-uri "$MLFLOW_BACKEND_URI" \
  --artifacts-destination /mlartifacts \
  --allowed-hosts mlflow:5000,mlflow.default.svc.cluster.local:5000,localhost:5002,127.0.0.1:5002
```

`MLFLOW_BACKEND_URI` (`postgresql://user:password@postgres/mlflow`) comes from the Secret. A port-forward keeps the client's `Host` header, so the host commands are accepted on 5002, and any other name is refused.

Probes:
- startup `GET /health` every 5 s, 36 failures (3 min for the first migration);
- readiness `GET /health` every 10 s;
- liveness `GET /health` every 20 s, 3 failures.

The `cryptography<47` line is added to `docker/mlflow/Dockerfile` only if the pod exits with code 132; the README then says so, as Lab 2's notes ask.

Alternative: SQLite and a file store on one PVC with the plain official image. Rejected: it changes the backend kind from the Compose server and the design document for no memory gain, since PostgreSQL runs anyway for the services.

### 4. Services

| | `ml` | `llm` |
|---|---|---|
| Image | `landcover-ml:COMMIT` | `landcover-llm:COMMIT` |
| Environment | `envFrom` ConfigMap `landcover`; `WAREHOUSE_DSN` from the Secret | same |
| Startup probe | none: liveness checks only the process, which answers at once | `GET /health/live` every 2 s, 60 failures (2 min) |
| Readiness | `GET /health/ready` every 5 s, timeout 5 s | `GET /health/ready` every 5 s, timeout 5 s (two 2 s checks) |
| Liveness | `GET /health/live` every 10 s, 3 failures | same |
| Memory request / limit | 1 Gi / 1536 Mi | 1 Gi / 1536 Mi |
| CPU request | 500m | 250m |

Both use `imagePullPolicy: IfNotPresent` and the default RollingUpdate. With one replica the default allows one extra pod and none unavailable, so a new pod that never becomes ready leaves the old one serving. The missing-model evidence relies on this.

No CPU limit: the image already pins one torch thread, and a limit would only add throttling to the latency the monitoring change measures.

| Pod | Memory request / limit | CPU request |
|---|---|---|
| postgres | 128 Mi / 512 Mi | 100m |
| mlflow | 512 Mi / 1 Gi | 100m |
| retrieval-index Job | 1 Gi / 1536 Mi | 500m |

Group 3 of the tasks measures these figures and corrects them.

### 5. ConfigMap and Secret

- ConfigMap `landcover`, committed in the manifest:
  - `MLFLOW_TRACKING_URI=http://mlflow:5000`
  - `MODEL_NAME=landcover-segmenter`
  - `MODEL_ALIAS=champion`
  - `LLM_BASE_URL=http://host.minikube.internal:8081/v1`

  Other variables keep the defaults of the service code.
- ConfigMap `postgres-init`, created from `sql/warehouse.sql` with `kubectl create configmap --dry-run=client -o yaml | kubectl apply -f -`.
- Secret `landcover`, created the same way with `--from-literal` from the variables of `.env`, which the Makefile exports:
  - `POSTGRES_USER` and `POSTGRES_PASSWORD`
  - `WAREHOUSE_DSN=postgresql://U:P@postgres/landcover`
  - `MLFLOW_BACKEND_URI=postgresql://U:P@postgres/mlflow`

  No AWS key: the cluster has no object store. No API key: the text model is local.

### 6. Manifests

One file, `k8s/landcover.yaml`, holds every object except the generated ConfigMap and Secret. The literal `COMMIT` stands for the full SHA in the two image tags and the Job name. The bring-up applies `sed "s/COMMIT/$(git rev-parse HEAD)/g" k8s/landcover.yaml | kubectl apply -f -`.

Alternatives:
- Helm: not installed, and a chart is another tool and templating language for a reviewer.
- kustomize through `kubectl apply -k`: it cannot set an image tag from the command line without the separate kustomize binary, and its generators add nothing that two `create --dry-run` lines do not.

### 7. Images in the cluster

`eval "$(minikube docker-env)"`, then `make images` unchanged, then `docker build -t landcover-mlflow:3.16.1 docker/mlflow`. The images are built by Minikube's daemon and stay where the pods run, with the BuildKit cache in the node.

Alternative: build on Docker Desktop and run `minikube image load`. That exports 2.9 and 3.7 GB unpacked on every commit and stores them twice. It remains the fallback if BuildKit's cache mounts fail against Minikube's daemon (Risks).

### 8. Retrieval index

The Job `retrieval-index-COMMIT` runs `python -m landcover.retrieval index` in `landcover-llm:COMMIT` with `WAREHOUSE_DSN` from the Secret, `backoffLimit: 1` and no TTL. The image is offline (`HF_HUB_OFFLINE=1`) and carries the documents and settings whose version the LLM readiness check expects, so the index equals the image by construction.

Applying the manifest at the same commit leaves the completed Job unchanged and nothing runs. A new commit creates a new Job, which replaces the schema in one transaction.

`ponytail:` completed Jobs of earlier commits stay listed; delete them with `kubectl delete job -l app=retrieval-index` if the list grows.

Alternative: `make retrieval-index` on the host through a port-forward to PostgreSQL. Rejected: it needs the `rag` group, a 471 MB Hugging Face download and a host process whose index might not match the image.

### 9. Seeding the registry

`python -m landcover.tracking seed`:

1. If `MlflowClient().get_model_version_by_alias(MODEL_NAME, "champion")` succeeds, print the version and stop.
2. Only on `RESOURCE_DOES_NOT_EXIST` or `INVALID_PARAMETER_VALUE` (no model, or no alias) continue. Any other error, such as an unreachable server, is raised.
3. For `rule` and then `rf`, run `python -m landcover.train <kind>` as a subprocess and take the last line of its output as the result directory, as `make train` does. Then `run = log(result)` and `version = register(run)`.
4. `champion(<forest version>)`.

`register` gains `return mv.version`. The test in `tests/test_training_and_tracking.py` replaces training, `log`, `register` and the client with fakes. It checks two things: an existing alias trains nothing, and a missing alias trains the two kinds in order and promotes the second version.

Alternative: chain `make train`, `make register RUN=…` and `make champion` in the shell, parsing the printed run ID. Rejected: fragile parsing, and no single place to test the skip.

### 10. Bring-up script

`make cluster` runs `scripts/cluster.sh` (bash, `set -euo pipefail`) with the variables of `.env` exported by the Makefile, plus `MINIKUBE_MEMORY ?= 6144` and `MINIKUBE_CPUS ?= 4`. The steps are too many for a readable recipe, and a script can own its port-forwards with one `trap`. `KUBECTL="minikube kubectl --"`.

1. Fail unless `.env` exists ("cp .env.example .env"). Fail if `git diff --quiet HEAD` fails, so the tree matches the images.
2. `minikube start --driver=docker --container-runtime=docker --kubernetes-version=v1.30.0 --memory=$MINIKUBE_MEMORY --cpus=$MINIKUBE_CPUS`. On a running profile this returns in seconds.
3. `eval "$(minikube docker-env)"`; `make images`; build the MLflow image.
4. `make sample`.
5. Create the Secret and `postgres-init`, then apply the substituted manifest.
6. `rollout status` for `postgres` and `mlflow`.
7. Port-forward `svc/mlflow` to `127.0.0.1:5002`, wait for `/health`, then run `MLFLOW_TRACKING_URI=http://127.0.0.1:5002 uv run --locked python -m landcover.tracking seed`.
8. `kubectl wait --for=condition=complete job/retrieval-index-<commit> --timeout=10m`.
9. `rollout status deploy/ml --timeout=5m`. Port-forward `svc/ml` to 8000. Run `uv run --locked python scripts/smoke.py predict --ml http://127.0.0.1:8000 --mlflow http://127.0.0.1:5002 --commit <sha>`.
10. If `curl -sf http://127.0.0.1:8081/v1/models` succeeds: run `rollout status deploy/llm --timeout=3m`, port-forward `svc/llm` to 8002 and run `smoke.py ask`. Otherwise print "llm not ready: no text model server on 127.0.0.1:8081 (make llm-server)".
11. `kubectl get pods,svc` and `took ${SECONDS} s`. The `trap` stops the port-forwards on any exit.

The Makefile's `data` becomes `data: sample` followed by `dvc push`. `sample` holds the fetch, the `dvc commit` and the `git diff --exit-code` check.

### 11. Smoke script

`scripts/smoke.py` uses only the standard library, because a reviewer may lack `jq`.

- `predict` reads the champion version from MLflow's REST endpoint `GET /api/2.0/mlflow/registered-models/alias?name=landcover-segmenter&alias=champion`. It posts `data/raw/D017-2021/images/AA-S2-9_2-7.tif` to `/predict` and fails unless:
  - the status is 200;
  - `width` and `height` are 512;
  - `mask` is non-empty;
  - `model_version` equals the champion;
  - `image_commit` equals `--commit`.

  It prints version and commit.
- `ask` posts the fixed question of the index check. It fails unless the status is 200, `answer` is non-empty and `model` equals `[llm].model` of `retrieval.toml`. It prints model and index version.

On failure it exits 1 with both values named.

### 12. Text model and memory

`make llm-server` gains `--cache-ram 2048`. The prompt cache only reuses evaluated prefixes, so answers at temperature 0 do not change. The Lab 3 runs mostly reused one cached token anyway, so latency does not change. Raising the limit costs memory the node needs.

The README memory table records, with the cluster up, the server answering and Compose stopped:
- `docker stats` of the Minikube container;
- each pod's `memory.peak` (`kubectl exec … cat /sys/fs/cgroup/memory.peak`);
- `footprint $(pgrep -x llama-server)`.

### 13. Evidence and documents

README section "Lab 4: cluster":
- prerequisites, `make cluster` and its captured output;
- the cold and warm duration and the three slowest steps;
- the memory table;
- port-forward commands for manual use;
- `minikube stop` and `minikube delete`.

Missing model:
1. `kubectl set env deployment/ml MODEL_ALIAS=missing`.
2. `rollout status --timeout=60s`, which fails.
3. Capture `get pods`, the new pod's `describe` events and `get endpointslices -l kubernetes.io/service-name=ml`.
4. Create alias `missing` and show the pod become ready without a restart.
5. Delete the alias and run `kubectl rollout undo deployment/ml`.

Alias:
1. With the MLflow port-forward up, `make import RESULT=runs/unet-c1f77a3 MLFLOW_TRACKING_URI=http://127.0.0.1:5002` and `make register` give version 3.
2. `make champion VERSION=3`, `kubectl rollout restart deployment/ml`, `rollout status`.
3. `/predict` reports `"3"`, and `kubectl get deploy ml -o wide` shows the same image before and after.

The reviewer's path is the same with `VERSION=1` and back to 2.

`kubectl get pods,svc` with everything ready, including `llm`, is captured with `make llm-server` up.

`docs/design.md` and the local `docs/design.uk.md`:
- **Section 5.5.** Rollout in the course: the operator runs `make champion` and `kubectl rollout restart`.
- **Section 6.2.**
  - A Lab 4 cluster paragraph covering what runs where, why Airflow and the DVC remote stay in Compose, the port-forward ports and `host.minikube.internal`.
  - The MLflow row and the "move to Minikube in Lab 4" sentence corrected.
  - The memory measurement replaces "measurement next to Minikube moves to Lab 4".
- **Section 6.4.** The sentence promising MLflow authentication in Lab 4 is replaced. The course server is a ClusterIP Service reached only through a port-forward on `127.0.0.1`, without authentication. The cloud deployment keeps operator credentials for the alias and read-only access for workers.
- **Section 6.7.** A Lab 4 paragraph: the LLM stays on the host and costs $0 per request. The node got 6 GB and the server's cache was capped at 2 GiB, which is the priority Appendix 2 asks about.

Sections 5.1 and 6.8 are not edited, so the index version does not change.

Three scorecard rows: "Services containerized", "Services deployed with health contracts" and "One command brings the system up", each pointing to its README block.

## Risks / Trade-offs

- [BuildKit cache mounts (`RUN --mount=type=cache`) fail when the host's Docker CLI builds against Minikube's daemon] → Task 1.1 checks this first. The fallback is to build on Docker Desktop and run `minikube image load` for both images in `cluster.sh`.
- [The existing `minikube` profile was created with 4 GB, and `minikube start --memory` does not resize a profile] → Task 1.1 asks the author to delete the test profile, which holds nothing of value. The README says to run `minikube delete` when changing memory.
- [Docker Desktop gives the VM less than 6 GB plus headroom] → `minikube start` refuses with the available amount. The README names the Docker Desktop setting and `MINIKUBE_MEMORY=4096` as a tight fallback.
- [The first request to `host.minikube.internal` after start-up times out] → The LLM readiness probe retries, and the bring-up waits for readiness instead of calling the host once.
- [Under memory pressure macOS drops the model file's pages, and generation slows] → The memory table shows the margin. Compose stays stopped; the cache cap keeps the server near 5 GB.
- [The MLflow pod exits with code 132] → Add `cryptography<47` to `docker/mlflow/Dockerfile` (46.0.7 is the last version reported working) and note it in the README. The cause is the hypervisor, so updating Docker Desktop is the first remedy.
- [A cold run downloads about 2–3 GB: the Minikube base image, Kubernetes images, pgvector, the Python and uv layers, torch] → The README states the cold duration separately from the warm one and names the downloads among the slowest steps.
- [The cluster registry starts without the author's Lab 2 history] → The Compose registry stays intact for Labs 2 and 3. The cluster's own U-Net version 3 is imported from the saved result with its original lineage tags.
- [`seed` trains with the code at `HEAD`, not at the commit of the historical versions] → Accepted: the cluster's versions carry `HEAD` as `git_commit`, and the reproduction command works on them as on any version.

## Migration Plan

Nothing migrates. The Compose stack and its volumes stay as they are. `minikube delete` removes the cluster with its database and artifacts. A new `make cluster` rebuilds everything and seeds a fresh registry.
# Proposal

## Why

Lab 4 steps 3 and 7 require both services and the tracking server deployed to Minikube, with configuration in a ConfigMap, secrets in a Secret and probes on the health endpoints. The ML service must load its model by registry alias, and a promotion followed by a restart must change the reported version without an image rebuild. One documented command must bring the system up from a clean clone and answer a smoke request. `add-lab4-services` built the two images and their contracts, but nothing runs them in a cluster, and the registry lives only in the Compose stack.

This is the second of four Lab 4 changes: `add-lab4-services` → `add-lab4-cluster` → `add-lab4-monitoring` → `add-lab4-drift-alert`.

## What Changes

- Deploy to Minikube 1.33.1 (Kubernetes 1.30.0, docker driver and runtime): PostgreSQL with pgvector holding the databases `landcover` and `mlflow`, the MLflow 3.16.1 tracking server, the ML service and the LLM service. Each runs as a Deployment with a Service. The cluster does not depend on the Compose stack.
- Run MLflow with one worker and its allowed hosts set. It keeps metadata in the cluster's PostgreSQL and proxies artifacts to a persistent volume, so the cluster has no object store.
- Put the tracking address, model name, alias and text-model address in a ConfigMap, and the database credentials and the connection string that contains them in a Secret created from `.env`.
- Add readiness and liveness probes on `/health/ready` and `/health/live`, and startup probes where start-up is slow (MLflow migrations, the LLM service's embedding model).
- Build the retrieval index in the cluster with a Job that runs the LLM image's own corpus, settings and embedding model.
- Add `make cluster`, one command that:
  - starts Minikube;
  - builds the three images in Minikube's Docker daemon;
  - fetches and checks the data sample;
  - applies the manifests;
  - seeds an empty registry with the majority-class rule (version 1) and the random forest (version 2), promoting version 2;
  - waits for readiness;
  - sends a smoke request to `/predict`, and to `/ask` when the host text-model server answers;
  - prints `kubectl get pods,svc` and its own duration.

  Running it again changes nothing that is already in place.
- Split `make data` into `make sample` (fetch and check) and the push to the Compose DVC remote, so the cluster path needs no Compose.
- Add `python -m landcover.tracking seed`. It trains, logs and registers the two CPU models and promotes the forest, only when the registry has no `champion`.
- Cap the host text-model server's prompt cache with `--cache-ram 2048` in `make llm-server`, so Minikube with 6 GB and the server fit in 24 GiB.
- Record evidence in the README:
  - an ML pod that is not ready while its alias is missing (saved output);
  - a promotion and a restart reporting the new version with the same image tag: the author's U-Net imported as version 3, and version 1 for a reviewer;
  - `kubectl get pods,svc`;
  - the memory measured next to the text model;
  - the cold and warm duration of `make cluster`.
- Revise the design document:
  - Section 6.2: the cluster, what stays in Compose and why.
  - Section 6.4: MLflow authentication is dropped from the course deployment.
  - Section 6.7: where the LLM runs and what it costs.
  - Section 5.5: who promotes.
- Add the three Lab 4 scorecard rows: services containerized, deployed with health contracts, one command.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| What runs in the cluster | PostgreSQL (pgvector) with `landcover` and `mlflow`, MLflow with artifacts on a persistent volume, the ML and LLM services. No object store in the cluster. The Compose stack stays as it is for Labs 2 and 3: Airflow, the DVC remote and the historical registry. `make cluster` does not start it |
| Memory | Minikube 6 GB and 4 CPUs by default, overridable through `MINIKUBE_MEMORY` and `MINIKUBE_CPUS`. One replica per service. Memory requests and limits from the measured footprints; CPU requests only. Compose is stopped while the cluster runs. `make llm-server` gains `--cache-ram 2048`. The measurement goes into the README |
| Registry on a clean clone | `seed` registers the rule as version 1 and the forest as version 2 and promotes version 2. It is skipped when `champion` exists. A reviewer proves the alias path with version 1 |
| U-Net | The author imports the saved U-Net result (`runs/unet-c1f77a3`) into the cluster registry as version 3 and promotes it for the saved evidence. It is not part of `make cluster`, which needs no Colab account |
| MLflow authentication | Not added. Section 6.4 no longer promises it for Lab 4. The course server is a ClusterIP Service, reached from the host only through a port-forward on `127.0.0.1`. The cloud deployment keeps authentication |

Proposed as defaults in exploration and taken without objection:

| Topic | Default | Reason |
|---|---|---|
| Waiting for the LLM service | `make cluster` waits for and smoke-tests the LLM service only when `http://127.0.0.1:8081/v1/models` answers on the host; otherwise it prints why the service is not ready and still succeeds | Lab 4 requires the smoke request on the prediction endpoint; a reviewer without the 7 GB model file would otherwise wait forever |
| Retrieval index | A Job named after the commit runs `python -m landcover.retrieval index` in the LLM image | The image already holds the corpus, settings and embedding model the readiness check compares against; the host needs neither the `rag` group nor a Hugging Face download |
| Text-model address | `http://host.minikube.internal:8081/v1`; llama-server stays on `127.0.0.1` | Measured in `add-lab4-services`: a pod reaches a host service bound to loopback through Docker Desktop's gateway |
| Images | Built with `minikube docker-env` and `make images`, plus the `docker/mlflow` image; `minikube image load` is the fallback | The images are 2.9 and 3.7 GB unpacked; building where they run avoids exporting and storing them twice |
| Manifests | Plain YAML in `k8s/`, the commit substituted with `sed`, applied with `minikube kubectl --` | No Helm on the machine; `kubectl apply -k` cannot set the tag from the command line; the bundled client matches the server's 1.30, while the installed 1.34 is outside the supported skew |
| Access from the host | ClusterIP Services and `kubectl port-forward` on fixed local ports: 5002 MLflow, 8000 ML, 8002 LLM | A NodePort is not reachable from macOS with the docker driver |

## Capabilities

### New Capabilities

- `cluster-deployment`: the Kubernetes objects of the course system, covering the services, tracking server and database, configuration and secrets, probes, model loading by alias with promotion by restart, and the in-cluster retrieval index.
- `cluster-bringup`: the one documented command that brings the cluster up from a clean clone, seeds an empty registry, smoke-tests the services, can be repeated safely and reports its duration.

### Modified Capabilities

None. The Compose tracking server of `experiment-tracking` and the fetch command of `raw-data-versioning` keep their requirements. `make data` still fetches, checks and pushes.

## Impact

- New files: `k8s/landcover.yaml`, `scripts/cluster.sh`, `scripts/smoke.py`.
- Changed files:
  - `Makefile`: targets `cluster` and `sample`, `data` built on `sample`, `--cache-ram 2048` in `llm-server`, the Minikube variables;
  - `src/landcover/tracking.py`: subcommand `seed`; `register` returns the version;
  - `tests/` for `seed`;
  - `README.md`;
  - `docs/design.md`, Sections 5.5, 6.2, 6.4 and 6.7, and the local, ignored `docs/design.uk.md`.
- Possibly changed: `docker/mlflow/Dockerfile` gains `cryptography<47` only if the pod exits with code 132.
- Not edited: Sections 5.1 and 6.8 of the design document, so the index version stays the same; `retrieval.toml`; `prompts/`; the service code and images; `docker-compose.yml`; the Compose registry.
- Out of scope:
  - Prometheus, Grafana, Pushgateway, Alertmanager, the drift CronJob, the replay script and alerts;
  - the topology diagram of Section 6.1 and Sections 6.3, 6.6, 6.9 and 7.3 (later changes);
  - the remaining scorecard rows and the `lab-4` tag.
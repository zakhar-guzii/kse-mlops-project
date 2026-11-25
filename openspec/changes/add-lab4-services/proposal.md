# Proposal

## Why

Lab 4 (step 2) requires a container image for the ML service and one for the LLM service, each with a health endpoint and a prediction endpoint, built from the repository by a documented command with the image tag equal to the commit; the ML service must report not ready while its model is absent. The repository has a registered model behind `champion` and a Lab 3 retriever and answer path, but nothing serves them over HTTP.

This is the first of four consecutive Lab 4 changes: `add-lab4-services` → `add-lab4-cluster` → `add-lab4-monitoring` → `add-lab4-drift-alert`. It builds the two services and their images and fixes the contracts the later changes depend on: the health endpoints the probes call, the configuration the ConfigMap and Secret supply, the `/metrics` names Prometheus scrapes, and the request log the drift job reads.

## What Changes

- Add the ML service: a synchronous `POST /predict` that takes one 8-bit RGB image as the raw request body and returns its class mask, the model name and version that produced it, the image commit, input features, class fractions and a dark-image warning. The service loads the model by registry name and alias, resolves the alias to a version number once at start-up and reports that number.
- Add the LLM service: a thin `POST /ask` that retrieves passages from the Lab 3 index, prompts the host text model with `prompts/rag.md` and returns the answer with its cited sources. The model name, prompt files, top-k and chunk settings come from `retrieval.toml` and `prompts/`. The model itself stays outside the container.
- Give both services `/health/live`, `/health/ready` and `/metrics`. The ML service is not ready until its model is loaded and its request log is reachable. The LLM service is not ready until the text model server and the corpus index respond.
- Log every request the ML service serves to a new table `serving.predictions` in the database `landcover`. One row holds one image: time, model version, image commit, outcome, input features, class fractions, warning and mask. Writing the row is part of serving the request.
- Add one Dockerfile with two targets and a `make images` command. It builds both images from `git archive HEAD`, tags each with the full commit SHA and refuses uncommitted changes to tracked files.
- Add a dependency group `serve` that takes the CPU-only build of torch from the PyTorch index. The groups `nn` and `rag` keep the CUDA build for Colab.
- Document the services in the README. Include the commands, the image sizes and the saved output of the missing-model case. Add a Lab 4 paragraph to Sections 6.2 and 6.3 of the design document.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| Request and response | Synchronous `POST /predict` with one image as the raw body and one JSON response. The job queue, workers, leases, user tokens, 24-hour retention, tiling of large images and the overlay stay product description in the design document |
| Input ceiling | An image above the configured pixel or byte limit is refused with its reason, because the course service does not tile |
| Model kinds | One ML image loads the rule, the random forest or the U-Net, whichever version the alias names. Promotion is then `make champion VERSION=1` and a restart, without training a third version |
| torch | CPU-only build from the PyTorch index in a separate group `serve`. The `nn` group keeps CUDA for Colab |
| Code that runs the model | The image's own `landcover` package. The registry supplies weights and model kind; the image tag names the code |
| Version resolution | Once at start-up, through the alias. The version stays fixed until restart (Section 5.5) |
| Liveness and readiness | `/health/live` checks only the process. `/health/ready` returns 503 with a reason until every dependency of a request responds |
| Missing model | The server starts at once. A background loader retries every 10 s until the first success, and `/predict` answers 503 meanwhile. Reproduced with an alias absent from the registry; the output is saved in the README |
| Request log | Table `serving.predictions` in `landcover`, one row per served request, plain columns for features and fractions, the mask as bytes, an optional client `X-Source-Id`. A failed write fails the request. The service creates the schema at start-up. The LLM service writes no rows |
| Observation unit | One request with one image. The replay and the reference of `add-lab4-drift-alert` use 256×256 quadrants of the development and final tiles, 128 per window; final labels are not opened |

Proposed as defaults and confirmed by the author on review:

| Topic | Default | Reason |
|---|---|---|
| LLM configuration | Model name, top-k, chunk settings and prompts from `retrieval.toml` and `prompts/` in the image. The server address (`LLM_BASE_URL`) and `WAREHOUSE_DSN` come from the environment | The lab requires the Lab 3 configuration file. The address differs inside a container |
| Embedding model | Downloaded into the image at build time at the pinned revision (about 490 MB of files). The container runs with `HF_HUB_OFFLINE=1` | A pod with no network start-up dependency on Hugging Face; the revision is in the image as well as the tag |
| Metrics | Request counter by endpoint and outcome (plus model version on the ML service), latency histogram per endpoint with buckets suited to each service, `landcover_model_loaded`; on the LLM service a histogram per stage (retrieve, generate) and token counters. Health and metrics requests are not counted | The lab names request count, latency and errors; the stage split shows where the 11 s of an answer go |
| Image build | `make images` builds from `git archive HEAD` and refuses a tree with uncommitted changes to tracked files. The commit is also in the environment and the OCI label `org.opencontainers.image.revision` | The image content equals the commit by construction; the refusal keeps a developer from expecting uncommitted edits in the image |
| Existing specs | `segmentation-monitoring` and `gis-assistant` keep their product wording on jobs and workers. The course services get their own capabilities | They describe the product the design document keeps; the course service is a stated subset of it |

## Capabilities

### New Capabilities

- `segmentation-service`: the ML prediction endpoint, its input contract, model loading by alias with version reporting, health endpoints, request log and service metrics.
- `assistant-service`: the LLM question endpoint over the Lab 3 retriever and the host text model, its configuration source, health endpoints and service metrics.
- `service-images`: building the two images from a commit by one documented command and tracing a running image back to that commit.

### Modified Capabilities

None.

## Impact

- New files: `src/landcover/serve_ml.py`, `src/landcover/serve_llm.py`, `sql/serving.sql`, `docker/serve/Dockerfile`, `tests/test_serve_ml.py`, `tests/test_serve_llm.py`.
- Changed files: `pyproject.toml` and `uv.lock` (group `serve` with the PyTorch CPU index and conflicts with `nn` and `rag`; `prometheus-client` as a project dependency; `httpx` in `dev` for the test client), `Makefile` (target `images`), `docker-compose.yml` (`mlflow:5000` added to `--allowed-hosts`, so a container on the Compose network can reach the registry), `README.md`, `docs/design.md` (Sections 6.2 and 6.3) and the local, ignored `docs/design.uk.md`.
- Database: a new schema `serving` in `landcover`, created by the ML service. Existing schemas are untouched.
- Not edited: Sections 5.1 and 6.8 of the design document, which the retrieval index includes, so the index version does not change; `retrieval.toml`; `prompts/`; the registry.
- Out of scope: Kubernetes manifests, MLflow in the cluster, loading images into Minikube, authentication on MLflow, Prometheus, Grafana, the drift job, the reference statistics, the dark-image threshold value, the replay script, alerts, the one-command bring-up, the Lab 4 scorecard rows, the revision of Sections 5.5, 6.1, 6.6, 6.7, 6.9 and 7.3, and the `lab-4` tag.

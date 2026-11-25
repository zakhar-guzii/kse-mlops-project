# Design

## Context

See proposal.md for the motivation and the decision tables. Current state that shapes the approach:

- **Registry.** `landcover-segmenter` has version 1 (random forest, 36.9 MB artifact) and version 2 (U-Net, 78.4 MB), and `champion` points to 2. Each version is a pyfunc model whose `Segmenter.load_context` calls `landcover.models.load_predictor(kind, path)`; each stores its own copy of `code/landcover` and a `requirements.txt`. The MLflow server proxies artifacts. In MLflow 3.16.1, `mlflow.models.get_model_info("models:/…@champion")` returns `registered_model_version = None`, while `MlflowClient().get_model_version_by_alias(name, alias).version` returns `"2"`. Downloads through the proxy need `MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false`, as in the `Makefile`.
- **Lab 3 code to reuse.** `retrieval.load_config`, `embedder`, `retrieve`, `check_index`, `index_version`, `documents`, `load_manifest`; `answer.load_llm`, `read_prompt`, `fill`, `passages`, `cited`, `chat`. `answer.server_build` already checks that the server serves the configured model.
- **Measured inference on the M4 Pro CPU.** U-Net 0.32 s per 512×512 tile with one thread and 0.36 s with two; load about 1 s; peak resident memory of the process 1.5 GB. Random forest 0.15 s per tile on all cores. The 64 training tiles have brightness percentiles p1 63.3, p50 114.4 and p99 220.5.
- **Packages.** FastAPI 0.165.0, uvicorn 0.54.0 and prometheus-client 0.26.0 are the current releases and are already in `uv.lock` (the first two through `mlflow-skinny`). The FastAPI test client needs `httpx` 0.28.1, which is locked only through the `demo` group. torch 2.15.0 for linux/aarch64 is 483.7 MB from PyPI plus at least 1.4 GB of CUDA wheels; the `+cpu` wheel from `https://download.pytorch.org/whl/cpu` is 170.7 MB. A scratch resolution with the group of Decision 6 locked in 1.4 s and gave `torch==2.15.0+cpu` on Linux for `serve` while `nn` and `rag` kept the PyPI build.
- **Local stack.** Compose runs MLflow with `--allowed-hosts=localhost:5001,127.0.0.1:5001,localhost:5000`, so a container that calls `http://mlflow:5000` on the Compose network is refused until `mlflow:5000` is added. A container on Docker Desktop reaches a host service bound to `127.0.0.1` through `host.docker.internal` (checked with a host HTTP server and a curl container), so `make llm-server` stays as it is.
- **Embedding model.** `intfloat/multilingual-e5-small` at revision `614241f…` holds `model.safetensors` (470.6 MB) next to ONNX, OpenVINO and `pytorch_model.bin` copies of similar size; SentenceTransformer downloads only the files it loads.

## Goals / Non-Goals

**Goals:**
- Two images that run on the course Mac's Docker and later in Minikube unchanged; configuration only through environment variables.
- Contracts the next three changes build on: environment variables, health paths, port, metric names, request log table.
- The missing-model case reproducible with one `docker run`.

**Non-Goals:**
- Concurrency beyond one request at a time per ML process; horizontal scaling is a replica count in `add-lab4-cluster`.
- Authentication, TLS, request quotas.
- A typed client or OpenAPI customisation beyond what FastAPI generates.

## Decisions

### 1. Two modules, one per service, in the existing package

`src/landcover/serve_ml.py` and `src/landcover/serve_llm.py`, each with a module-level FastAPI `app` started by `uvicorn landcover.serve_ml:app --host 0.0.0.0 --port 8000` (and `serve_llm`). Both listen on port 8000. The ML module also holds the pure function `observe(rgb, valid, mask)` that returns the features and class fractions of Decision 4; the reference builder of `add-lab4-drift-alert` imports it, so both sides of a drift comparison use one definition.

Alternative: a separate package or a shared `serving` module for health and metrics helpers. Rejected: the shared part is a few lines per service.

### 2. ML model loading: alias to number once, pyfunc by number, background retry

A daemon thread started in the FastAPI lifespan runs until the first success: run `sql/serving.sql`, resolve `MODEL_NAME@MODEL_ALIAS` with `get_model_version_by_alias`, then `mlflow.pyfunc.load_model(f"models:/{name}/{version}")`. On failure it stores the reason (`alias champion not found for landcover-segmenter`, `registry unreachable: …`) and retries after `LOAD_RETRY_SECONDS` (default 10). After success the version never changes until the process restarts.

The service imports its own `landcover` package before loading. MLflow then prepends the artifact's `code/` to `sys.path`, but `landcover` is already in `sys.modules`, so the pickled `Segmenter` (`landcover.tracking`) and its `load_context` resolve to the image's code. The image tag therefore names the code that runs any version's weights. An incompatible version fails to load and keeps the service not ready.

Alternatives: load `models:/name@alias` directly, and read the version from the response of a second registry call. Rejected because the alias may move between the two calls and the service would report a version it did not load. Or exit on failure and let Kubernetes restart the container. Rejected because the pod enters CrashLoopBackOff with growing delays and the health endpoint never reports "not ready", which is the case the lab asks to show.

### 3. ML request path

`POST /predict` is a plain `def` endpoint, so FastAPI runs it in its thread pool. The endpoint reads the body (refused above `MAX_BYTES`, default 16 MiB) and decodes it with `rasterio.MemoryFile`. It refuses the input when the dtype is not `uint8`, there are fewer than three bands, or `width × height` exceeds `MAX_PIXELS` (default 1,048,576, i.e. 1024×1024).

Valid pixels are those where the dataset masks of bands 1–3 are all non-zero. An image with no valid pixel is refused. Prediction and the log write run under one process-wide lock. Invalid pixels are set to 255 in the mask. The mask is written as a deflate GeoTIFF with the source CRS and transform when present and nodata 255, and returned base64-encoded.

Error statuses:

| Status | Cause |
|---|---|
| 400 | decode failure, wrong dtype or band count, no valid pixel |
| 413 | above the byte or pixel limit |
| 503 | model not loaded |
| 500 | prediction or log failure |

The image sets `OMP_NUM_THREADS=1`: one thread was the fastest measured setting, and the default thread count follows the node's cores rather than the container's CPU limit.

Response fields:

| Field | Content |
|---|---|
| `request_id` | UUID; also the key of the log row |
| `model_name`, `model_version`, `image_commit` | what produced the mask |
| `width`, `height`, `valid_px` | grid size and valid pixel count |
| `features` | `mean_r`, `mean_g`, `mean_b`, `brightness` |
| `class_shares` | eight values keyed by class name |
| `dark_warning` | boolean, or null without a threshold |
| `mask` | base64-encoded GeoTIFF |

A refused request returns the same `request_id` and `reason` as FastAPI's `detail`.

`ponytail:` the lock serialises requests in one process, matching the one-worker design of Section 6.3; scale with replicas.

### 4. Request log contract

`sql/serving.sql`, idempotent:

```sql
CREATE SCHEMA IF NOT EXISTS serving;
CREATE TABLE IF NOT EXISTS serving.predictions (
    request_id    uuid PRIMARY KEY,
    received_at   timestamptz NOT NULL,
    model_name    text NOT NULL,
    model_version text NOT NULL,
    image_commit  text NOT NULL,
    outcome       text NOT NULL CHECK (outcome IN ('ok', 'invalid', 'error')),
    reason        text,
    source_id     text,
    width integer, height integer, valid_px integer,
    mean_r real, mean_g real, mean_b real, brightness real,
    share_bareland real, share_rangeland real, share_developed real, share_road real,
    share_tree real, share_water real, share_agriculture real, share_building real,
    dark_warning  boolean,
    mask          bytea
);
CREATE INDEX IF NOT EXISTS predictions_received_at ON serving.predictions (received_at);
```

A request refused with 503 before a model is loaded is not served and writes no row. Feature and share columns are null unless `outcome = 'ok'`. Means are over valid pixels on 0–255, brightness is their mean, and each share is a class's pixel count over valid pixels (Section 6.6). `received_at` is set by the service when the body arrives. The drift job selects `outcome = 'ok'` rows by `received_at` and groups by `model_version`.

Each request opens one connection with `psycopg.connect(WAREHOUSE_DSN, connect_timeout=3)`. `ponytail:` a connection per request, about 5 ms; add a pool if request rates reach hundreds per second.

Alternative: a JSON-lines file on a volume. Rejected: the drift CronJob is a separate pod, and a file would need a shared volume while PostgreSQL is already in the stack.

### 5. LLM service

The lifespan loads `retrieval.load_config()`, `answer.load_llm()` with `base_url` replaced by `LLM_BASE_URL` when set, `prompts/rag.md` and its hash through `read_prompt`, and the embedder. It also computes the expected index version from `documents(load_manifest())` once.

`POST /ask` takes `{"question": str}`, 1 to `MAX_QUESTION_CHARS` (default 2000) characters. It opens a connection, checks the index version, retrieves `top_k` rows, fills the prompt with `passages(rows)` and calls `chat(llm, text, llm["max_tokens"])`. It returns:

- `answer`;
- `sources`: for each number from `cited(answer)` between 1 and k, its `n`, `doc_id`, `doc_version` and `locator`;
- `model`, `top_k`, `index_version`, `prompt_hash` and `image_commit`;
- `tokens_in`, `tokens_out`, `retrieval_s` and `generation_s`.

The call to the text model has the 120 s timeout of `chat`. A failure of the server or the database returns 503 with the reason.

`/health/ready` makes two checks, each with a 2 s timeout:

- `GET {base_url}/models` returns the configured model ID;
- `SELECT index_version FROM retrieval.index_meta` equals the expected version.

The image downloads the embedding model at build time by calling `retrieval.embedder(load_config())` with `HF_HOME=/opt/hf`. This fetches exactly the files SentenceTransformer loads, at the revision in `retrieval.toml`, and proves that they load. The image then sets `HF_HUB_OFFLINE=1`.

Alternative: download on start-up into an emptyDir. Rejected: every pod start would depend on Hugging Face and add about 490 MB of transfer.

### 6. Dependencies

`pyproject.toml` gains:

- `prometheus-client==0.26.0` in the project dependencies;
- `httpx==0.28.1` in `dev`;
- a group `serve` with `torch==2.15.0`, `torchvision==0.29.2`, `segmentation-models-pytorch==0.5.0`, `timm==1.0.31` and `sentence-transformers==6.3.0`;
- `[tool.uv.sources]` mapping `torch` and `torchvision` to an explicit index `pytorch-cpu` (`https://download.pytorch.org/whl/cpu`) for group `serve`;
- `[tool.uv] conflicts` between `serve` and `nn`, and between `serve` and `rag`.

On macOS the CPU index serves the same `2.15.0` wheel, so local runs of the services behave like the images. FastAPI and uvicorn stay transitive through `mlflow`, at the locked versions.

Both images install the same group, so they share one dependency layer. The ML image carries sentence-transformers (about 15 MB) and the LLM image carries segmentation-models-pytorch and timm (about 3 MB). That is cheaper than two groups and two resolutions.

Alternative: platform markers selecting the CPU index on Linux. Rejected: Colab training needs the CUDA build on Linux.

### 7. Dockerfile and build command

`docker/serve/Dockerfile`, multi-stage:

- **`base`**:
  - starts from `python:3.12.13-slim-trixie` and copies `uv` from `ghcr.io/astral-sh/uv:0.13.9`;
  - runs `uv sync --locked --no-dev --group serve --no-install-project` with a cache mount, using only `pyproject.toml` and `uv.lock`;
  - copies the tree and runs `uv sync --locked --no-dev --group serve`;
  - sets `ARG GIT_COMMIT`, `ENV IMAGE_COMMIT=$GIT_COMMIT`, `LABEL org.opencontainers.image.revision=$GIT_COMMIT`, `ENV OMP_NUM_THREADS=1 MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false PYTHONPATH=src`;
  - runs as a non-root user and exposes port 8000.
- **`ml`** runs `uvicorn landcover.serve_ml:app`.
- **`llm`** runs the embedding download of Decision 5 and `uvicorn landcover.serve_llm:app`.

`make images`:

```make
images:
	@git diff --quiet HEAD || { echo "uncommitted changes to tracked files; commit them first" >&2; exit 1; }
	for target in ml llm; do \
		git archive HEAD | docker build --target $$target --build-arg GIT_COMMIT=$$(git rev-parse HEAD) \
			-t landcover-$$target:$$(git rev-parse HEAD) -f docker/serve/Dockerfile - || exit 1; \
	done
```

`git archive HEAD` as the build context makes the image content equal the commit by construction. Ignored and untracked files cannot enter, so no `.dockerignore` is needed. The refusal covers staged and unstaged edits of tracked files. Untracked files are harmless because they never reach the archive.

Alternatives: `docker build .` with a `.dockerignore` and a dirty check. Rejected: a forgotten ignore pattern ships local files such as `runs/` or `.env`. Or a short SHA. Rejected: the full SHA is unambiguous and fits Docker's 128-character tag limit.

### 8. Configuration contract

| Variable | Service | Default |
|---|---|---|
| `MLFLOW_TRACKING_URI` | ML | none (required) |
| `MODEL_NAME` | ML | `landcover-segmenter` |
| `MODEL_ALIAS` | ML | `champion` |
| `WAREHOUSE_DSN` | both | none (required; a Secret in the cluster) |
| `DARK_BRIGHTNESS` | ML | unset, no warning |
| `MAX_PIXELS`, `MAX_BYTES` | ML | 1,048,576 and 16 MiB |
| `LOAD_RETRY_SECONDS` | ML | 10 |
| `LLM_BASE_URL` | LLM | `base_url` of `retrieval.toml` |
| `MAX_QUESTION_CHARS` | LLM | 2000 |

`IMAGE_COMMIT` comes from the image.

### 9. Metrics contract

One uvicorn process per container, so the default `prometheus_client` registry is exact. `/metrics` is a route that returns `generate_latest()` with `CONTENT_TYPE_LATEST`, which avoids the trailing-slash redirect of a mounted ASGI app.

| Metric | Type | Labels | Service |
|---|---|---|---|
| `landcover_requests_total` | counter | `endpoint`, `outcome` (`ok`, `invalid`, `error`, `unavailable`), `model_version` (ML only, empty before load) | both |
| `landcover_request_seconds` | histogram | `endpoint`; ML buckets 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10; LLM buckets 0.5, 1, 2.5, 5, 10, 15, 20, 30, 60, 120 | both |
| `landcover_model_loaded` | gauge | — | ML |
| `landcover_llm_stage_seconds` | histogram | `stage` (`retrieve`, `generate`) | LLM |
| `landcover_llm_tokens_total` | counter | `direction` (`in`, `out`) | LLM |

Prometheus adds `job` and `instance`. Health and metrics routes are not instrumented.

### 10. Tests

These run in `make test` without the `serve` group, a registry or a text model server.

**`tests/test_serve_ml.py`** uses the FastAPI test client with the loader replaced by a rule predictor:
- a 512×512 GeoTIFF returns a mask on the same grid and transform;
- a PNG returns a mask without a CRS;
- a pixel masked as invalid gets 255 and is excluded from the means;
- garbage bytes give 400 and a 16-bit image gives 400;
- an image above the limit gives 413 before prediction;
- with a failing loader, `/health/live` gives 200 and `/health/ready` and `/predict` give 503 with the reason; once the loader succeeds, both give 200;
- `/metrics` counts as in the specification;
- `observe()` returns the known values for a constructed image.

With `TEST_DSN`, a fresh database gets the schema twice without error, a served request writes one row with the response's request ID, and a broken DSN gives 500.

**`tests/test_serve_llm.py`** uses a fake embedder and search and a stubbed `chat`:
- sources follow the cited numbers, and numbers above k are dropped;
- an empty question gives 422 without a call;
- a server error gives 503 and an `error` count;
- readiness gives 503 naming the address when the models request fails.

### 11. Documents

A README section "Lab 4: services" gives:

- `make images` and the two image sizes;
- the `docker run` commands on the Compose network with the environment of Decision 8;
- one `/predict` and one `/ask` with `curl` and the start of their output;
- the missing-model block: `docker run … -e MODEL_ALIAS=missing`, then `curl -i` of `/health/live`, `/health/ready` and `/predict` and the service's log line, pasted as captured;
- the promotion check: `make champion VERSION=1`, a container restart and the response reporting version 1, then `make champion VERSION=2` back.

In `docs/design.md`:

- **Section 6.2:** the Lab 4 paragraph names the two services, the port, the health paths and the request log.
- **Section 6.3:** a paragraph "Course service (Lab 4)" states that the course serves synchronous single-image requests within the pixel limit, names the measured per-tile latency, and lists what remains product description: queue, workers, leases, tiling.

The same passages go into the local `docs/design.uk.md`. Sections 5.1 and 6.8 are not edited.

## Risks / Trade-offs

- [The pickled `Segmenter` of a version was written by older code that the image no longer has] → Loading fails, readiness stays 503 with the reason, and the operator rolls the alias back. Versions 1 and 2 are loaded by the image in task 4.3 before the change is done.
- [U-Net memory in the container exceeds what a Minikube pod can get next to MLflow, PostgreSQL and the monitoring stack] → Measure peak memory for a 512×512 and a 1024×1024 input in the container (task 4.2) and record it for the resource limits of `add-lab4-cluster`; lower `MAX_PIXELS` if 1024×1024 does not fit in 2 GiB.
- [`host.minikube.internal` does not reach a host service bound to `127.0.0.1` the way `host.docker.internal` does] → Checked here only for Docker Desktop. `add-lab4-cluster` checks it first; the fallback binds llama-server to the Docker gateway address only, not `0.0.0.0`.
- [CI's uv 0.11.21 reads the lock with group conflicts and a group-scoped index differently from local uv 0.13.9] → `make setup` on CI is part of task 1.1's verification; if it fails, pin CI's uv to the local version.
- [The image is large] → Estimated at 1.3–1.6 GB for ML and 0.5 GB more for LLM, sharing the dependency layer. Measured and recorded in the README (task 4.1). Further cuts, such as dropping pandas and pyarrow through `mlflow-skinny`, are not made because `mlflow.pyfunc` needs the full package.
- [The serialising lock limits throughput to about 3 U-Net tiles per second per pod] → Enough for "a few hundred requests per window" (lab Notes); more replicas if not.
- [A request whose log write fails is lost to monitoring] → It returns 500 and is counted as `error`, so the gap is visible on the dashboard.

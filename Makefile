.PHONY: setup lint test up down airflow-password sample data pull-data train import register champion reproduce train-remote retrieval-index retrieval-eval llm-server answer-eval images cluster

# Credentials for DVC and Compose come from the untracked .env (see .env.example).
-include .env
export
# MLflow clients: the server proxies artifacts, so no store credentials or presigned URLs are needed.
MLFLOW_TRACKING_URI ?= http://localhost:5001
MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD = false
PYTHONPATH = src

setup:
	uv sync --locked

lint:
	uv run --locked ruff check .

test:
	uv run --locked pytest -q

up:
	docker compose up -d --build --wait

down:
	docker compose down

airflow-password:
	docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated

# Fetch the sample from the source and fail unless it hashes to the committed data/raw.dvc.
# make data also seeds the Compose store; make cluster needs only the sample.
sample:
	uv run --locked python scripts/fetch_sample.py
	uv run --locked dvc commit -f -q data/raw.dvc
	git diff --exit-code HEAD -- data/raw.dvc

data: sample
	uv run --locked dvc push

pull-data:
	uv run --locked dvc pull

# Training and MLflow. MODEL is rule, rf or unet; ARGS passes parameters to the training command.
# The U-Net needs the nn dependency group (torch), also to log, import or register it.
NN = $(if $(or $(filter unet,$(MODEL)),$(findstring unet-,$(RESULT))),--group nn)

# Train on the committed tree, then log the result.
train:
	result=$$(uv run --locked $(NN) python -m landcover.train $(MODEL) $(ARGS)) && \
		uv run --locked $(NN) python -m landcover.tracking log "$$result"

# Log an existing result directory, e.g. RESULT=runs/unet-1a2b3c4.
import:
	uv run --locked $(NN) python -m landcover.tracking log $(RESULT)

register:
	uv run --locked $(NN) python -m landcover.tracking register $(RUN)

champion:
	uv run --locked python -m landcover.tracking champion $(VERSION)

reproduce:
	uv run --locked python -m landcover.tracking reproduce $(VERSION) $(if $(GPU),--gpu $(GPU))

# Train the U-Net of the pushed HEAD on Colab (L4 by default), then log the result.
# Only scripts/remote_train.py is sent; the session is stopped on success and on failure.
train-remote:
	uv run --locked --group nn python -m landcover.remote $(or $(GPU),L4) $(ARGS)

# Lab 3: rebuild the retrieval index from corpus/ and retrieval.toml on the host. The first run downloads
# the embedding model (471 MB) from Hugging Face; later runs use its cache.
WAREHOUSE_DSN ?= postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:5433/landcover

retrieval-index:
	uv run --locked --group rag python -m landcover.retrieval index

# Evaluate eval/questions.toml against the current index and log one run to MLflow (experiment
# landcover-retrieval). Refuses an uncommitted tree and a stale index. TOP_K=<n> overrides top_k for one run.
retrieval-eval:
	uv run --locked --group rag python -m landcover.retrieval eval $(if $(TOP_K),--top-k $(TOP_K))

# Lab 3: the text model. Builds llama-server at the pinned llama.cpp release once (Xcode command line tools;
# CMake comes from PyPI through uvx), downloads the pinned GGUF file once (6.98 GB, resumable), checks its
# SHA-256 on every start, then runs the server in the foreground on 127.0.0.1:8081. The prompt cache is capped at
# 2 GiB so the server fits next to Minikube (Lab 4); it only reuses evaluated prefixes, answers are unchanged.
# --alias must equal model in the [llm] table of retrieval.toml.
LLAMA_TAG = b12359
LLAMA_COMMIT = b1b770d90
LLAMA_DIR = models/llama.cpp
LLAMA_SERVER = $(LLAMA_DIR)/build/bin/llama-server
CMAKE = uvx --from cmake==3.31.6 cmake
LLM_REPO = https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/resolve/29d097773436b69ff9feafd636ab4cf873786537
LLM_FILE = models/gemma-4-12b-it-qat-q4_0.gguf
LLM_SHA256 = 93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b

# A partial clone, not a shallow one: llama.cpp numbers its build by the commit count.
$(LLAMA_SERVER):
	test -d $(LLAMA_DIR) || git clone --filter=blob:none --branch $(LLAMA_TAG) \
		https://github.com/ggml-org/llama.cpp $(LLAMA_DIR)
	test "$$(git -C $(LLAMA_DIR) rev-parse --short=9 HEAD)" = $(LLAMA_COMMIT)
	$(CMAKE) -S $(LLAMA_DIR) -B $(LLAMA_DIR)/build -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON -DLLAMA_CURL=OFF
	$(CMAKE) --build $(LLAMA_DIR)/build --target llama-server -j

$(LLM_FILE):
	mkdir -p models
	curl -L --fail -C - -o $@.part $(LLM_REPO)/$(notdir $@)
	echo "$(LLM_SHA256)  $@.part" | shasum -a 256 -c
	mv $@.part $@

llm-server: $(LLAMA_SERVER) $(LLM_FILE)
	echo "$(LLM_SHA256)  $(LLM_FILE)" | shasum -a 256 -c
	$(LLAMA_SERVER) -m $(LLM_FILE) --alias gemma-4-12b-it-qat-q4_0 \
		--host 127.0.0.1 --port 8081 --ctx-size 8192 --parallel 1 --cache-ram 2048

# Answer eval/questions.toml with prompts/plain.md and no retrieval, judge each answer with prompts/judge.md,
# and log one run to MLflow (experiment landcover-answers). Needs make llm-server and a clean tree.
# TOP_K=<n> retrieves n passages per question from the current index and answers with prompts/rag.md
# (group rag; refuses a stale index).
answer-eval:
	uv run --locked $(if $(TOP_K),--group rag) python -m landcover.answer eval $(if $(TOP_K),--top-k $(TOP_K))

# Lab 4: build both service images from the committed tree, tagged with the full commit SHA.
# The context is `git archive HEAD`, so uncommitted and ignored files never enter an image;
# a tree with uncommitted changes to tracked files is refused so no edit is expected in it.
images:
	@git diff --quiet HEAD || { echo "uncommitted changes to tracked files; commit them first" >&2; exit 1; }
	for target in ml llm; do \
		git archive HEAD | docker build --target $$target --build-arg GIT_COMMIT=$$(git rev-parse HEAD) \
			-t landcover-$$target:$$(git rev-parse HEAD) -f docker/serve/Dockerfile - || exit 1; \
	done

# Lab 4: one command from a clean clone. Starts Minikube, builds the images of HEAD in its Docker daemon, fetches
# the data sample, deploys PostgreSQL, MLflow and both services (k8s/landcover.yaml), seeds an empty registry,
# builds the retrieval index and sends a smoke request to /predict (and /ask when make llm-server is running).
MINIKUBE_MEMORY ?= 6144
MINIKUBE_CPUS ?= 4

cluster:
	scripts/cluster.sh

.PHONY: setup lint test up down airflow-password data pull-data train import register champion reproduce train-remote

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

# Fetch the sample from the source, fail unless it hashes to the committed data/raw.dvc, seed the store.
data:
	uv run --locked python scripts/fetch_sample.py
	uv run --locked dvc commit -f -q data/raw.dvc
	git diff --exit-code HEAD -- data/raw.dvc
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

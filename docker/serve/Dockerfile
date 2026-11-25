# Lab 4 service images, targets ml and llm. Build with `make images`: the context is `git archive HEAD`,
# so an image holds exactly the files of the commit in its tag.

FROM python:3.12.13-slim-trixie AS deps
# The rasterio wheel bundles GDAL but links the system expat, which the slim image lacks.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH PYTHONPATH=/app/src
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# Group serve: CPU-only torch (pyproject.toml). Both targets share this layer.
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --group serve --no-install-project

# The embedding model at the revision in retrieval.toml; rebuilt only when that file or retrieval.py changes.
FROM deps AS embedding
COPY retrieval.toml ./
COPY src/landcover/retrieval.py src/landcover/
RUN HF_HOME=/opt/hf python -c "from landcover import retrieval; retrieval.embedder(retrieval.load_config())"

FROM deps AS app
COPY . .
RUN useradd --system --uid 1000 --create-home app
ARG GIT_COMMIT
LABEL org.opencontainers.image.revision=$GIT_COMMIT
# One torch thread: the fastest measured setting, and the default follows the node, not the CPU limit.
ENV IMAGE_COMMIT=$GIT_COMMIT OMP_NUM_THREADS=1 MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false \
    MLFLOW_DISABLE_AGENT_HINT=1 MLFLOW_ENABLE_ARTIFACTS_PROGRESS_BAR=false
USER app
EXPOSE 8000

FROM app AS ml
CMD ["uvicorn", "landcover.serve_ml:app", "--host", "0.0.0.0", "--port", "8000"]

FROM app AS llm
COPY --from=embedding /opt/hf /opt/hf
ENV HF_HOME=/opt/hf HF_HUB_OFFLINE=1
CMD ["uvicorn", "landcover.serve_llm:app", "--host", "0.0.0.0", "--port", "8000"]

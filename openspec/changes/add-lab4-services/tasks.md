# Tasks

Follow [design.md](design.md) and the three specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`. Do not add Kubernetes manifests, Prometheus or Grafana configuration, a drift job, a replay script, reference statistics or alerts; they belong to `add-lab4-cluster`, `add-lab4-monitoring` and `add-lab4-drift-alert`. Do not edit Sections 5.1 or 6.8, `retrieval.toml`, `prompts/` or the registry's versions and alias (task 4.4 moves the alias and restores it). Do not archive any change and do not add licence checks.

## 1. Dependencies and schema

- [ ] 1.1 Add the group `serve`, the `pytorch-cpu` index, the group-scoped sources and the two conflicts, `prometheus-client` to the project dependencies and `httpx` to `dev`, as in design Decision 6, and run `uv lock`. Verify `uv export --locked --no-dev --group serve --no-hashes` lists `torch==2.15.0+cpu ; sys_platform != 'darwin'`; `--group nn` and `--group rag` still list `torch==2.15.0` with `nvidia-cudnn-cu13`; `make setup`, `make lint` and `make test` pass; and CI passes on a pushed branch (design Risks, uv version).
- [ ] 1.2 Add `sql/serving.sql` as in design Decision 4. Verify `psql` applies it twice to a scratch database without error and `\d serving.predictions` shows the columns of the decision.

## 2. ML service

- [ ] 2.1 Add `observe()` and the decoding, validation and mask encoding of design Decision 3 to `src/landcover/serve_ml.py`, with their tests of Decision 10. Verify the constructed image gives the expected means, brightness and shares, a masked pixel becomes 255 and is excluded, a PNG mask has no CRS, a GeoTIFF mask keeps the transform, and `make test` passes.
- [ ] 2.2 Add the app: the lifespan with the background loader of Decision 2, `/predict`, `/health/live`, `/health/ready`, `/metrics` of Decisions 3 and 9 and the log write of Decision 4. Add the tests of Decision 10 with a rule predictor, including the `TEST_DSN` tests. Verify the scenarios of `specs/segmentation-service/spec.md` that do not need a registry pass as tests, and `make test` passes with and without `TEST_DSN`.
- [ ] 2.3 Run the service on the host against the Compose stack: `uv run --locked --no-dev --group serve uvicorn landcover.serve_ml:app` with `MLFLOW_TRACKING_URI=http://localhost:5001` and `WAREHOUSE_DSN` on port 5433. Verify `/health/ready` turns 200 with `model_version` 2, a dev tile through `curl --data-binary` returns a 512×512 mask whose class IDs equal `models.load_predictor("unet", "runs/unet-c1f77a3/model.pt")` on the same tile, and one `ok` row exists in `serving.predictions`.

## 3. LLM service

- [ ] 3.1 Add `src/landcover/serve_llm.py` as in design Decisions 5 and 9, with the tests of Decision 10. Verify the scenarios of `specs/assistant-service/spec.md` pass as tests with the fakes, and `make test` passes.
- [ ] 3.2 Run it on the host with `make llm-server` up and the current index. Verify `/health/ready` gives 200; "What does the value 255 mean in the output mask?" returns an answer whose sources include `export-contract` Section 5.1; top-k, model name and prompt hash equal those of `retrieval.toml` and `prompts/rag.md`; with the server stopped, `/health/ready` gives 503 naming the address.

## 4. Images

- [ ] 4.1 Add `docker/serve/Dockerfile` and the `images` target of design Decision 7, and add `mlflow:5000` to `--allowed-hosts` in `docker-compose.yml`. Ask the author to commit or approve the commit, then run `make images`. Verify both tags equal `git rev-parse HEAD`; `docker inspect` shows the label and `IMAGE_COMMIT`; the images contain no `.env`, `runs/` or `models/`; `python -c "import torch; print(torch.__version__)"` in the ML image prints `2.15.0+cpu`. With a tracked file edited, `make images` exits non-zero and builds nothing. Record both image sizes for the README.
- [ ] 4.2 Run the ML image on the Compose network (`--network kse-mlops-project_default`, `MLFLOW_TRACKING_URI=http://mlflow:5000`, `WAREHOUSE_DSN` on `postgres`). Verify it becomes ready with version 2 and serves a dev tile; with `docker stats`, record peak memory for one 512×512 and one 1024×1024 input; lower `MAX_PIXELS` in Decision 8 and the specification if 1024×1024 needs more than 2 GiB.
- [ ] 4.3 Reproduce the missing model: run the ML image with `MODEL_ALIAS=missing` and capture `curl -i` of `/health/live`, `/health/ready` and `/predict` and the loader's log line. Verify the captured output shows 200, 503 with the alias named, and 503. Then create alias `missing` on version 1 with `MlflowClient().set_registered_model_alias`. Verify the running container becomes ready with version 1 without a restart, then delete the alias.
- [ ] 4.4 Prove the alias path with the image: `make champion VERSION=1`, restart the ML container, post a tile and verify the response reports `model_version` 1 and the random forest's mask; `make champion VERSION=2`, restart and verify version 2. Verify `MlflowClient().get_model_version_by_alias("landcover-segmenter", "champion").version` is `"2"` at the end.
- [ ] 4.5 Run the LLM image on the Compose network with `LLM_BASE_URL=http://host.docker.internal:8081/v1` and `make llm-server` up. Verify readiness 200 and one answer as in 3.2. Verify it also starts with `--network none` added only for start-up, showing that the embedding model loads offline from the image (readiness then reports both dependencies down).
- [ ] 4.6 Verify `/metrics` of both containers after the requests of 4.2–4.5 shows the metric names and labels of design Decision 9, with counts equal to the requests sent.

## 5. Documents

- [ ] 5.1 Add the README section "Lab 4: services" of design Decision 11 with the outputs captured in group 4. Verify every command in it runs as written on the current commit, and the missing-model block is pasted, not retyped.
- [ ] 5.2 Revise the Lab 4 paragraphs of Sections 6.2 and 6.3 as in design Decision 11, and the same passages in the local `docs/design.uk.md`. Verify `git check-ignore docs/design.uk.md` succeeds and `make retrieval-index` prints the unchanged index version, showing that Sections 5.1 and 6.8 were not edited.

## 6. Integration check

- [ ] 6.1 Run `openspec validate add-lab4-services --strict`, `make lint`, `make test` with `TEST_DSN` set and `git diff --check`. Verify all pass and the diff of the change touches no file excluded in the preamble.

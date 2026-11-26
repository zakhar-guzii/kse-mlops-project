# KSE MLOps: Land-cover segmentation

GIS specialists need a first land-cover layer for new aerial imagery, which they then check and edit in QGIS. The planned service takes an 8-bit RGB aerial image and returns an eight-class OpenEarthMap (OEM) mask, a colour overlay and a legend. For a georeferenced GeoTIFF it also returns a GeoTIFF layer on the source grid. The design specifies asynchronous inference, operator-approved model updates and a rollback path. [System design](docs/design.md)

Lab 2 implements versioned FLAIR-HUB ingestion, training for three segmentation models and a local MLflow registry. The current `champion` is U-Net version 2, trained on Colab L4. It scored **0.3355 mIoU** on the six-class development control. [Lab 2 results](#results) · [Model demo](#model-demo)

Lab 3 adds the GIS assistant's documentation answers: a versioned retrieval index over five public documents, a local Gemma 4 12B with versioned prompt files, and an evaluation that chose top-k 10, where **25 of 32** answers are judged correct (24 by the reviewed labels) against 16 without retrieval. [Lab 3 answers](#lab-3-retrieval-augmented-answers)

## Maturity scorecard

| Property | Evidence a reviewer checks | Added in |
|---|---|---|
| Repository setup and checks | The [lint workflow](.github/workflows/lint.yml) runs `make setup`, `make lint` and `make test` ([Local setup](#local-setup)) | Lab 1 |
| Design document exists and is current | Trace a GeoTIFF from upload to QGIS in design §§2, 6.1 and 6.8, then check the drift decision in §6.6. The [design](docs/design.md) follows the numbered template. | Lab 1 |
| Data versioned | `dvc pull` retrieves the raw data with hash verification, and its identifier is in [data/raw.dvc](data/raw.dvc) ([Raw data](#raw-data)) | Lab 2 |
| Pipeline idempotent | Two runs of 2019 give the same row counts, both pasted under [Ingestion pipeline](#ingestion-pipeline) | Lab 2 |
| Quality gate present | The broken batch fails `quality_check` on purpose, with a screenshot ([Broken batch](#broken-batch)) | Lab 2 |
| Experiments tracked | Every run in MLflow has its parameters, scores, `data_version` and `git_commit` ([Training and logging](#training-and-logging), [Results](#results)) | Lab 2 |
| Models registered with lineage | Both versions carry the data version and code commit. `make reproduce VERSION=1` reproduced the registered random forest on CPU ([Reproduction](#reproduction)). U-Net version 2 carries `champion` ([Results](#results)). | Lab 2 |
| LLM component evaluated | `make answer-eval TOP_K=<n>` logs hit rate, MRR and the judged answer metric for 32 questions; the table compares the plain baseline with top-k 3, 5 and 10, and the judge is checked against reviewed labels ([Lab 3: retrieval-augmented answers](#lab-3-retrieval-augmented-answers), [eval/judge-check-rag.toml](eval/judge-check-rag.toml)) | Lab 3 |
| Prompts versioned | Each prompt is a file in [prompts/](prompts/), and every run of `landcover-answers` carries its `prompt_hash` and `judge_prompt_hash`, the first 12 hex digits of the file's SHA-256 ([Lab 3: LLM baseline](#lab-3-llm-baseline)) | Lab 3 |
| Cost and latency recorded | Every answer run logs tokens in and out, a shadow cost, compute seconds and p50/p95 latency; the columns of the [answer table](#lab-3-retrieval-augmented-answers) give them per run | Lab 3 |
| Services containerized | `make images` builds both images from `git archive HEAD`, tagged with the full commit, and refuses uncommitted changes ([Build](#build)) | Lab 4 |
| Services deployed with health contracts | Both services, MLflow and PostgreSQL ready on Minikube ([Pods and services](#pods-and-services)); with the alias missing the ML pod stays 0/1 and out of the Service's endpoints ([Missing model in the cluster](#missing-model-in-the-cluster)); a promotion and a restart change the reported version with the same image ([Promotion in the cluster](#promotion-in-the-cluster)) | Lab 4 |
| Monitoring scheduled | A CronJob reports every 5 minutes: drift of the served window against the training reference per input feature and predicted class share, mean IoU on labelled quadrants, insufficient data and data age, pushed to Prometheus; the Grafana dashboard from the repository shows two windows ([Lab 4: monitoring](#lab-4-monitoring), [Two windows](#two-windows)) | Lab 4 |
| One command brings the system up | `make cluster` from a clean clone starts Minikube, deploys every component, seeds the registry, passes a smoke request to `/predict` and deploys the monitoring components in 8 minutes cold and 13 s repeated ([Bring-up](#bring-up)) | Lab 4 |

## Lab 1 status

Lab 1 delivers the system design and reproducible development tooling. Documentation, code and OpenSpec artifacts are in English, and the English design is authoritative.

| Path | Contents |
|---|---|
| [docs/design.md](docs/design.md) | The intended service, sections 1–7.4 |
| [docs/diagrams/](docs/diagrams/) | Context, data-flow and deployment views |
| [openspec/](openspec/) | Change proposals and acceptance criteria |
| `pyproject.toml`, `uv.lock`, `Makefile`, `.pre-commit-config.yaml`, [.github/workflows/lint.yml](.github/workflows/lint.yml) | Reproducible setup, lint and CI |

## Local setup

Prerequisites: Git, Make, and uv 0.11.21 in PATH. The project uses Python 3.12.13 from `.python-version` and dependencies pinned in `uv.lock`. uv can obtain a missing project interpreter without replacing the system Python. Initial setup needs network access for missing packages or the interpreter.

```sh
make setup
make lint
uv run --locked pre-commit run --all-files
```

`make setup` installs the locked development environment. `make lint` runs Ruff static checks without modifying files. The pre-commit configuration runs the same locked Ruff command and is retained for Lab 1 and manual checks. Automatic local Git hooks are not installed.

The [lint workflow](.github/workflows/lint.yml) runs `make setup`, `make lint` and `make test` on GitHub for every push and pull request. The unit tests of the pipeline functions need no Docker; the warehouse test runs when `TEST_DSN` names a PostgreSQL server, which the workflow provides, and is skipped otherwise.

## Lab 2: data pipeline

### Local stack

Additional prerequisite: Docker with Compose v2. The stack is PostgreSQL 16, Apache Airflow 3.3.1 (LocalExecutor), the S3-compatible store `pgsty/silo` and the MLflow 3.16.1 tracking server; published ports bind to `127.0.0.1` only.

```sh
cp .env.example .env      # then replace the placeholder passwords
make up                   # build and start; returns when the services are ready
make airflow-password     # password of the Airflow user "admin"
```

MLflow is at <http://localhost:5001> (port 5000 is held by macOS AirPlay), without authentication: it keeps runs in the PostgreSQL database `mlflow` and model files in the bucket `landcover-mlflow`, and proxies the files, so clients need only the address. `curl -fs http://localhost:5001/health` prints `OK`.

`make down` stops the stack; `docker compose down -v` also deletes the warehouse, the Airflow history, the store and MLflow's runs and models (training results stay in `runs/` and can be logged again with `make import`). The databases `airflow` and `mlflow` are created by [sql/warehouse.sql](sql/warehouse.sql), which runs only on an empty volume: a checkout that predates MLflow needs `docker compose down -v` once. After `down -v`, run `make data` again to refill the store (files already in `data/raw` are not downloaded again) and unpause the DAG again (see [Ingestion pipeline](#ingestion-pipeline)): a new Airflow database starts with the DAG paused, and its runs wait as "queued" with no task status.

### Airflow UI

1. Open <http://localhost:8080>.
2. Sign in as `admin` with the password from `make airflow-password`. The password is regenerated whenever the Airflow container is recreated, for example after `make down`.
3. Open **Dags → `landcover_ingest`**:
   - the grid on the left has one column per run and one square per task; click a square, then **Logs**, to read that task's log;
   - the graph button, the third icon at the top left, shows the six tasks in order, as in the screenshot under [Ingestion pipeline](#ingestion-pipeline);
   - **Runs** lists every run: `backfill__<date>` for a year, `manual__<time>` for the broken batch, whose failed `quality_check` log is shown under [Broken batch](#broken-batch).

The silo console is at <http://localhost:9001>: sign in with `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from `.env`. The bucket `landcover-dvc` holds the files DVC pushed, named by their hashes.

### Raw data

The sample is 16 image–label pairs from each of the six FLAIR-HUB domains D080-2017 to D073-2022: for each domain, the patches present in both its `AERIAL_RGBI` and `AERIAL_LABEL-COSIA` archives at commit [`37d52ec`](https://huggingface.co/datasets/IGNF/FLAIR-HUB/tree/37d52ec88c72b5961de6ba3a6fae67686b0c2355) are sorted by tile ID and every k-th is kept. The 192 GeoTIFFs (98 MB) are stored unmodified under `data/raw/<batch_id>/`, which Git ignores. DVC tracks the directory with an S3-type remote, `s3://landcover-dvc` on the local pgsty/silo store ([.dvc/config](.dvc/config)).

On a fresh stack, seed its empty S3 bucket once. The bootstrap downloads the pinned sample from Hugging Face and verifies the committed DVC hash before pushing it.

```sh
make data
```

`make data` runs `make sample`, which fetches the files that are missing and fails unless `data/raw` hashes to `data/raw.dvc`, and then pushes to the store. `make sample` alone needs no store; [Lab 4: cluster](#lab-4-cluster) uses it.

From a clean clone pointing at the populated store, copy its credentials into `.env` and run the following command to retrieve and verify the same files through DVC.

```sh
make pull-data
```

Checksum of what arrives: `6a0c8cc2708d6616c0bfb9f3f5095708.dir`, the DVC hash of `data/raw` in [data/raw.dvc](data/raw.dvc) and the single data version identifier. A second clean checkout with an empty DVC cache reported `193 files fetched and 192 files added`. DVC status reported that the data was up to date.

### Ingestion pipeline

The DAG [`landcover_ingest`](dags/landcover_ingest.py) runs `extract → validate → transform → load → build_features → quality_check` for one batch, using functions from [src/landcover/pipeline.py](src/landcover/pipeline.py). It fills `dwh.tiles` (one row per image–label pair) and `features.tile_features` (derived in SQL, with `feature_version`), defined in [sql/warehouse.sql](sql/warehouse.sql).

Timetable choice: the batch is keyed on `data_interval_start` alone. The schedule is `@yearly` with `CronTriggerTimetable`, where a run's interval starts at its logical date, so the run for 2019-01-01 loads the 2019 batch `D065-2019`. In Airflow 3.3.1, `airflow dags trigger --logical-date` takes the interval from the trigger time, so years are run as one-date backfills. Rerunning a batch replaces its rows.

With the stack running and `data/raw` retrieved:

```sh
set -a; . ./.env; set +a    # credentials for psql below, in every new terminal
docker compose exec airflow airflow dags unpause landcover_ingest   # "No paused DAGs" means already unpaused
# 1. run 2019
docker compose exec airflow airflow backfill create --dag-id landcover_ingest \
  --from-date 2019-01-01 --to-date 2019-01-01 --reprocess-behavior completed
# 2. the command above returns before the tasks finish: repeat this until the run's state is "success"
docker compose exec airflow airflow dags list-runs landcover_ingest
# 3. row counts per batch
docker compose exec postgres psql -U "$POSTGRES_USER" -d landcover -c "SELECT 'dwh.tiles' AS table_name, batch_id, count(*) FROM dwh.tiles GROUP BY batch_id UNION ALL SELECT 'features.tile_features', batch_id, count(*) FROM features.tile_features GROUP BY batch_id ORDER BY 1, 2"
# 4. repeat steps 1 to 3: the second run re-executes every task and the counts stay the same
```

Airflow allows one running backfill per DAG and closes a backfill a few seconds after its last run succeeds; if `backfill create` reports `AlreadyRunningBackfill`, repeat the command.

Row counts after the first and the second run of 2019:

```text
-- after run 1                                    -- after run 2
       table_name       | batch_id  | count              table_name       | batch_id  | count
------------------------+-----------+-------     ------------------------+-----------+-------
 dwh.tiles              | D065-2019 |    16       dwh.tiles              | D065-2019 |    16
 features.tile_features | D065-2019 |    16       features.tile_features | D065-2019 |    16
```

![Successful run of 2019: all six tasks green](docs/screenshots/airflow-run-2019-success.png)

All six years, 2017 to 2022, once the runs above have finished:

```sh
docker compose exec airflow airflow backfill create --dag-id landcover_ingest \
  --from-date 2017-01-01 --to-date 2022-01-01 --reprocess-behavior completed
```

### Broken batch

[tests/fixtures/bad_batch/](tests/fixtures/bad_batch/) holds two synthetic 64×64 image–label pairs in the FLAIR-HUB layout, written with rasterio: random 4-band uint8 images and labels whose every pixel is FLAIR-HUB class ID 1, which crosswalk v1 maps to ignore. The batch passes structural validation, so it reaches the gate, which allows at most 0.90 ignored pixels.

```sh
docker compose exec airflow airflow dags trigger landcover_ingest -c '{"batch_id": "bad-demo"}'
```

`extract` through `build_features` succeed; `quality_check` fails with `ValueError: ignored-pixel share 1.00 exceeds the maximum 0.90 (8192 of 8192 pixels)` and deletes the batch's rows, so neither table holds a `bad-demo` row.

![The quality_check task of the bad-demo run failed](docs/screenshots/airflow-bad-demo-quality-check-failed.png)

## Lab 2: models and tracking

### Split and models

Each batch has one role ([src/landcover/pipeline.py](src/landcover/pipeline.py), `BATCH_ROLES`). A batch is one département in one year, so the control is later in time and from another region than every training tile ([design Section 5.4](docs/design.md#54-experimentation-and-validation)).

| Role | Batches | Use |
|---|---|---|
| Train | D080-2017, D033-2018, D065-2019, D045-2020 (64 tiles) | Pooled into one training set |
| Development control | D017-2021 (16 tiles) | Scores every model and decides `champion` |
| Final holdout | D073-2022 | Not opened by any training or scoring code |

| Model | `MODEL=` | Role | Time on an M4 Pro |
|---|---|---|---|
| Majority class of the training labels | `rule` | Rule-based baseline | about 1 s |
| Random forest on per-pixel texture features, 10,000 pixels per class | `rf` | Trained model; the reference for reproduction | about 30 s |
| U-Net with an EfficientNet-B4 encoder, ImageNet weights, 40 epochs | `unet` | Current champion | about 7 s per epoch on MPS |

All three are scored by one evaluation ([src/landcover/models.py](src/landcover/models.py)): one confusion matrix over every labelled pixel of the development control, and the mean intersection over union (mIoU) of the six classes FLAIR-HUB labels can contain (bareland, rangeland, tree, water, agriculture, building). A prediction of road or developed space counts as a miss.

### Training and logging

With the stack running, on a committed tree:

```sh
make train MODEL=rule
make train MODEL=rf
make train MODEL=unet ARGS="--epochs 40"   # installs torch on first use (dependency group nn)
```

`make train` first runs `python -m landcover.train`. Training checks that the tree is clean and verifies `data/raw` against `data/raw.dvc`. Each completed run publishes its own Git-ignored `runs/<model>-<commit7>-<id>/` directory with the model and `run.json`. The record holds training parameters, the train, development and final batch IDs, lineage, scores and the model file's SHA-256. U-Net records the pinned encoder revision and per-epoch history. CUDA runs also record the GPU name. Use `ARGS` to pass training parameters. For the forest, list them with `PYTHONPATH=src uv run --locked python -m landcover.train rf --help`.

`make train` then logs the result to MLflow, experiment `landcover`. Logging verifies the model file's SHA-256, the data version at the recorded commit and the local raw files. It rescores the model and requires the development mIoU to agree within 0.005 before it creates an MLflow run. A saved result directory can be logged again, for example after `docker compose down -v`:

```sh
make import RESULT=runs/unet-c1f77a3
```

### Registration and promotion

```sh
make register RUN=<run ID>       # add MODEL=unet for a U-Net run
make champion VERSION=<n>
```

`make register` creates a version of `landcover-segmenter`, copies the run's `data_version` and `git_commit` tags, and downloads and loads the model through MLflow. It keeps the version only if a probe tile returns a 512×512 mask of class IDs. `make champion` points the alias at a version. Promote an earlier version to roll back. Any client can load the alias without object-store credentials:

```python
import mlflow  # with MLFLOW_TRACKING_URI=http://localhost:5001
model = mlflow.pyfunc.load_model("models:/landcover-segmenter@champion")
mask = model.predict(rgb)  # rgb: height x width x 3, uint8 -> mask: height x width, class IDs
```

### Reproduction

```sh
make reproduce VERSION=1          # registered CPU random forest in the author’s registry
make reproduce VERSION=2 GPU=L4   # registered U-Net in the author’s registry, via Colab
```

The command uses a temporary worktree at the registered `git_commit` and verifies that `data/raw.dvc` names its `data_version`. It runs `dvc pull` in that commit's locked environment. It trains with the recorded parameters, pins the encoder revision for U-Net, and logs the repeated run under `reproduces=<original run ID>`. It prints both development mIoUs and fails if their difference exceeds the configured tolerance. With `GPU=L4`, Colab fetches and verifies the same pinned data independently and returns the result for local logging. You can omit `GPU` when reproducing on a machine with CUDA.

| Model | Configured tolerance (development mIoU) |
|---|---:|
| Majority-class rule | 0.01 |
| Random forest | 0.01 |
| U-Net | 0.02 |

For the reviewer on a clean clone, follow [Local setup](#local-setup), [Local stack](#local-stack) and [Raw data](#raw-data), then run:

```sh
make train MODEL=rule
make train MODEL=rf
make register RUN=<random-forest-run-id>
make champion VERSION=<registered-version>
make reproduce VERSION=<registered-version>
```

Use the run ID printed by forest training and the version printed by registration. The Compose registry starts empty. This path needs a CPU and the pinned FLAIR-HUB sample. The clean-clone walkthrough registered a forest that returned a 512×512 mask and repeated at 0.1478 mIoU.

The historical Random Forest version was reproduced from commit `07c41af` on 23 November 2026:

```text
version 1: run 4565bb91a82c40de8c83dea560aee462 reproduced by run 77375bfa9d574a74884c68213713593c
development mIoU: original 0.1478, reproduced 0.1478, difference 0.0000, tolerance 0.01
```

U-Net version 2 was retrained twice on Colab L4 from commit `c1f77a3`, with the same DVC data and pinned EfficientNet-B4 encoder revision `c474abe5a8689bd017e9a50b41aa72ac253a63e1`. The original and both repeats scored **0.3355 development mIoU**. The absolute difference was **0.0000** for both, so the tolerance stays at the minimum of **0.02**. The second repeat used an explicit Colab session after automatic allocation returned HTTP 503.

| Run | MLflow ID |
|---|---|
| Original U-Net v2 | `d8c2abf763d5438d93df7dc3dfdda42a` |
| Repeat from the recovered Colab archive | `a3125a89ed3b4cb4888607ad930b9035` |
| Repeat in an explicit Colab session | `befa9a9dd42e46b8ae88d46540b37344` |

### Remote training

The U-Net trains on Colab L4 by default. Remote training needs a Colab Pro account, the official client (`uv tool install google-colab-cli==0.8.0` on Linux and macOS), and the checkout's commit pushed to `origin`. The client can prompt for a browser sign-in.

```sh
git push
make train-remote GPU=L4           # ARGS="--epochs 40" passes training parameters
colab sessions                     # afterwards: no session is listed
```

`make train-remote` checks that the tree is clean and the commit is on `origin` before provisioning. It sends [scripts/remote_train.py](scripts/remote_train.py) and the run arguments to Colab. The runtime clones the public repository at that commit, installs the locked dependencies, fetches and verifies the sample, and trains using the allocated GPU. The command stops the Colab session on completion or failure. It validates the download, publishes a unique local result directory and logs it through the same path as `make import`. Local stack credentials remain on the host.

To use the launcher from a Colab notebook, select an L4 runtime, upload `scripts/remote_train.py` and run `!python remote_train.py --gpu L4 https://github.com/zakhar-guzii/kse-mlops-project.git <commit> --device=cuda`. Download `/content/result.zip`, extract it into `runs/`, release the runtime and pass the extracted directory to `make import RESULT=<directory>`.

### Results

Scores are from the 16 tiles of development batch D017-2021. Each class column shows its IoU and labelled pixel count. [Local MLflow experiment](http://localhost:5001/#/experiments/1)

| Model | Run ID | mIoU | Pixel accuracy | Bareland | Rangeland | Tree | Water | Agriculture | Building |
|---|---|---|---|---|---|---|---|---|---|
| Majority class | `901302cb1dfe4cafa6fc85236091a459` | 0.0456 | 0.2735 | 0.0000 (660,088) | 0.0000 (688,132) | 0.0000 (330,408) | 0.0000 (1,057,240) | 0.2735 (1,035,380) | 0.0000 (14,896) |
| Random forest | `4565bb91a82c40de8c83dea560aee462` | 0.1478 | 0.2558 | 0.2133 (660,088) | 0.2523 (688,132) | 0.3025 (330,408) | 0.0269 (1,057,240) | 0.0658 (1,035,380) | 0.0258 (14,896) |
| U-Net (Colab L4, 40 epochs) | `d8c2abf763d5438d93df7dc3dfdda42a` | 0.3355 | 0.4340 | 0.1823 (660,088) | 0.2031 (688,132) | 0.4748 (330,408) | 0.1615 (1,057,240) | 0.3413 (1,035,380) | 0.6502 (14,896) |

The majority-class rule and random forest used commit `07c41af971fd4d29cf6f51d1f17dae126eaf3eef`. The U-Net used commit `c1f77a319a1a25d6164d01703b89f318ce3174e9`. The model and training code, lockfile and DVC data identifier match across these commits. The U-Net ran in an allocated L4 session, with a median of 2.7 seconds per epoch after the first epoch, excluding provisioning and data preparation. Its archive is stored locally at `runs/unet-c1f77a3.zip`. The extracted weights and metrics were logged with `make import`.

Registered versions of `landcover-segmenter`

| Version | Model | Run ID | `data_version` | `git_commit` | Alias |
|---|---|---|---|---|---|
| 1 | Random forest | `4565bb91a82c40de8c83dea560aee462` | `6a0c8cc2708d6616c0bfb9f3f5095708.dir` | `07c41af971fd4d29cf6f51d1f17dae126eaf3eef` | |
| 2 | U-Net | `d8c2abf763d5438d93df7dc3dfdda42a` | `6a0c8cc2708d6616c0bfb9f3f5095708.dir` | `c1f77a319a1a25d6164d01703b89f318ce3174e9` | `champion` |

### Model demo

Open the [model comparison notebook](notebooks/landcover-model-demo.ipynb) to see three aerial images with reference masks, predictions from all three saved models and a U-Net overlay. The figures and the validation score table are saved in the notebook.

To rerun inference, use the saved result directories `runs/rule-07c41af`, `runs/rf-07c41af` and `runs/unet-c1f77a3`, plus the DVC sample under `data/raw/`. The notebook includes the JupyterLab command with the locked `demo` dependency group and uses the saved weights directly.

## Lab 3: retrieval index

The GIS assistant answers questions about the export package from public documentation, with citations. The corpus has 5 documents: four cleaned Markdown copies in [corpus/](corpus/) (the OpenEarthMap and FLAIR-HUB papers, the USGS NAIP data dictionary and the QGIS raster properties page) and `export-contract`, which is Sections 5.1 and 6.8 of [docs/design.md](docs/design.md), read when the index is built. [corpus/manifest.toml](corpus/manifest.toml) records each copy's source URLs, access date and SHA-256.

With the stack up (see [Local stack](#local-stack)):

```sh
make retrieval-index
```

```
index 5570e99ba60e: 5 documents, 575 chunks (intfloat/multilingual-e5-small, 600/100)
check "What does the value 255 mean in the output mask?" -> export-contract, 5.1 Problem statement, distance 0.160
```

The command checks every copy against its SHA-256 in the manifest, splits each document into chunks that stay inside one section, embeds them on the CPU and replaces the schema `retrieval` of the database `landcover` in one transaction. Before committing, it asks the fixed question above and fails unless a chunk of Section 5.1 is among the top-k results; a failed build leaves the previous index in place. The first line gives the index version, which changes with any document, with the chunking or model settings, or with `INDEX_FORMAT`, the version of the chunking and embedding code; the chunk count and version above change whenever Section 5.1 or 6.8 of the design is edited, while the document count stays 5.

The settings are in [retrieval.toml](retrieval.toml): chunk size and overlap in characters, the embedding model with its pinned revision, and top-k. The command runs on the host with the `rag` dependency group, which `make setup` does not install. The first run downloads the model from Hugging Face (471 MB) and needs network access; later runs use the Hugging Face cache. PostgreSQL, now the `pgvector/pgvector:0.8.7-pg16-trixie` image, is published on `127.0.0.1:5433`; the command connects there with the credentials of `.env` unless `WAREHOUSE_DSN` is set.

## Lab 3: retrieval evaluation

The evaluation set [eval/questions.toml](eval/questions.toml) has 32 questions in English: 6 on `export-contract`, 8 on the QGIS page, 8 on the OpenEarthMap paper, 6 on FLAIR-HUB and 4 on the NAIP dictionary. Each question has a reference answer and one or more sources: a document, a section locator and a short evidence quote copied from that section. Claude (`claude-opus-5-5`) drafted the questions from the corpus; the author read every question, answer and quote against its section. The tests check that every section exists in the chunked corpus, that one of its chunks holds the quote, and that no question names its document or shares four consecutive words with its passage.

A retrieved chunk is a hit when it lies in a cited section and contains that source's evidence quote. Hit rate at k is the share of questions with a hit in the first k chunks; MRR at k is the mean of 1 / rank of the first hit, 0 when there is none.

With the stack up, a current index and a clean working tree:

```sh
make retrieval-eval TOP_K=3
make retrieval-eval TOP_K=5
make retrieval-eval                # top_k of retrieval.toml, 10
```

```
run 1bbbd66d: top_k 5, 32 questions, hit rate 0.656, MRR 0.450, p50 0.011 s, p95 0.013 s (index 5570e99ba60e, questions 5e2556f998a1)
```

The command refuses uncommitted changes and an index that was not built from the committed corpus and `retrieval.toml`. It logs one run to the MLflow experiment `landcover-retrieval` with the settings, the tags `git_commit`, `index_version` and `eval_set` (the first 12 hex digits of the SHA-256 of the question file), both metrics, the seconds of the 32 searches (`retrieval_s`) with their p50 and p95 per question, and `results.json` with each question's first-hit rank and retrieved chunks. A search includes the embedding of the question on the CPU; loading the model does not count.

Index `5570e99ba60e`, evaluation set `5e2556f998a1`, commit `c472b1a1301f18cf228d868ced02d02570c5310f`:

| top-k | Hit rate | MRR | Search p50 | Search p95 | Run ID |
|---|---|---|---|---|---|
| 3 | 0.531 | 0.422 | 0.011 s | 0.013 s | `f01baf6f55854c988c732d28f60d762a` |
| 5 | 0.656 | 0.450 | 0.011 s | 0.013 s | `1bbbd66dfd6343f18be0cc4cc9bc2f21` |
| 10 | 0.844 | 0.473 | 0.011 s | 0.013 s | `c50f9644767e43a0b5b47e243cfeb380` |

The 32 searches took 0.38 to 0.39 s per run. At k = 5, the NAIP dictionary misses 3 of its 4 questions, FLAIR-HUB 3 of 6, the QGIS page 3 of 8, the OpenEarthMap paper 2 of 8 and `export-contract` none of 6. One question moves the hit rate by 3.1 points. The search is exact, so the three rows are cuts of one ranking and cannot fall as k grows. The table shows what a larger k buys; it cannot choose k, which also depends on the answer quality, latency and prompt length measured in [Lab 3: retrieval-augmented answers](#lab-3-retrieval-augmented-answers), which chooses k = 10. They replace runs `1405ba4d9eba46a88121bb6cb7ea97c9`, `c001c9b19cee4abb9b9761b9a655e100` and `a11718188dd549dc8542bd70f145d6f2` on set `d06b7a39c631` and index `56be0057b30e` (hit rate 0.469, 0.594 and 0.750), which replaced runs `14432e325a7340a589863ee502645872`, `04d99fd20ead4599bd42740aa8a4de15` and `78971d105bfe4dc68d57fe40951a5a96` on the first set `0174445a4974`. The set was revised a second time after the review of Lab 3: q08 accepts both ways the QGIS page gives to make a value transparent, q25 and q26 ask about the dataset's published experiments rather than about this project's model, whose crosswalk and split differ, q23 quotes the part of its evidence sentence that one chunk holds whole, and q25 and q28 cite the further passages of FLAIR-HUB that state their answers. q29 still contains the code it asks about: the dictionary lists CNIR, CLR and CIR, so a question asking for the code of colour infrared imagery would have two answers. The index version changed because it now includes `INDEX_FORMAT`; the chunks are the same.

## Lab 3: LLM baseline

The text model is Gemma 4 12B QAT Q4_0, served by `llama-server` from [llama.cpp](https://github.com/ggml-org/llama.cpp) release `b12359` on the Mac host with Metal. Start it in a separate terminal:

```sh
make llm-server
```

The first start clones llama.cpp at tag `b12359` into the ignored directory `models/llama.cpp`, checks that the commit is `b1b770d90` and builds `llama-server` with CMake 3.31.6, which `uvx` takes from PyPI; it needs Git and the Xcode command line tools, and the built server reports build `b12359-b1b770d90`. It then downloads `gemma-4-12b-it-qat-q4_0.gguf` (6.98 GB) from a pinned Hugging Face revision into `models/`; an interrupted download resumes when the command is run again. The file gets its final name only after its SHA-256 matches the one in the `Makefile`, and the command checks the hash again on every start, so a damaged or replaced file stops the command before the server starts. The server listens on `http://127.0.0.1:8081/v1` and speaks the OpenAI chat completions protocol; its address and model name are the table `[llm]` of [retrieval.toml](retrieval.toml).

With the stack and the server up and a clean working tree:

```sh
make answer-eval
```

```
run e6d9e1d6: plain, 32 questions, correct 0.500, tokens 3822 in / 1346 out, p50 1.8 s, p95 2.9 s, shadow cost $0.0211 (prompt e88db3af2e2d, judge a11f648cb1f0, questions 5e2556f998a1)
```

The command sends every question of [eval/questions.toml](eval/questions.toml) to the model with [prompts/plain.md](prompts/plain.md), which holds no retrieved passage, at temperature 0 with at most 256 output tokens. The same model then judges each answer against the question's reference answer with [prompts/judge.md](prompts/judge.md) and returns `correct` or `incorrect` as schema-constrained JSON; an answer that declines or says it does not know is `incorrect`. The command refuses uncommitted changes, a server that does not answer and a server that serves another model. It logs one run named `answer-plain` to the MLflow experiment `landcover-answers` with the model, the server build, `top_k` 0, the tags `git_commit`, `eval_set`, `prompt_hash` and `judge_prompt_hash` (the first 12 hex digits of each prompt file's SHA-256), the metrics, and `results.json` with each answer, its verdict and reason, its tokens and its seconds.

Model `gemma-4-12b-it-qat-q4_0`, llama-server build `b12359-b1b770d90`, answer prompt `e88db3af2e2d`, judge prompt `a11f648cb1f0`, evaluation set `5e2556f998a1`, commit `c472b1a1301f18cf228d868ced02d02570c5310f`:

| Prompt | Answer correct | Tokens in | Tokens out | Shadow cost | Compute | p50 | p95 | Run ID |
|---|---|---|---|---|---|---|---|---|
| plain, no retrieval | 0.500 (16 of 32) | 3,822 | 1,346 | $0.0211 | 58.1 s | 1.76 s | 2.88 s | `e6d9e1d6e94b414f998e2c4862da704d` |

Tokens, compute seconds, cost and latency count the 32 answer calls; latency is the client's wall clock per call. The 32 judge calls used 8,900 tokens in and 1,514 out, which are logged as `judge_tokens_in` and `judge_tokens_out` and are not in the cost. The run cost no money. The shadow cost prices the answer tokens at the Sonnet 5.5 rates of Section 6.7 of the design ($2 and $10 per million in and out), about $0.0007 per question. It is not what Bedrock would bill: Claude's tokenizer would count the same text differently from Gemma's.

The first answer call skips the prompt cache, so `cold_calls` is 1 and the first question has 0 cached tokens. The other 31 calls reused 1 cached token each, not the roughly 70 tokens of the shared instruction. Gemma 4 uses sliding-window attention in part of its layers, and llama.cpp by default keeps only the window for those layers, so the cache cannot be rolled back to a prefix that two prompts share: everything after the first token is evaluated again, while an identical prompt is reused whole (960 prompt tokens, 955 cached, 1.0 s instead of about 4 s). The server log names no reason; it prints only the slot selection. Measured on this build with the command of `make llm-server` and again with `--swa-full` added, which makes the server log "using full-size SWA cache": the plain prompt went from 1 to 86 cached of 102 to 104 tokens and from 0.47 s to 0.14 to 0.24 s of prompt evaluation, and a prompt with five passages (780 to 1,103 tokens) from 1 to 84 to 91 cached tokens and from 2.9 to 3.9 s to 2.4 to 3.5 s, about 0.4 s per call, for 61 MB more memory (3,867 against 3,806 MB). `make llm-server` keeps its flags, so all rows of both Lab 3 answer tables come from one server configuration. In the plain run and the runs at top-k 5 and 10 every later call reused 1 cached token (one call at top-k 5 reused 427), so these calls evaluate their whole prompt and `cold_calls` 1 understates how cold they are; in the run at top-k 3, whose prompts are the shortest with passages, the 31 later calls reused 162 to 180 tokens. A server that reports no cached tokens leaves `cold_calls` out of the run instead of counting its calls as cold. The first call still sends `cache_prompt: false`, which keeps one cold prompt per run whatever the server's flags. `--swa-full` is the first latency lever for Lab 4 (Section 6.3 of the design). Every answer ended with `finish_reason` `stop`. The request sets `reasoning_effort` to `none`: without it, Gemma 4 spent the whole output limit on reasoning text and returned no answer.

The model answered 2 of the 6 `export-contract` questions correctly, which shows that it does not know this project's export package: 7 of 8 on the QGIS page, 1 of 8 on the OpenEarthMap paper, 2 of 6 on FLAIR-HUB and 4 of 4 on the NAIP dictionary. The QGIS page and the NAIP dictionary hold what the model already knows; the gain from retrieval is to be sought in the other three documents.

Measured with the same build and flags during the earlier runs on set `d06b7a39c631`: with the server freshly started and after one run, its physical footprint (`footprint $(pgrep -x llama-server)`) was 3,012 MB, plus 6,666 MB of clean memory-mapped pages of the model file. The server keeps a prompt cache in host memory of up to 8,192 MiB by default (`--cache-ram`), so the footprint grows with use: after several hundred calls in one process it was 9,179 MB.

This row replaces run `8fe988ff4fa94f2d956a189fb9015b8d` (0.469, 15 of 32) on set `d06b7a39c631` with judge prompt `5b291def62c3`. After the review of Lab 3 the set was revised a second time (see [Lab 3: retrieval evaluation](#lab-3-retrieval-evaluation)), and the judge prompt gained a third rule: an answer that states the key fact but adds a false statement about what the question asks is `incorrect`. The baseline's 32 answers are the same as before except q25 and q26, whose questions changed; the extra question judged correct is q25 (see the check below). Run `8fe988ff4fa94f2d956a189fb9015b8d` itself replaced run `736634076b744485a8c19f690101c03c` (0.312, 10 of 32) on the first evaluation set `0174445a4974`. That run showed questions that did not say what they asked about and reference answers holding several facts, which the judge read as all required. The set was revised once: each question describes its subject by its properties, still without a document's name, and each reference answer is one sentence with the direct answer. The judge prompt gained two rules: the key fact is the direct answer to the question, and another name for the same setting counts. Judging these answers with the earlier judge prompt in an unlogged check gave the same 15 of 32, so the rise comes from the revised set.

The judge was checked against labels on the answers of run `e6d9e1d6e94b414f998e2c4862da704d`, in [eval/judge-check.toml](eval/judge-check.toml). Claude (`claude-opus-5-5`) labelled each answer `correct` or `incorrect` by the rubric of `prompts/judge.md` from the question, the reference answer and the answer, before reading any verdict of this run; it had seen the run's printed answer metric and the reviewed labels of the earlier baseline, whose answers are the same except q25 and q26. A script then copied the verdicts in. The author reviewed every label.

| | Label `correct` | Label `incorrect` |
|---|---|---|
| Judge `correct` | 15 | 1 |
| Judge `incorrect` | 1 | 15 |

The judge agrees with the labels on 30 of 32 answers; the rule set before the check required 29. The labels count 16 correct answers, the same as the judge, but not the same ones. q02 says 255 is "No Data", which the label accepts as the invalid pixels of the reference and the judge does not. q25 says that the codes for clear cuts and mixed areas are left out, which only repeats the examples of the question without the codes; the judge accepts it. The check on the earlier baseline agreed on 31 of 32, and the first run's check on 27 of 32, which led to the first revision of the set. Half of the answers are wrong, most of them "I do not know", which any judge rejects easily, so the table says more about rejecting than accepting; the check is repeated on a retrieval-augmented run in [Lab 3: retrieval-augmented answers](#lab-3-retrieval-augmented-answers).

## Lab 3: retrieval-augmented answers

The same evaluation set is answered from retrieved passages at three values of top-k. With the stack and the server up, a current index (`make retrieval-index`) and a clean working tree:

```sh
make answer-eval TOP_K=3
make answer-eval TOP_K=5
make answer-eval TOP_K=10
```

For each question the command retrieves the top-k chunks through the retriever of `make retrieval-eval` and fills [prompts/rag.md](prompts/rag.md) with them, numbered in order of distance, each headed by its document and section. The prompt tells the model to answer from a passage when one states the answer and to prefer it to its own memory, and, when none does, to answer from its own knowledge only if it is confident and otherwise to say that it does not know. A passage about a public dataset or tool does not describe this service's export package, and the prompt says so. Every answer ends with `Sources: [n]`, the passages that state it, or `Sources: none`, which is how an answer reports that no retrieved passage supports it (Sections 5.1 and 6.8 of the design). The judge, the model, the temperature and the output limit are those of the baseline.

The run needs the `rag` dependency group, which the target adds when `TOP_K` is given; `make answer-eval` without it stays the plain baseline. Besides the checks of the baseline, the command refuses an index that was not built from the committed corpus and `retrieval.toml`, and names `make retrieval-index`. It logs one run named `answer-rag-k<n>` to the MLflow experiment `landcover-answers`, beside the baseline, with `top_k`, the four retrieval settings, the tag `index_version` and the hash of `prompts/rag.md` as `prompt_hash`. Hit rate and MRR are computed from the passages each answer was given, by the definition of `make retrieval-eval`, so one run is one row of the table below. Latency per question is retrieval plus the answer call; `retrieval_s` sums the retrieval seconds, and `compute_s` stays the answer calls only. `cited_answers` counts the answers that name at least one passage between 1 and k. `results.json` adds to the baseline's fields each question's first-hit rank, the retrieved chunk identifiers, the passage numbers the answer names and its retrieval seconds.

```
run 7fdebd8f: rag top_k 5, 32 questions, correct 0.656, hit rate 0.656, MRR 0.450, tokens 35956 in / 1455 out, p50 6.9 s, p95 9.1 s, shadow cost $0.0865 (prompt 4be4e95ed4e7, judge a11f648cb1f0, index 5570e99ba60e, questions 5e2556f998a1)
```

Model `gemma-4-12b-it-qat-q4_0`, llama-server build `b12359-b1b770d90`, plain prompt `e88db3af2e2d`, retrieval-augmented prompt `4be4e95ed4e7`, judge prompt `a11f648cb1f0`, index `5570e99ba60e`, evaluation set `5e2556f998a1`; the plain row is the baseline above, and it and the runs at top-k 3 and 5 ran on commit `c472b1a1301f18cf228d868ced02d02570c5310f`, the run at top-k 10 on commit `feb483bb18ab2c7a5829a4fc1056380f3cd463cf`, which adds only the labels of the two judge checks:

| top-k | Hit rate | MRR | Answer correct | Tokens in | Tokens out | Shadow cost | Compute | p50 | p95 | Run ID |
|---|---|---|---|---|---|---|---|---|---|---|
| 0, plain | – | – | 0.500 (16 of 32) | 3,822 | 1,346 | $0.0211 | 58.1 s | 1.76 s | 2.88 s | `e6d9e1d6e94b414f998e2c4862da704d` |
| 3 | 0.531 | 0.422 | 0.469 (15 of 32) | 24,047 | 1,303 | $0.0611 | 111.0 s | 3.49 s | 4.56 s | `3163de3f58e54a45bf846d0f74b30c43` |
| 5 | 0.656 | 0.450 | 0.656 (21 of 32) | 35,956 | 1,455 | $0.0865 | 218.2 s | 6.86 s | 9.11 s | `7fdebd8f4a974e50835fcf6d9dd6b3f1` |
| 10 | 0.844 | 0.473 | 0.781 (25 of 32) | 65,900 | 1,564 | $0.1474 | 336.5 s | 10.72 s | 12.95 s | `af9dc5b71a6e4ba7a6a598ef8f4636b9` |

All four rows use one server build, question set and judge prompt. Hit rate and MRR equal the retrieval runs of the same k above, so the passages each answer was given are those `make retrieval-eval` scores. Tokens, compute and cost count the 32 answer calls; p50 and p95 add each question's retrieval, which took 0.88, 1.09 and 1.91 s over all 32 questions at k = 3, 5 and 10. The runs cost no money. Every answer ended with `finish_reason` `stop`, and every passage number an answer names lies between 1 and k.

The four rows replace runs `8fe988ff4fa94f2d956a189fb9015b8d`, `1d13c9db9d0c46b29ef62243f770290d`, `1591a97b45fc4e6c910919598a964051` and `01551e9c8bdf43fc956a149c57f773c3` (15, 15, 19 and 25 of 32) on set `d06b7a39c631`, index `56be0057b30e` and judge prompt `5b291def62c3`, revised after the review of Lab 3 as described above. Those runs at top-k 3, 5 and 10 had in turn replaced runs `9ef2c97fca7f4aba8805f9a624da1fb1`, `032c60ed38194c27b0acc95b187ca55b` and `fe3d49fe10d548899b332338dbbd361f`, which read a citation written as `[3, 9]` as no citation. The first run at top-k 10 on the revised set, `31c7400e856a49a8a85baaf4bb802cc2`, gave the same 32 answers, verdicts and tokens as the row above; it was repeated because the Mac was swapping during it, and three of its calls took 25 to 76 s, which put its p95 at 27.70 s. The repeat ran after restarting the server, which frees its prompt cache.

Correct answers per document (questions per document in brackets):

| top-k | `export-contract` (6) | QGIS page (8) | OpenEarthMap paper (8) | FLAIR-HUB (6) | NAIP dictionary (4) |
|---|---|---|---|---|---|
| 0, plain | 2 | 7 | 1 | 2 | 4 |
| 3 | 4 | 4 | 4 | 2 | 1 |
| 5 | 6 | 6 | 6 | 2 | 1 |
| 10 | 6 | 6 | 7 | 4 | 2 |

Retrieval hit against answer verdict, per question:

| top-k | Hit, correct | Hit, incorrect | Miss, correct | Miss, incorrect |
|---|---|---|---|---|
| 3 | 15 | 2 | 0 | 15 |
| 5 | 20 | 1 | 1 | 10 |
| 10 | 24 | 3 | 1 | 4 |

An answer names at least one retrieved passage in 23, 23 and 27 of 32 answers at k = 3, 5 and 10. No answer that names no passage was judged correct: given passages that do not state the answer, the model says it does not know rather than answer from its own knowledge, although the prompt allows it. This is why retrieval costs answers the plain prompt had right, most of them on the QGIS page and the NAIP dictionary, which the model knows: 9 at k = 3, 6 at k = 5 and 4 at k = 10 (q13, q25, q30 and q31). The one correct answer after a miss, q08 at k = 5 and 10, uses the transparent-pixel list of the QGIS page, which its reference answer now accepts but its source does not cite, so Section 5.4 does not count that passage as relevant; adding it as a source changes the set and is left to the next revision. `export-contract` is answered fully from k = 5, and FLAIR-HUB gains most from k = 10.

The judge was checked again on the answers of run `af9dc5b71a6e4ba7a6a598ef8f4636b9` at top-k 10, the run with the most answers the judge should accept, in [eval/judge-check-rag.toml](eval/judge-check-rag.toml). Claude (`claude-opus-5-5`) labelled each answer `correct` or `incorrect` by the rubric of `prompts/judge.md` from the question, the reference answer and the answer, ignoring the line `Sources:`. The labels were written before any per-question verdict of a run on this set was read; Claude had seen the answer metric each run prints and the reviewed labels of the earlier run at top-k 10, whose answers are the same except q25 and q26. A script then copied the verdicts in. The author reviewed every label.

| | Label `correct` | Label `incorrect` |
|---|---|---|
| Judge `correct` | 24 | 1 |
| Judge `incorrect` | 0 | 7 |

The judge agrees with the labels on 31 of 32 answers, above the 29 required. The disagreement is q03: the answer names the right class, developed space, and then says that the OpenEarthMap labels count parking lots as road, while the paper counts only the lane between parking lots as road. The new rule of the judge prompt asks for `incorrect`, but the judge sees only the reference answer, which does not mention the lane, and accepts it; the earlier check had labelled the same answer `correct` too. By the labels the run has 24 correct answers, not 25. q08, which gives the transparent-pixel list instead of a no-data value, is now accepted by the revised reference, and q28 gives the 19 classes of the revised reference. The 7 rejected answers are one wrong value (q13), q25, which says the passages do not name the codes, and five "I do not know" answers.

**Choice of top-k.** The rule, fixed before the runs, takes the smallest of 3, 5 and 10 whose answer metric is no more than two questions below the best of the three. The best is 25 of 32 at k = 10; k = 5 has 21 and k = 3 has 15, four and ten below. By the labels of the check the best would be 24, and k = 5 would still be three below. The chosen top-k stays 10, the value of `top_k` in [retrieval.toml](retrieval.toml) and the default of `make retrieval-eval`; the index version does not depend on top-k. The price is latency: p50 10.7 s against 6.9 s at k = 5, because each question sends about 2,060 prompt tokens instead of 1,120.

Configuration for Lab 4:

| Item | Value |
|---|---|
| Index version | `5570e99ba60e` |
| top-k | 10 |
| Answer prompt | `prompts/rag.md`, `4be4e95ed4e7` |
| Judge prompt | `prompts/judge.md`, `a11f648cb1f0` |
| Model | `gemma-4-12b-it-qat-q4_0`, llama-server build `b12359-b1b770d90` |
| Evaluation set | `5e2556f998a1` |
| Run | `af9dc5b71a6e4ba7a6a598ef8f4636b9` |

**Memory.** Measured after the earlier run at k = 10 (`01551e9c8bdf43fc956a149c57f773c3`, the same server build and flags), with the Compose stack and the server up since before the runs:

| What | Command | Value |
|---|---|---|
| Text model server | `footprint $(pgrep -x llama-server)` | 8,638 MB physical footprint (peak 11 GB), plus 6,014 MB of clean memory-mapped pages of the model file |
| Compose stack | `docker stats --no-stream` | 3.69 GiB: Airflow 1.29 GiB, MLflow 2.19 GiB, silo 113 MiB, PostgreSQL 99 MiB |
| Answer command at k = 10 | `/usr/bin/time -l make answer-eval TOP_K=10` | 999 MiB maximum resident set size: the embedding model, the client and MLflow |

Most of the server's footprint is its prompt cache in host memory, which grows with use up to the default 8,192 MiB of `--cache-ram`; the clean pages of the model file can be dropped by macOS under pressure and read again. Without the clean pages the three take about 13 GiB of the Mac's 24 GiB; Minikube comes in Lab 4 and is measured there.

## Lab 4: services

Lab 4 serves the Lab 2 model and the Lab 3 answers over HTTP as two images built from this repository. Both listen on port 8000 and expose `/health/live`, `/health/ready` and `/metrics`.

| Image | Endpoint | What it does |
|---|---|---|
| `landcover-ml:<commit>` | `POST /predict` | Takes one 8-bit image with at least three bands (GeoTIFF, PNG or JPEG) as the raw body. Returns the class mask as a base64 GeoTIFF on the input's grid, the model name and version that produced it, the image commit, the RGB means and brightness, the class shares and a dark-image warning. Loads the model by registry name and alias. |
| `landcover-llm:<commit>` | `POST /ask` | Takes `{"question": "..."}` and retrieves `top_k` passages from the Lab 3 index. It answers with `prompts/rag.md` through the text model of `make llm-server`, which stays on the host, and returns the cited passages with document, version and section. |

The course service answers one image per request in the same HTTP response, up to 1024×1024 pixels and 16 MiB. The job queue, workers, tiling of large images and the 24-hour retention of the design (Sections 6.2 and 6.3) stay product description.

### Build

```sh
make images
```

The command refuses a tree with uncommitted changes to tracked files. It builds both targets of [docker/serve/Dockerfile](docker/serve/Dockerfile) from `git archive HEAD` and tags them `landcover-ml:<commit>` and `landcover-llm:<commit>` with the full SHA of `HEAD`. An image therefore holds exactly the committed files, never `.env`, `runs/` or `models/`. The same SHA is in the label `org.opencontainers.image.revision`, in the environment variable `IMAGE_COMMIT` and in every response. Both images install the dependency group `serve`, which takes the CPU-only build of torch (`2.15.0+cpu`). The groups `nn` and `rag` keep the CUDA build for Colab. The LLM image also holds `intfloat/multilingual-e5-small` at the revision of `retrieval.toml` and runs with `HF_HUB_OFFLINE=1`.

Measured at commit `d0d7818` on the M4 Pro (linux/arm64):

| Image | Compressed (`docker image inspect`) | Unpacked (`docker image ls`) |
|---|---|---|
| `landcover-ml` | 641 MB | 2.94 GB |
| `landcover-llm` | 930 MB | 3.72 GB |

The first build downloads about 1 GB and took under 2 minutes. torch takes 688 MB of the unpacked virtual environment, which is 2.0 GB in all, and the embedding model 471 MB.

### Run on the Compose network

The services read their configuration from the environment:

| Variable | Service | Default |
|---|---|---|
| `MLFLOW_TRACKING_URI` | ML | required |
| `MODEL_NAME`, `MODEL_ALIAS` | ML | `landcover-segmenter`, `champion` |
| `WAREHOUSE_DSN` | both | required |
| `DARK_BRIGHTNESS` | ML | unset: no warning |
| `MAX_PIXELS`, `MAX_BYTES` | ML | 1048576, 16777216 |
| `LOAD_RETRY_SECONDS` | ML | 10 |
| `LLM_BASE_URL` | LLM | `base_url` of `retrieval.toml` |
| `MAX_QUESTION_CHARS` | LLM | 2000 |

The model name, top-k, chunk settings and prompt of the LLM service come from `retrieval.toml` and `prompts/` as committed. Start the stack with `make up`; MLflow accepts the host `mlflow:5000` that the containers use. Then:

```sh
set -a; . ./.env; set +a
C=$(git rev-parse HEAD)
docker run -d --name ml --network kse-mlops-project_default -p 127.0.0.1:8000:8000 \
  -e MLFLOW_TRACKING_URI=http://mlflow:5000 \
  -e WAREHOUSE_DSN="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres/landcover" \
  landcover-ml:$C
curl -s --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif \
  -H 'X-Source-Id: D017-2021/AA-S2-9_2-7' localhost:8000/predict | jq 'del(.mask)'
```

```json
{
  "request_id": "c1b789f2-5bf7-47eb-a207-e0415f130d2a",
  "model_name": "landcover-segmenter",
  "model_version": "2",
  "image_commit": "d0d78181a077a6905228d28fc5d71eed4201112a",
  "width": 512,
  "height": 512,
  "valid_px": 262144,
  "features": {
    "mean_r": 129.78781509399414,
    "mean_g": 134.10511779785156,
    "mean_b": 99.95866012573242,
    "brightness": 121.2838643391927
  },
  "class_shares": {
    "bareland": 0.000030517578125,
    "rangeland": 0.001216888427734375,
    "developed": 0.0,
    "road": 0.0,
    "tree": 0.00778961181640625,
    "water": 0.0,
    "agriculture": 0.9909629821777344,
    "building": 0.0
  },
  "dark_warning": null
}
```

With `make llm-server` running on the host:

```sh
docker run -d --name llm --network kse-mlops-project_default -p 127.0.0.1:8002:8000 \
  -e LLM_BASE_URL=http://host.docker.internal:8081/v1 \
  -e WAREHOUSE_DSN="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres/landcover" \
  landcover-llm:$C
curl -s localhost:8002/ask -H 'Content-Type: application/json' \
  -d '{"question": "What does the value 255 mean in the output mask?"}' | jq
```

```json
{
  "answer": "In the output mask, the value 255 marks pixels that are ignored in training and invalid input pixels.\n\nSources: [4]",
  "cited": [
    4
  ],
  "sources": [
    {
      "n": 4,
      "doc_id": "export-contract",
      "doc_version": "209d12a719fc",
      "locator": "5.1 Problem statement"
    }
  ],
  "model": "gemma-4-12b-it-qat-q4_0",
  "top_k": 10,
  "index_version": "5570e99ba60e",
  "prompt_hash": "4be4e95ed4e7",
  "image_commit": "d0d78181a077a6905228d28fc5d71eed4201112a",
  "tokens_in": 2028,
  "tokens_out": 30,
  "retrieval_s": 0.12357245798921213,
  "generation_s": 8.26648533801199
}
```

The container reaches llama-server, which listens on the host's `127.0.0.1:8081`, through Docker Desktop's `host.docker.internal`, so `make llm-server` is unchanged.

### Health and the missing model

`/health/live` answers 200 while the process runs and checks nothing else, so a failing dependency never makes Kubernetes restart the container.

`/health/ready` answers 200 only when a request can succeed, and 503 with the reason otherwise:
- **ML service:** the model is loaded and the request log is reachable.
- **LLM service:** llama-server serves the model named in `retrieval.toml`, and the database holds the index built from the image's corpus and settings.

The ML service resolves the alias to a version number once. A background thread retries every `LOAD_RETRY_SECONDS` until it has loaded that version, which then stays fixed until a restart. `/predict` answers 503 until then.

The missing model, reproduced with an alias that the registry does not have (captured at commit `d0d7818`):

```sh
docker rm -f ml
docker run -d --name ml --network kse-mlops-project_default -p 127.0.0.1:8000:8000 \
  -e MLFLOW_TRACKING_URI=http://mlflow:5000 \
  -e WAREHOUSE_DSN="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@postgres/landcover" \
  -e MODEL_ALIAS=missing landcover-ml:$C
```

```text
$ curl -i localhost:8000/health/live
HTTP/1.1 200 OK
content-length: 13
content-type: application/json

{"live":true}


$ curl -i localhost:8000/health/ready
HTTP/1.1 503 Service Unavailable
content-length: 148
content-type: application/json

{"ready":false,"reason":"landcover-segmenter@missing not loaded: RestException: INVALID_PARAMETER_VALUE: Registered model alias missing not found."}


$ curl -i --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8000/predict
HTTP/1.1 503 Service Unavailable
content-length: 134
content-type: application/json

{"detail":"landcover-segmenter@missing not loaded: RestException: INVALID_PARAMETER_VALUE: Registered model alias missing not found."}


$ docker logs ml
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
landcover-segmenter@missing not loaded: RestException: INVALID_PARAMETER_VALUE: Registered model alias missing not found.; retrying in 10 s
```

When the alias `missing` was then created on version 1, the same container became ready within 6 s without a restart:

```text
loaded landcover-segmenter version 1 (landcover-segmenter@missing), image d0d78181a077a6905228d28fc5d71eed4201112a
```

The alias was deleted afterwards.

### Promotion without a rebuild

With the ML container started as in [Run on the Compose network](#run-on-the-compose-network), on the alias `champion`:

```text
$ curl -s --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8000/predict | jq .model_version
"2"
$ make champion VERSION=1
uv run --locked python -m landcover.tracking champion 1
landcover-segmenter@champion -> version 1
$ docker restart ml
ml
$ until curl -sf localhost:8000/health/ready >/dev/null; do sleep 1; done
$ curl -s --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8000/predict | jq .model_version
"1"
```

`make champion VERSION=2` and another restart returned the service to the U-Net. The mask of version 1 equals, pixel for pixel, the one `models.load_predictor("rf", "runs/rf-07c41af/model.joblib")` gives for the same tile, and that of version 2 equals the U-Net's. The image runs both because it carries the code for the rule, the random forest and the U-Net: the registry supplies the weights and the model kind, and the image tag names the code that runs them.

### Request log

The ML service writes every request it serves to `serving.predictions` in the database `landcover` before it responds. If the row cannot be written, the request fails with 500. The service creates the table from [sql/serving.sql](sql/serving.sql) at start-up.

- **One row per request:** time received, model name and version, image commit, outcome (`ok`, `invalid` or `error`) and reason.
- **Client and grid:** the client's optional `X-Source-Id`, grid size and valid pixel count.
- **Inputs and outputs:** the RGB means and brightness over valid pixels on 0–255, the eight class shares of valid pixels, the dark-image warning and the mask.

Requests refused with 503 before a model is loaded write no row. The drift job reads this table (`add-lab4-drift-alert`):

```sh
docker compose exec postgres psql -U "$POSTGRES_USER" -d landcover -c \
  "SELECT received_at, model_version, outcome, source_id, round(brightness::numeric, 1) AS brightness,
          round(share_agriculture::numeric, 3) AS agriculture FROM serving.predictions ORDER BY received_at DESC LIMIT 3"
```

```text
          received_at          | model_version | outcome | source_id | brightness | agriculture
-------------------------------+---------------+---------+-----------+------------+-------------
 2026-11-25 21:40:26.862036+00 | 2             | invalid |           |            |
 2026-11-25 21:40:25.576918+00 | 2             | ok      |           |      121.3 |       0.991
 2026-11-25 21:40:24.061165+00 | 2             | ok      |           |      121.3 |       0.991
(3 rows)
```

### Metrics

`/metrics` is in the Prometheus text format. Requests to the health and metrics endpoints are not counted.

| Metric | Labels | Service |
|---|---|---|
| `landcover_requests_total` | `endpoint`, `outcome` (`ok`, `invalid`, `error`, `unavailable`), `model_version` on the ML service | both |
| `landcover_request_seconds` (histogram) | `endpoint` | both |
| `landcover_model_loaded` | — | ML |
| `landcover_llm_stage_seconds` (histogram) | `stage` (`retrieve`, `generate`) | LLM |
| `landcover_llm_tokens_total` | `direction` (`in`, `out`) | LLM |

After two valid tiles and one invalid upload the ML service reports:

```text
landcover_requests_total{endpoint="/predict",model_version="2",outcome="ok"} 2.0
landcover_requests_total{endpoint="/predict",model_version="2",outcome="invalid"} 1.0
landcover_request_seconds_bucket{endpoint="/predict",le="0.05"} 1.0
landcover_request_seconds_bucket{endpoint="/predict",le="0.1"} 1.0
landcover_request_seconds_bucket{endpoint="/predict",le="0.25"} 1.0
landcover_request_seconds_bucket{endpoint="/predict",le="0.5"} 1.0
landcover_request_seconds_bucket{endpoint="/predict",le="1.0"} 1.0
landcover_request_seconds_bucket{endpoint="/predict",le="2.5"} 3.0
landcover_request_seconds_bucket{endpoint="/predict",le="5.0"} 3.0
landcover_request_seconds_bucket{endpoint="/predict",le="10.0"} 3.0
landcover_request_seconds_bucket{endpoint="/predict",le="+Inf"} 3.0
landcover_request_seconds_count{endpoint="/predict"} 3.0
landcover_request_seconds_sum{endpoint="/predict"} 2.7696777940145694
landcover_model_loaded 1.0
```

### Measurements

Measured in the ML container at commit `d0d7818`, with `OMP_NUM_THREADS=1` as the image sets it. The first request after start-up also warms up torch:

| Input | First request | Peak memory of the container (`memory.peak`) |
|---|---|---|
| Idle, model loaded | — | 827 MiB |
| 512×512 tile | 1.6 s | 969 MiB |
| 1024×1024 image | 6.8 s | 1,145 MiB |

On the Mac host a warm U-Net takes 0.32 s per 512×512 tile on one thread. One answer of the LLM service took 8.5 s, of which 0.09 s was retrieval and 8.46 s generation for 2,028 prompt and 30 completion tokens.

## Lab 4: cluster

Lab 4 runs the two services on Minikube next to their own MLflow server and PostgreSQL. One command brings it up from a clean clone. The text model stays on the host.

### Bring-up

Prerequisites, besides [Local setup](#local-setup):
- Docker Desktop with at least 7 GB of memory (Settings, Resources);
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) 1.33.1 in `PATH`;
- `cp .env.example .env`.

No Compose stack, cloud account or kubectl is needed: the command uses `minikube kubectl --`, a client that matches the cluster's Kubernetes 1.30.0. Stop Compose (`make down`) first so that the two fit in memory.

```sh
make cluster
```

The command:
- starts Minikube (Kubernetes 1.30.0, docker driver and runtime, `MINIKUBE_MEMORY=6144` and `MINIKUBE_CPUS=4` by default) unless it is running;
- builds the two service images and the drift job image of `HEAD` and the MLflow image of [docker/mlflow](docker/mlflow) with Minikube's Docker daemon;
- runs `make sample`;
- applies [k8s/landcover.yaml](k8s/landcover.yaml) with the ConfigMaps (including [k8s/prometheus.yml](k8s/prometheus.yml) and [k8s/grafana/](k8s/grafana/)), a Secret built from `.env` and the commit in the image tags;
- seeds an empty registry: the majority-class rule as version 1 and the random forest as version 2, `champion` on 2;
- waits for the retrieval index Job and the ML service;
- sends a smoke request to `/predict` ([scripts/smoke.py](scripts/smoke.py)). The request fails unless the response reports the champion's version and the deployed commit;
- builds the drift reference of the served version and loads the development labels ([Lab 4: monitoring](#lab-4-monitoring)); both do nothing when already in place;
- waits for Prometheus, the Pushgateway and Grafana, and prints the port-forward commands of the dashboard and Prometheus.

When `make llm-server` is running on the host, the command also waits for the LLM service and asks it one question. Otherwise it says why the LLM service cannot be ready and still succeeds.

The cold run from a clean clone (`cp .env.example .env`), with a new Minikube profile and no images in it, at commit `dcd039c` (build, download and apply lines left out):

```text
== minikube (at 0 s)
== images, built by Minikube's Docker daemon (at 20 s)
== data sample (at 153 s)
== manifests (at 364 s)
deployment "postgres" successfully rolled out
deployment "mlflow" successfully rolled out
pod/mlflow-6cc95db77b-mff67 condition met
== registry (at 390 s)
run 1c83ec71c1bd4fd18bd95d264f56de7f: development mIoU 0.0456 (recorded 0.0456)
landcover-segmenter version 1: run 1c83ec71c1bd4fd18bd95d264f56de7f, data_version 6a0c8cc2708d6616c0bfb9f3f5095708.dir, git_commit dcd039cf598bfbb28c7649a8292fdbe975939b42; predicted a 512x512 mask
run ed4a6ebc1d3d49279ba9af971d8b9d45: development mIoU 0.1478 (recorded 0.1478)
landcover-segmenter version 2: run ed4a6ebc1d3d49279ba9af971d8b9d45, data_version 6a0c8cc2708d6616c0bfb9f3f5095708.dir, git_commit dcd039cf598bfbb28c7649a8292fdbe975939b42; predicted a 512x512 mask
landcover-segmenter@champion -> version 2
== retrieval index (at 444 s)
job.batch/retrieval-index-dcd039cf598bfbb28c7649a8292fdbe975939b42 condition met
== ML service (at 444 s)
deployment "ml" successfully rolled out
smoke /predict: landcover-segmenter version 2 (champion), image dcd039cf598bfbb28c7649a8292fdbe975939b42
== drift reference and labels (at 455 s)
reference of version 2: 256 quadrants sent, 256 in all
labels: 64 quadrants of D017-2021, 64 in the table
== monitoring (at 475 s)
deployment "pushgateway" successfully rolled out
deployment "prometheus" successfully rolled out
deployment "grafana" successfully rolled out
== LLM service (at 475 s)
llm not ready: no text model server on 127.0.0.1:8081 (make llm-server)
dashboard: minikube kubectl -- port-forward svc/grafana 3000:3000, then http://127.0.0.1:3000/d/landcover
metrics:   minikube kubectl -- port-forward svc/prometheus 9090:9090, then http://127.0.0.1:9090
took 475 s
```

| Run | Duration |
|---|---|
| Cold: clean clone, new Minikube profile, no images or data | **475 s (8 min)** |
| Repeated on the same commit: nothing built, registered, indexed or sent for the reference | 13 s |
| After a new commit: the last image layers and a new index Job | about 1 minute (60 s) |

The three slowest cold steps are the data sample (211 s: 192 files from Hugging Face over range requests), the images (133 s: the base images, the locked packages with the CPU build of torch, the 471 MB embedding model and the drift job's Evidently, all downloaded into Minikube) and the registry seed (54 s: training and registering two models). The index Job runs during the seed, and the monitoring images are pulled while the earlier steps run. The drift reference of the random forest takes 20 s. The Minikube base image was already cached by Docker Desktop. Without it, the first start pulls about 500 MB more. The first cold run, at commit `3984c35` before the monitoring components, took 662 s, mostly because its image step downloaded more (339 s).

A run on a new commit deploys the new images and builds the index again with a Job named after the commit. Completed Jobs of earlier commits stay listed; `kubectl delete job -l app=retrieval-index` removes them. PostgreSQL takes its password from `.env` only on the first start of its volume. After changing `POSTGRES_PASSWORD`, run `minikube delete` before `make cluster`. `minikube stop` keeps the cluster, the registry and the index for the next `make cluster`; `minikube delete` removes all of them.

### Using the cluster from the host

The Services are of type ClusterIP, and the node is not reachable from macOS with the docker driver, so the host uses port-forwards bound to `127.0.0.1`:

```sh
alias kubectl="minikube kubectl --"
kubectl port-forward svc/mlflow 5002:5000 &   # MLflow UI and the registry for make champion, make import
kubectl port-forward svc/ml 8000:8000 &
kubectl port-forward svc/llm 8002:8000 &
export MLFLOW_TRACKING_URI=http://127.0.0.1:5002
```

The ConfigMap `landcover` holds the tracking address (`http://mlflow:5000`), the model name, the alias and the text-model address (`http://host.minikube.internal:8081/v1`). The Secret `landcover` holds the PostgreSQL user, its password and `WAREHOUSE_DSN`. The LLM service reaches the host's llama-server through `host.minikube.internal`, Docker Desktop's gateway to the host, although the server listens on `127.0.0.1` only. MLflow accepts only the host names `mlflow:5000`, its full cluster name and the two port-forward addresses. It runs one worker with `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`. Without that setting MLflow 3.16 also starts about ten job-runner processes of about 220 MB each, and the first deployment was killed for exceeding its 1 GiB limit.

### Pods and services

With `make llm-server` running, the monitoring components deployed and the drift reports of [Two windows](#two-windows) done:

```text
$ kubectl get pods,svc
NAME                                                                 READY   STATUS      RESTARTS   AGE
pod/drift-report-29928555-88fs9                                      0/1     Error       0          27m
pod/drift-report-29928570-fvf7x                                      0/1     Completed   0          12m
pod/drift-report-29928575-pb2qt                                      0/1     Completed   0          7m59s
pod/drift-report-29928580-njdhw                                      0/1     Completed   0          2m59s
pod/grafana-87df95659-nr5jr                                          1/1     Running     0          21m
pod/llm-646cd5f99b-cdhc9                                             1/1     Running     0          43m
pod/ml-57b474875f-pptfp                                              1/1     Running     0          43m
pod/mlflow-67bd658488-r9xww                                          1/1     Running     0          43m
pod/postgres-875f46476-p6qv9                                         1/1     Running     0          3h6m
pod/prometheus-855c48cf6c-dkp2p                                      1/1     Running     0          21m
pod/pushgateway-5664486c87-q99wt                                     1/1     Running     0          27m
pod/retrieval-index-3984c35cb0801116d75df783a44ebeacbd4c715a-kqrxk   0/1     Completed   0          3h5m
pod/retrieval-index-64b5ff6a9ddc25cccb83b88702c39fdada546e8c-m8mrh   0/1     Completed   0          177m
pod/retrieval-index-be7e975db7c98e776855b500c99fc5cbc064794d-fbsng   0/1     Completed   0          42m

NAME                  TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)    AGE
service/grafana       ClusterIP   10.103.39.192    <none>        3000/TCP   140m
service/kubernetes    ClusterIP   10.96.0.1        <none>        443/TCP    3h15m
service/llm           ClusterIP   10.105.138.220   <none>        8000/TCP   3h5m
service/ml            ClusterIP   10.105.253.89    <none>        8000/TCP   3h5m
service/mlflow        ClusterIP   10.106.187.93    <none>        5000/TCP   3h5m
service/postgres      ClusterIP   10.106.23.16     <none>        5432/TCP   3h6m
service/prometheus    ClusterIP   10.103.248.190   <none>        9090/TCP   140m
service/pushgateway   ClusterIP   10.107.29.174    <none>        9091/TCP   140m
```

The report Jobs and their pods are in [Lab 4: monitoring](#lab-4-monitoring).

### Missing model in the cluster

Readiness calls `/health/ready` and liveness calls `/health/live`. The LLM service also has a startup probe, because it loads its embedding model before it accepts connections. The ML service starts at once and loads its model in the background. It is reproduced here with an alias that the registry does not have (captured at commit `3984c35`). The rolling update starts a new pod and keeps the old one until the new one is ready:

```text
$ kubectl set env deployment/ml MODEL_ALIAS=missing
deployment.apps/ml env updated
$ kubectl rollout status deployment/ml --timeout=60s
Waiting for deployment "ml" rollout to finish: 1 old replicas are pending termination...
error: timed out waiting for the condition
$ kubectl get pods -l app=ml
NAME                  READY   STATUS    RESTARTS   AGE
ml-68c5f5c974-7vvwf   1/1     Running   0          3m1s
ml-7f4c74d5b9-wmsd4   0/1     Running   0          60s
$ kubectl describe pod ml-7f4c74d5b9-wmsd4 | sed -n '/^Events/,$p'
Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Normal   Scheduled  67s                default-scheduler  Successfully assigned default/ml-7f4c74d5b9-wmsd4 to minikube
  Normal   Pulled     67s                kubelet            Container image "landcover-ml:3984c35cb0801116d75df783a44ebeacbd4c715a" already present on machine
  Normal   Created    67s                kubelet            Created container ml
  Normal   Started    67s                kubelet            Started container ml
  Warning  Unhealthy  2s (x15 over 66s)  kubelet            Readiness probe failed: HTTP probe failed with statuscode: 503
$ kubectl get endpointslices -l kubernetes.io/service-name=ml -o jsonpath='{range .items[*].endpoints[*]}{.addresses[0]} ready={.conditions.ready} {.targetRef.name}{"\n"}{end}'
10.244.0.5 ready=true ml-68c5f5c974-7vvwf
10.244.0.8 ready=false ml-7f4c74d5b9-wmsd4
$ kubectl logs ml-7f4c74d5b9-wmsd4
INFO:     10.244.0.1:46252 - "GET /health/live HTTP/1.1" 200 OK
landcover-segmenter@missing not loaded: RestException: INVALID_PARAMETER_VALUE: Registered model alias missing not found.; retrying in 10 s
INFO:     10.244.0.1:39162 - "GET /health/ready HTTP/1.1" 503 Service Unavailable
$ kubectl get endpoints ml
NAME   ENDPOINTS         AGE
ml     10.244.0.5:8000   3m21s
$ kubectl port-forward pod/ml-7f4c74d5b9-wmsd4 8010:8000 &   # this pod only
$ curl -i localhost:8010/health/ready
HTTP/1.1 503 Service Unavailable
date: Thu, 26 Nov 2026 14:40:31 GMT
server: uvicorn
content-length: 148
content-type: application/json

{"ready":false,"reason":"landcover-segmenter@missing not loaded: RestException: INVALID_PARAMETER_VALUE: Registered model alias missing not found."}
$ curl -i --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8010/predict
HTTP/1.1 503 Service Unavailable
date: Thu, 26 Nov 2026 14:40:31 GMT
server: uvicorn
content-length: 134
content-type: application/json

{"detail":"landcover-segmenter@missing not loaded: RestException: INVALID_PARAMETER_VALUE: Registered model alias missing not found."}
```


`kubectl get endpoints ml` lists only the old pod, so the Service sends no traffic to the new one. The EndpointSlice keeps the new pod's address marked `ready=false`. When the alias was then created on version 1, the same pod became ready without a restart:

```text
$ MLFLOW_TRACKING_URI=http://127.0.0.1:5002 uv run --locked python -c "from mlflow import MlflowClient; MlflowClient().set_registered_model_alias(\"landcover-segmenter\", \"missing\", \"1\")"
# ready after 6 s
$ kubectl get pod ml-7f4c74d5b9-wmsd4
NAME                  READY   STATUS    RESTARTS   AGE
ml-7f4c74d5b9-wmsd4   1/1     Running   0          105s
$ kubectl logs ml-7f4c74d5b9-wmsd4 | grep loaded
loaded landcover-segmenter version 1 (landcover-segmenter@missing), image 3984c35cb0801116d75df783a44ebeacbd4c715a
```

`kubectl rollout undo deployment/ml` and deleting the alias `missing` restored the deployment and the registry.

### Promotion in the cluster

The author's U-Net (the saved result of [Results](#results)) was imported into the cluster's registry and registered as version 3, with its original lineage (`git_commit` `c1f77a3`, development mIoU 0.3355):

```sh
make import RESULT=runs/unet-c1f77a3            # with the MLflow port-forward and MLFLOW_TRACKING_URI above
make register RUN=<printed run ID> MODEL=unet   # landcover-segmenter version 3
```

`make champion VERSION=3` and `kubectl rollout restart deployment/ml` then moved the service from version 2 to the U-Net. The block below was captured afterwards with the commands of this README and the port-forwards above. It moves `champion` to version 1, the reviewer's path, and back to version 3:

```text
$ kubectl get deployment ml -o wide
NAME   READY   UP-TO-DATE   AVAILABLE   AGE    CONTAINERS   IMAGES                                                  SELECTOR
ml     1/1     1            1           7m4s   ml           landcover-ml:3984c35cb0801116d75df783a44ebeacbd4c715a   app=ml
$ curl -s --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8000/predict | grep -o '"model_version":"[0-9]*"'
"model_version":"3"
$ make champion VERSION=1
landcover-segmenter@champion -> version 1
$ kubectl rollout restart deployment/ml
deployment.apps/ml restarted
$ kubectl rollout status deployment/ml
deployment "ml" successfully rolled out
$ curl -s --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8000/predict | grep -o '"model_version":"[0-9]*"'
"model_version":"1"
$ make champion VERSION=3
landcover-segmenter@champion -> version 3
$ kubectl rollout restart deployment/ml
deployment.apps/ml restarted
$ kubectl rollout status deployment/ml
deployment "ml" successfully rolled out
$ curl -s --data-binary @data/raw/D017-2021/images/AA-S2-9_2-7.tif localhost:8000/predict | grep -o '"model_version":"[0-9]*"'
"model_version":"3"
$ kubectl get deployment ml -o wide
NAME   READY   UP-TO-DATE   AVAILABLE   AGE     CONTAINERS   IMAGES                                                  SELECTOR
ml     1/1     1            1           7m31s   ml           landcover-ml:3984c35cb0801116d75df783a44ebeacbd4c715a   app=ml
```

The image tag is the same before and after: the registry chose the model, the restart loaded it, and nothing was rebuilt. The author's cluster keeps `champion` on version 3. A fresh `make cluster` has versions 1 and 2 with `champion` on 2. A reviewer repeats the proof with `make champion VERSION=1`, the same restart, a response reporting `"1"`, and `make champion VERSION=2` back.

### Memory

Measured with the cluster up, after one 1024×1024 `/predict` and one `/ask`, Compose stopped and Docker Desktop given 7.75 GiB:

| What | Command | Value |
|---|---|---|
| PostgreSQL pod | `memory.peak` of the container's cgroup | 131 MiB |
| MLflow pod (one worker, no job execution) | same | 402 MiB |
| ML pod, random forest at 1024×1024 | same | 1,476 MiB (limit 2 GiB) |
| LLM pod | same | 861 MiB (limit 1.5 GiB) |
| Minikube node container | `docker stats --no-stream` | 3.59 GiB of 6 GiB |
| Text model server, `--cache-ram 2048` | `footprint $(pgrep -x llama-server)` | 1,725 MB (peak 1,811 MB) |
| The Mac | `memory_pressure` | 30% free of 24 GiB |

The memory requests and limits in [k8s/landcover.yaml](k8s/landcover.yaml) come from these peaks. The random forest needs more memory at 1024×1024 than the U-Net (1,145 MiB in [Measurements](#measurements)), so the ML limit is 2 GiB. `make llm-server` now caps the server's prompt cache at 2 GiB (`--cache-ram 2048`). Without the cap the cache grew to 8.6 GB in Lab 3. The cap does not change the answers, because the cache only reuses prompt prefixes that were already evaluated. The node keeps more than 2 GiB free for the monitoring components.

## Lab 4: monitoring

A CronJob compares what the ML service served in the last 5 minutes with what its model was trained on, and pushes the result to the Prometheus Pushgateway. Prometheus also scrapes `/metrics` of both services. Grafana shows both on one dashboard, [k8s/grafana/landcover.json](k8s/grafana/landcover.json), which it loads from the repository at start-up. The design is in Section 6.6 of the [design document](docs/design.md).

### What runs

| Object | Image | Job |
|---|---|---|
| CronJob `drift-report` | `landcover-monitor:<commit>` (target `monitor` of [docker/serve/Dockerfile](docker/serve/Dockerfile): Evidently 0.7.23, no torch) | `python -m landcover.monitor report` every 5 minutes |
| Deployment and Service `pushgateway` | `prom/pushgateway:v1.11.4` | holds the last report |
| Deployment and Service `prometheus` | `prom/prometheus:v3.13.5` | scrapes `ml`, `llm` and the Pushgateway every 15 s ([k8s/prometheus.yml](k8s/prometheus.yml)); keeps 2 days in an `emptyDir` |
| Deployment and Service `grafana` | `grafana/grafana:13.3.2` | data source and dashboard from [k8s/grafana/](k8s/grafana/); anonymous viewing |

```sh
alias kubectl="minikube kubectl --"
kubectl port-forward svc/grafana 3000:3000 &      # http://127.0.0.1:3000/d/landcover
kubectl port-forward svc/prometheus 9090:9090 &   # http://127.0.0.1:9090
kubectl port-forward svc/pushgateway 9091:9091 &  # curl -s 127.0.0.1:9091/metrics | grep '^landcover_'
```

The dashboard cannot be saved from the browser; a change goes into `landcover.json` and the next `make cluster`.

### Reference, labels and replay

The observation unit is a 256×256 quadrant of a sample tile, sent to `/predict`, so the ML service computes the features on both sides of a comparison ([src/landcover/monitor.py](src/landcover/monitor.py)). The header `X-Source-Id` marks what a request is:

| Command | Sends or writes | Source ID |
|---|---|---|
| `make reference` | the 256 quadrants of the four training batches, through the service, for the version `champion` names; only those still missing | `reference/<data version>/<batch>/<tile>/q<n>` |
| `python -m landcover.monitor labels --dsn …` | the crosswalked masks of the 64 quadrants of the development batch D017-2021 into `serving.labels` | key `replay/D017-2021/<tile>/q<n>` |
| `make replay` | the 128 quadrants of the development and final batches, starting at the next 5-minute boundary so that they fall into one window | `replay/<batch>/<tile>/q<n>` |

`make cluster` runs the first two. Both need the port-forwards of `make cluster` (ML on 8000, MLflow on 5002, PostgreSQL on 5433); `make replay` needs only the ML one. After a promotion and `kubectl rollout restart deployment/ml`, run `make reference` once: until then the new version's reports say `no_reference`. The final batch D073-2022 has no labels, a declared simulation of labels that have not arrived.

### The report

Every 5 minutes the job takes the window of the previous 5 minutes. For each model version served in it, and the version of the latest served request, it compares the `ok` rows that are not reference rows with that version's reference rows:

- **Drift.** Evidently's `DataDriftPreset` with normed Wasserstein distance (in reference standard deviations) on ten columns: the red, green and blue means, brightness, and the shares of the six classes the labels can score (`developed` and `road` have zero variance in the reference). A column with distance ≥ `DRIFT_THRESHOLD` counts as drifted. The threshold is 0.5: the 95th percentile of the worst column between two halves of the training tiles was 0.45. The alert compares the brightness column alone with it ([Lab 4: drift alert](#lab-4-drift-alert)).
- **Quality.** Mean IoU of the six scored classes over the window's rows that have a label, computed as in Lab 2.
- **Insufficient data.** Fewer than 50 observations on either side, or no reference, gives `insufficient_data` with the reason (`few_observations`, `no_reference`, `incomplete_labels`) instead of a value.
- **Freshness.** The receive time of the latest served request, next to the Pushgateway's `push_time_seconds`: a job that keeps running while nothing is served shows a growing data age.

Each run replaces one Pushgateway group, `job="landcover-drift"`, so a version that leaves the traffic disappears on the next run:

| Metric | Labels |
|---|---|
| `landcover_drift_distance` | `model_version`, `column` |
| `landcover_drift_columns_drifted`, `landcover_drift_columns_share` | `model_version` |
| `landcover_drift_threshold` | — |
| `landcover_report_observations` | `model_version`, `side` (`current`, `reference`, `labelled`) |
| `landcover_report_insufficient` | `model_version`, `signal` (`drift`, `quality`), `reason` |
| `landcover_quality_miou` | `model_version` |
| `landcover_report_window_end_seconds`, `landcover_latest_request_seconds` | — |

A run that cannot reach the Pushgateway fails its Job. With the Pushgateway scaled to 0 the run of 17:15 failed with `urllib.error.URLError: <urlopen error timed out>`, and the run of 17:20 succeeded after it was scaled back.

### Two windows

On the author's cluster (`champion` on the U-Net, version 3, commit `be7e975`), `make replay` was run twice with one empty window between:

```text
$ make replay
waiting for the window that starts at 17:25 UTC
128 ok, window 17:25-17:30 UTC, version ['3']
$ make replay        # started at 17:30:55
waiting for the window that starts at 17:35 UTC
128 ok, window 17:35-17:40 UTC, version ['3']
$ for j in 29928570 29928575 29928580; do kubectl logs job/drift-report-$j | grep '^window'; done
window 2026-11-26 17:25-17:30 UTC: {"3": {"observations": {"current": 128, "reference": 256, "labelled": 64}, "drift": "3 drifted", "quality": 0.3345}}
window 2026-11-26 17:30-17:35 UTC: {"3": {"observations": {"current": 0, "reference": 256, "labelled": 0}, "drift": "few_observations", "quality": "few_observations"}}
window 2026-11-26 17:35-17:40 UTC: {"3": {"observations": {"current": 128, "reference": 256, "labelled": 64}, "drift": "3 drifted", "quality": 0.3345}}
```

![Grafana dashboard: two equal drift segments at 17:30 and 17:40 with a gap between them, insufficient data in the empty window, two request bursts, mean IoU 0.33 and the data and job ages](docs/screenshots/grafana-two-windows.png)

The report of the second window as the Pushgateway held it:

```text
landcover_drift_columns_drifted{instance="",job="landcover-drift",model_version="3"} 3
landcover_drift_columns_share{instance="",job="landcover-drift",model_version="3"} 0.3
landcover_drift_distance{column="brightness",instance="",job="landcover-drift",model_version="3"} 0.32180519328040946
landcover_drift_distance{column="mean_b",instance="",job="landcover-drift",model_version="3"} 0.3250881344999206
landcover_drift_distance{column="mean_g",instance="",job="landcover-drift",model_version="3"} 0.3303896988836811
landcover_drift_distance{column="mean_r",instance="",job="landcover-drift",model_version="3"} 0.3495431995693471
landcover_drift_distance{column="share_agriculture",instance="",job="landcover-drift",model_version="3"} 0.44225584604688717
landcover_drift_distance{column="share_bareland",instance="",job="landcover-drift",model_version="3"} 0.5246675845220734
landcover_drift_distance{column="share_building",instance="",job="landcover-drift",model_version="3"} 0.5341230019264545
landcover_drift_distance{column="share_rangeland",instance="",job="landcover-drift",model_version="3"} 0.5307541354639174
landcover_drift_distance{column="share_tree",instance="",job="landcover-drift",model_version="3"} 0.10048244293087728
landcover_drift_distance{column="share_water",instance="",job="landcover-drift",model_version="3"} 0.21236497376004032
landcover_drift_threshold{instance="",job="landcover-drift"} 0.5
landcover_latest_request_seconds{instance="",job="landcover-drift"} 1.795714548502374e+09
landcover_quality_miou{instance="",job="landcover-drift",model_version="3"} 0.3345219486430588
landcover_report_observations{instance="",job="landcover-drift",model_version="3",side="current"} 128
landcover_report_observations{instance="",job="landcover-drift",model_version="3",side="labelled"} 64
landcover_report_observations{instance="",job="landcover-drift",model_version="3",side="reference"} 256
landcover_report_window_end_seconds{instance="",job="landcover-drift"} 1.7957148e+09
```

The two replay windows give the same distances because they hold the same images. The held-out batches are other regions and years than the training batches. Without any injected shift, their input features lie 0.32–0.35 reference standard deviations from the reference, inside the range between two halves of the training tiles. The U-Net's predicted shares of bareland, rangeland and building lie 0.52–0.53 away, just above the provisional threshold, so three columns count as drifted before any shift. The development quadrants score a mean IoU of 0.3345. Section 7.2 reports 0.3355 for the same model on the whole development tiles.

Report Jobs, including the failed run of the Pushgateway check:

```text
$ kubectl get cronjob,jobs
NAME                         SCHEDULE      TIMEZONE   SUSPEND   ACTIVE   LAST SCHEDULE   AGE
cronjob.batch/drift-report   */5 * * * *   <none>     False     0        2m59s           125m

NAME                                                                 STATUS     COMPLETIONS   DURATION   AGE
job.batch/drift-report-29928555                                      Failed     0/1           27m        27m
job.batch/drift-report-29928570                                      Complete   1/1           7s         12m
job.batch/drift-report-29928575                                      Complete   1/1           3s         7m59s
job.batch/drift-report-29928580                                      Complete   1/1           6s         2m59s
job.batch/retrieval-index-3984c35cb0801116d75df783a44ebeacbd4c715a   Complete   1/1           40s        3h5m
job.batch/retrieval-index-64b5ff6a9ddc25cccb83b88702c39fdada546e8c   Complete   1/1           42s        177m
job.batch/retrieval-index-be7e975db7c98e776855b500c99fc5cbc064794d   Complete   1/1           44s        42m
```

### Memory of the monitoring components

Measured on the same cluster after a 1024×1024 `/predict` and a report on a full window:

| Pod | `memory.peak` | Request / limit |
|---|---|---|
| Grafana | 768 MiB, of which 349 MiB anonymous and the rest file cache | 512 / 768 MiB |
| Prometheus | 92 MiB | 128 / 256 MiB |
| Pushgateway | 34 MiB | 32 / 64 MiB |
| Report Job (128 against 256 rows) | 234 MiB | 256 / 512 MiB |
| Minikube node container, everything ready, `make llm-server` up | 4.51 GiB of 6 GiB (`docker stats`) | — |

Grafana 13 was killed for exceeding a first limit of 256 MiB at start-up; at 768 MiB the kernel reclaims its file cache at the limit and it has not been killed.

## Lab 4: drift alert

Prometheus evaluates five alert rules, [k8s/alerts.yml](k8s/alerts.yml), every 15 s and sends firing alerts to Alertmanager ([k8s/alertmanager.yml](k8s/alertmanager.yml)). Alertmanager has one route: it emails every alert to `operator@landcover.local`, a mailbox in Mailpit inside the cluster. The path needs no secret and no external account. An alert never trains, promotes, rolls back or restarts anything; those stay the operator's commands. The design is in Section 6.6 of the [design document](docs/design.md).

### Rules

| Alert | Fires when | `for` | Why |
|---|---|---|---|
| `BrightnessDrift` | the report's brightness distance for a model version ≥ the threshold it publishes (`landcover_drift_threshold`, `DRIFT_THRESHOLD` = 0.5 in the CronJob) | 0 s | Lab step 5: a shift in the served images |
| `DataStale` | the latest served request is more than 1 h old while the job keeps pushing | 0 s | the data, not only the job, can stop |
| `DriftReportStale` | no report pushed for 15 minutes, or no report group for 10 minutes | 10 min | the Pushgateway keeps a group without a TTL |
| `MLServiceUnavailable` | the `ml` Service has no ready pod, for example because the model is missing | 5 min | service health (Section 6.6) |
| `PredictErrors` | `/predict` answered with `error` 3 or more times in the last hour; `invalid` does not count | 0 s | a ready service can still fail on images |

The alert watches brightness only. The class-share columns of the U-Net already reach 0.53 on unchanged held-out traffic ([Two windows](#two-windows)), and brightness does not depend on the model. A report holds one value for its window; the next report brings a new one or none, so the alert resolves by itself. A version with `insufficient_data` has no distance and cannot fire it.

`DataStale` fires on any cluster that has served nothing for an hour, for example after a bring-up without a replay, and its email repeats every 4 hours. The course system has no steady traffic, so this is expected.

### Channel

| Object | Image | Job |
|---|---|---|
| Deployment and Service `alertmanager` | `prom/alertmanager:v0.34.2` | one route and one email receiver; groups by alert name and model version, waits 30 s, repeats a firing alert every 4 h, sends no resolved email |
| Deployment and Service `mailpit` | `axllent/mailpit:v1.33.1` | SMTP on 1025, mailbox web UI and API on 8025; no database, so a pod restart empties it |

`make cluster` deploys both, puts `alerts.yml` next to `prometheus.yml` in the ConfigMap `prometheus` and creates the ConfigMap `alertmanager`. A hash of each configuration is a pod annotation, so a changed file rolls only its pod and an unchanged one leaves the mailbox alone.

```sh
kubectl port-forward svc/mailpit 8025:8025 &        # http://127.0.0.1:8025
curl -s 127.0.0.1:8025/api/v1/messages              # the received emails as JSON
kubectl port-forward svc/alertmanager 9093:9093 &   # http://127.0.0.1:9093
curl -s 127.0.0.1:9090/api/v1/alerts                # active alerts, with the Prometheus port-forward
```

### The operator's first ten minutes

After a `BrightnessDrift` email (design Section 5.5):

1. Open the report window the email names on the dashboard; note the column, the distance and the threshold.
2. Check the window's source mix in the request log: `SELECT split_part(source_id, '/', 1), count(*) FROM serving.predictions WHERE received_at >= <window start> AND received_at < <window end> GROUP BY 1`.
3. Check `insufficient_data` and the data age, so that a thin or stale window is not read as drift.
4. Keep the model serving: the alert changed nothing, and `champion` stays where it is.
5. Record the decision: no action with the reason, a fault to investigate, or a request for labelled controls or a labelled batch from the affected source. Promotion and rollback stay `make champion VERSION=<n>` and `kubectl rollout restart deployment/ml`.

### Checking the rules

The rules are tested against synthetic series in [k8s/alerts_test.yml](k8s/alerts_test.yml): the drift alert fires at 0.62 and not at 0.32 nor on a share column at 0.53, and resolves when the series ends; `DataStale` fires at 1 h of data age while the job pushes; `DriftReportStale` fires after 15 minutes without a push; `PredictErrors` counts a new series' first error and ignores `invalid`. Both checks use the images' own tools and need nothing else on the host:

```sh
docker run --rm -v "$PWD/k8s:/k8s" --entrypoint promtool prom/prometheus:v3.13.5 test rules /k8s/alerts_test.yml
docker run --rm -v "$PWD/k8s:/k8s" --entrypoint amtool prom/alertmanager:v0.34.2 check-config /k8s/alertmanager.yml
```

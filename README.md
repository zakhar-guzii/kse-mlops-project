# KSE MLOps: Land-cover segmentation

GIS specialists need a first land-cover layer for new aerial imagery, which they then check and edit in QGIS. The planned service takes an 8-bit RGB aerial image and returns an eight-class OpenEarthMap (OEM) mask, a colour overlay and a legend. For a georeferenced GeoTIFF it also returns a GeoTIFF layer on the source grid. The design specifies asynchronous inference, operator-approved model updates and a rollback path. [System design](docs/design.md)

Lab 2 implements versioned FLAIR-HUB ingestion, training for three segmentation models and a local MLflow registry. The current `champion` is U-Net version 2, trained on Colab L4. It scored **0.3355 mIoU** on the six-class development control. [Lab 2 results](#results) · [Model demo](#model-demo)

## Maturity scorecard

| Property | Evidence a reviewer checks | Added in |
|---|---|---|
| Repository setup and checks | The [lint workflow](.github/workflows/lint.yml) runs `make setup`, `make lint` and `make test` ([Local setup](#local-setup)) | Lab 1 |
| Design document exists and is current | [docs/design.md](docs/design.md) follows the template; every section is filled or marked as an assumption or a placeholder | Lab 1 |
| Data versioned | `dvc pull` retrieves the raw data with hash verification, and its identifier is in [data/raw.dvc](data/raw.dvc) ([Raw data](#raw-data)) | Lab 2 |
| Pipeline idempotent | Two runs of 2019 give the same row counts, both pasted under [Ingestion pipeline](#ingestion-pipeline) | Lab 2 |
| Quality gate present | The broken batch fails `quality_check` on purpose, with a screenshot ([Broken batch](#broken-batch)) | Lab 2 |
| Experiments tracked | Every run in MLflow has its parameters, scores, `data_version` and `git_commit` ([Training and logging](#training-and-logging), [Results](#results)) | Lab 2 |
| Models registered with lineage | Both versions carry the data version and code commit. `make reproduce VERSION=1` reproduced the registered random forest on CPU ([Reproduction](#reproduction)). U-Net version 2 carries `champion` ([Results](#results)). | Lab 2 |

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

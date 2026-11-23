# Design

## Context

See [proposal.md](proposal.md) for motivation, scope and the decisions settled with the author. The repository holds the ingestion pipeline of the first Lab 2 change: `src/landcover/pipeline.py` (batch registry, crosswalk lookup table, tile reading), the Compose stack (PostgreSQL 16, Airflow 3.3.1, `pgsty/silo`), and `data/raw.dvc`, whose hash `6a0c8cc2708d6616c0bfb9f3f5095708.dir` is the data version identifier. There is no model code and no tracking server.

Facts checked for this design on 2026-11-23:

- The sample is 96 image–label pairs, 16 per batch, every tile 512×512 with four 8-bit bands. Share of all pixels per internal class after the crosswalk, computed from the raw files:

  | Batch | Role | Ignored | Bare | Range | Tree | Water | Agri | Building |
  |---|---|---:|---:|---:|---:|---:|---:|---:|
  | D080-2017 | train | 36.9 | 0.4 | 16.3 | 5.6 | 21.6 | 0.0 | 19.2 |
  | D033-2018 | train | 20.5 | 4.0 | 19.5 | 20.1 | 2.8 | 26.8 | 6.4 |
  | D065-2019 | train | 24.3 | 34.1 | 19.2 | 2.5 | 1.7 | 17.2 | 1.1 |
  | D045-2020 | train | 24.1 | 4.4 | 11.5 | 15.4 | 4.9 | 28.8 | 11.0 |
  | D017-2021 | dev | 9.7 | 15.7 | 16.4 | 7.9 | 25.2 | 24.7 | 0.36 |
  | D073-2022 | final | 37.3 | 36.8 | 12.0 | 3.3 | 2.5 | 8.0 | 0.08 |

  All six classes have labelled pixels in every batch. In the development control, building is in 2 of 16 tiles (about 15,000 pixels). The pooled training set has about 12.3 million labelled pixels and more than one million of each class; its most frequent class is agriculture land.
- The GitHub repository is public: an anonymous request for its page returns 200.
- On the author's Mac, port 5000 is held by the macOS Control Center (AirPlay Receiver).
- `ghcr.io/mlflow/mlflow:v3.16.1` is published for arm64 and amd64. Whether it contains a PostgreSQL driver and an S3 client was not checked.
- The official Colab command-line client is `google-colab-cli` 0.8.0 (PyPI, 2026-11-10), for Linux and macOS. Documented: `colab run [-s NAME] [--gpu T4] [--keep] [--timeout SECONDS] SCRIPT [ARGS]`, where the script's `sys.exit(N)` becomes the exit code and `--keep` leaves the runtime running; `colab download -s NAME REMOTE LOCAL`; `colab stop -s NAME`; `colab ssh -s NAME -- CMD`, whose exit status is the command's. Sign-in is a one-time OAuth flow in the browser; there is no API key. Not documented: whether script output streams to the local terminal, what the default `--timeout 30` counts, and whether the runtime has `git`.
- The warehouse tables are currently empty, so recreating the PostgreSQL volume loses nothing that the README commands do not restore.

Pinned by the course reference table: MLflow 3.16.1 with a PostgreSQL backend and artifacts in the S3-compatible store.

## Goals / Non-Goals

**Goals:**

- Everything the lab grades works on a reviewer's laptop without a GPU or an external account: the rule, the random forest, the tracking server, registration and reproduction.
- One training code path for the Mac and the remote GPU, and one path by which a result enters MLflow.
- A registered version is explained by two tags, and the reproduction command uses nothing else.

**Non-Goals:**

- Model quality. Hyperparameters are starting values, and no search is built.
- A configuration file format, an experiment framework, a training loop library, W&B or resuming an interrupted run.
- Reading the warehouse during training, or changing the ingestion pipeline and its tables.
- A model-serving image or tiling of large images (Lab 4).

The comparison notebook is a demo for the three saved models. It uses the shared evaluation code and the optional locked `demo` dependency group.

## Decisions

### 1. Three models and their roles

| Model | Role in the lab | Role in the design document | Trains on |
|---|---|---|---|
| Majority class | Rule-based baseline | New: the floor every model must beat | Mac, seconds |
| Random forest on pixel texture features | The trained model; the reference for reproduction | Was "baseline"; becomes the first trained model | Mac CPU |
| U-Net, EfficientNet-B4 encoder | Additional, stronger model | The candidate, unchanged | Colab GPU, or the Mac |

The lab's baseline must be a rule, and the design's random forest is trained, so the design document gains the rule and renames the forest's role. The forest stays because it is deterministic on a CPU, which makes it the version a reviewer can reproduce in minutes.

Alternative considered: a hand-written colour rule (greenness and brightness thresholds). It needs thresholds chosen by looking at images, which invites tuning on the control; the majority class has no free choice.

### 2. One split by whole batch

Training pools `D080-2017`, `D033-2018`, `D065-2019` and `D045-2020` (64 tiles). `D017-2021` (16 tiles) is the development control: it compares the three models, decides the `champion`, and is the only data the operator may use to change U-Net settings. `D073-2022` is not opened by any training or evaluation code in Lab 2, so it remains a holdout for one final evaluation later.

The roles are a constant next to the batch registry in `pipeline.py`. A batch is one département in one acquisition year, so the control is both later in time and from a different region than any training tile. There is no inner validation split: the U-Net trains a fixed number of epochs and keeps the last weights, so nothing is selected on held-out training tiles.

Alternatives considered: walk-forward evaluation over five year pairs would average out the noise of a 16-tile control, at five runs per model and a harder README; a random tile split would put neighbouring patches of one flight on both sides, which is the leak Section 5.4 exists to prevent.

### 3. A run is determined by commit, data version and parameters

`python -m landcover.train` starts by establishing its identity and refuses to continue otherwise:

- `git status --porcelain` must be empty; the commit is `git rev-parse HEAD`.
- DVC must report that `data/raw` matches `data/raw.dvc`; the data version is the `md5` in that file.

Training then reads only the raw files. It does not connect to PostgreSQL, the object store or MLflow. Three consequences follow. The run is fully described by its two tags and its parameters, which is what makes the reproduction command honest. The same command works on a Colab runtime, which can reach none of the local services. And the majority class is counted from the labels in memory rather than read from `dwh.tiles`, although both give the same counts.

Parameters are command-line arguments with defaults; the defaults are the configuration. Every argument is logged, and the reproduction command passes the logged values back as arguments.

There is no flag that allows a dirty tree. A run with uncommitted code has no commit that explains it, and committing first is cheap.

### 4. Shared loading and the three fits

All models use one loader in `src/landcover/models.py`: for each tile of the requested batches, the first three bands as an 8-bit RGB array and the label passed through the existing `pipeline.LUT`. The 96 tiles fit in memory, so there is no dataset class, worker pool or cache.

- **Rule.** Count labelled pixels per internal class over the training tiles; the model is that one class ID.
- **Random forest.** Per pixel, `skimage.feature.multiscale_basic_features` on the RGB image (intensity, edges and texture at scales 1 to 8 px). A first pass over the labels draws, with the run's seed, at most 10,000 pixel positions per class from the pooled training set; a second pass computes features tile by tile and keeps only the drawn positions, so the full feature array is never held. `RandomForestClassifier` with 100 trees, depth 12 and the run's seed. The cap per class keeps the forest from learning mostly class frequencies.
- **U-Net.** `segmentation_models_pytorch` U-Net with the `tu-tf_efficientnet_b4.in1k` encoder and ImageNet weights, eight outputs. Input scaled to 0–1 and normalised with the ImageNet mean and standard deviation. Full 512×512 tiles, batch size 8, random flips and 90° rotations applied to image and mask together. Cross-entropy that ignores label 255, AdamW, 40 epochs, mixed precision on CUDA only. The device is CUDA, then MPS, then CPU. After every epoch the training loss and the development score are recorded for the history; they select nothing.

`torch` is imported inside the U-Net functions only, so the rule and the forest run without it.

The ImageNet weights are a third input that neither tag covers. The run records the Hugging Face repository and the revision the download resolved to as parameters.

Road and developed space never appear in FLAIR-HUB labels. The forest therefore has six classes, and the U-Net's two extra outputs receive no positive target.

### 5. One evaluation

One function scores every model: predict each development tile, add to one 8×8 confusion matrix over pixels whose label is not 255, then compute intersection over union for classes 0, 1, 4, 5, 6 and 7 and their mean. A prediction of class 2 or 3 adds to the missed pixels of the true class. The function also returns pixel accuracy, labelled pixels per class and the ignored share, and raises when a scored class has no labelled pixel.

Per-class pixel counts are reported next to every score because one class is a sixth of the mean and building rests on two tiles.

### 6. A training result is a directory, and logging has one path

A run publishes `runs/<model>-<commit7>-<id>/` (ignored by Git) after it finishes. The directory holds `run.json` and `model.json` for the rule, `model.joblib` for the forest or `model.pt` for the U-Net. The record includes every batch role, both lineage identifiers, scores, device, package versions and the model SHA-256. U-Net records the encoder revision and epoch history. Remote results include the actual GPU and location.

`python -m landcover.tracking log <dir>` is the only way a result enters MLflow, for local and remote runs alike. It checks the SHA-256, loads the model through the same wrapper that is stored with the run, scores it again on the development control, and fails when the score differs from the recorded one by more than 0.005. The logged score is therefore always measured on this machine by the model that was stored. `make train` is "train, then log"; `make import RESULT=<dir>` is the log step alone.

Only the U-Net is trained remotely, and its state dictionary is loaded with `weights_only=True`, so no pickle from a remote machine is ever executed.

Alternative considered: logging to MLflow directly from the training process. A Colab runtime cannot reach the local server without a public tunnel, which would require authentication and an exposed port, and it would leave two logging paths.

### 7. MLflow in the Compose stack

| Item | Choice |
|---|---|
| Image | `docker/mlflow/Dockerfile`: `ghcr.io/mlflow/mlflow:v3.16.1` plus pinned `psycopg2-binary` and `boto3` |
| Backend store | Database `mlflow` on the existing `postgres` service, created by one more line in `sql/warehouse.sql` |
| Artifact store | Bucket `landcover-mlflow` on `silo`, created by the existing `create-bucket` service; the server proxies uploads and downloads (`--artifacts-destination`) |
| Address | `127.0.0.1:5001` on the host, because macOS holds port 5000; port 5000 inside the network |
| Client settings | `MLFLOW_TRACKING_URI=http://localhost:5001` and `MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false`, exported by the Makefile |

With proxied artifacts a client needs only the tracking address and no object-store credentials. The second client setting is the one the lab notes prescribe so that downloads do not use presigned URLs naming `silo:9000`.

`sql/warehouse.sql` runs only on an empty volume, so the existing volume is recreated once and the six batches are loaded again. This is the convention the file's header already states. Alternatives considered: a one-shot service that creates the database if missing adds a second mechanism for the same job; placing MLflow's tables in the `landcover` database mixes bookkeeping with the warehouse.

Authentication is not enabled. The only client is the operator on the same machine, and the port is bound to localhost. Lab 4 adds it together with the first read-only client, the serving worker.

### 8. What MLflow holds

Experiment `landcover`. Every run has the parameters, the scores of Decision 5 as metrics, the per-epoch history as stepped metrics, the tags `data_version` and `git_commit`, `run.json`, and the model.

The model is stored as one `mlflow.pyfunc` wrapper for all three kinds: `predict` takes an RGB array of height × width × 3 and returns a mask of height × width. Feature computation for the forest and scaling, normalisation and padding to a multiple of 32 for the U-Net happen inside the wrapper, and the `landcover` package is stored with the model. This is what gives every model input a serving-time source: the same code, loaded with the model version.

`make register RUN=<id>` creates a version of the registered model `landcover-segmenter`, copies both tags to the version, loads the version back through the server and predicts one development tile. That load is the artifact download check that Section 7.4 left to this change. The rule is logged as a run and is not registered. `make champion VERSION=<n>` sets the alias. Registration and promotion are separate commands because Section 5.5 makes promotion the operator's decision.

The forest and the U-Net are both registered. `champion` goes to the one with the higher development mean intersection over union.

### 9. Reproduction

`make reproduce VERSION=<n>`:

1. Read the version's tags and its run's parameters and score.
2. `git worktree add --detach <temporary directory> <git_commit>`; fail unless `data/raw.dvc` there names the `data_version` tag.
3. In the worktree, `dvc pull` uses the locked environment and checks the data hashes.
4. Train with the logged parameters and exact encoder revision. `GPU=L4` delegates a recorded CUDA U-Net run to Colab, where the pinned source sample is verified against the same DVC pointer. Log the result in the worktree with `reproduces=<original run id>` and retain its exact run ID.
5. Compare the two scores with the tolerance for the model kind, print both, remove the worktree, and exit non-zero outside the tolerance.

A worktree leaves the author's checkout alone and makes the old commit's own code and lock file do the training.

Tolerances are constants per model kind, stated in the README. For the forest the expected difference on one machine is zero, and the tolerance is 0.01 to cover numerical differences between machines. For the U-Net it is set after measuring: twice the largest difference seen between the registered run and its repetitions, rounded up to 0.01 and not below 0.02.

On a clean clone the registry is empty, so a reviewer trains and registers the forest and reproduces that version. The README also lists the author's registered versions with their identifiers and scores; a forest trained at the same commit and data version lands within the tolerance of the listed score.

### 10. Remote training through the Colab client

`make train-remote`:

1. Fail unless the tree is clean and a remote branch contains `HEAD`.
2. Start a uniquely named Colab session with L4 by default and confirm the runtime's actual GPU before training.
3. Download the result, release the session and verify the archive's lineage and model hash before publishing a unique result directory in `runs/` and logging it.
4. Attempt to release the session on every failure path and preserve the original error if cleanup also fails.

`scripts/remote_train.py` uses only the standard library. On the runtime it clones the repository, checks out the commit, installs `uv`, runs `uv sync --locked --group nn`, runs `scripts/fetch_sample.py`, runs the same `landcover.train` command for the U-Net and zips the result. The identity checks of Decision 3 run there unchanged, so a fetch that does not match `data/raw.dvc` stops the run. Its exit code is the exit code of the first failing step.

The local stack's credentials are never needed remotely: the code comes from the public repository and the data from Hugging Face.

Fallbacks, in order, if the client does not behave as documented: an explicit session (`colab new`, `colab upload`, `colab ssh -- python remote_train.py …`, `colab download`, `colab stop`); then running the same launcher from a notebook cell in the browser, downloading the zip and running `make import`. Because the U-Net command is the same everywhere, `make train MODEL=unet` on the Mac is always available.

Alternatives considered: a Kaggle launcher has a real API token but is asynchronous (push, poll, fetch) and needs a metadata file, and the author already owns Colab Pro; a notebook needs a browser and a manually typed commit.

### 11. Dependencies and layout

- `pyproject.toml` dependencies gain `mlflow==3.16.1`, `scikit-learn` and `scikit-image`, pinned exactly like the existing ones.
- A dependency group `nn` holds `torch`, `segmentation-models-pytorch==0.5.0` and `timm`. `make setup` and CI do not install it; `make train MODEL=unet` and the launcher do.
- The Airflow image is unchanged: training does not run in Airflow.
- New files: `src/landcover/models.py` (loader, evaluation, the three models), `src/landcover/train.py` (identity checks, fit, result directory), `src/landcover/tracking.py` (log, register, promote, reproduce, the wrapper), `scripts/remote_train.py`, `docker/mlflow/Dockerfile`, `tests/test_models.py`.
- Tests cover the evaluation on a hand-computed matrix (including ignored pixels, a prediction of an unscored class and a class without pixels), the rule, the per-class cap and determinism of the pixel draw, and the hash in `run.json`. The U-Net has no unit test; its check is the recorded run.

### 12. Document revisions

| Location | Revision |
|---|---|
| Section 5.3 | Add the majority-class rule as the baseline; describe the forest as the first trained model; state that the course trains each model once on the pooled 2017–2020 batches from FLAIR-HUB only and that the update loop and OEM replay are product behaviour not run in the course; remove the sentence that mentions `replay=true`; replace the feature table with one that lists every model input and every column of `features.tile_features` with its training and serving source (below) |
| Section 5.4 | The course split and why it cannot leak; no inner validation; the six-class score with per-class pixel counts as the only course metric; the `champion` rule for the course; which approval rules need OEM and are not exercised; the reproduction tolerance and how it was measured |
| Section 7.2 | Results read from the tracking server: for each model the run ID, both identifiers, mean intersection over union, pixel accuracy and per-class values with pixel counts; which version is `champion`; whether the rule beat a model; the measured reproduction differences |
| Section 6.1 and `data-flow.svg` | Layers 4 and 5 show `make train` and `make train-remote`, the result directory, the MLflow server with its PostgreSQL database and `silo` bucket, the registered model name and the alias, in place of "Drive export, verified import" |
| Section 6.2 | MLflow row: no authentication until Lab 4, host port 5001; replace the "Training exchange" paragraph with the Colab client flow and remove the W&B sentence; add MLflow to the "Lab 2 stack" paragraph |
| Section 6.4 | MLflow in the course is unauthenticated and bound to localhost; the launcher sends no credentials |
| Section 6.9, Colab row | An interrupted run is started again; a run takes minutes at the course scale |
| Section 7.4 | Lab 2 milestone names the rule, the forest and the U-Net; the storage check reports the MLflow artifact upload and download actually run |
| `deployment.svg` | MLflow card and `<desc>`: drop "authentication" |
| `docs/design.uk.md` | The same passages, if the file exists |

Sections 1 to 4 keep describing the product (OEM training and updates in year order); Section 5.2 already says OEM is not ingested in the course.

The feature table of Section 5.3:

| Value | Training source | Serving source | Read by |
|---|---|---|---|
| RGB pixels | Raw tile, first three bands | The uploaded image | Forest, U-Net |
| Pixel texture features | Computed from the tile by the packaged code | Computed from the upload by the same code, loaded with the model version | Forest |
| Scaling, normalisation, padding | Packaged code and constants | Same code, loaded with the model version | U-Net |
| `channel_mean` | `features.tile_features`, from the image | Computed from the upload | Input-drift monitoring (Lab 4); no model |
| `class_share`, `ignored_share` | `features.tile_features`, from the labels | None: a label statistic that exists only for labelled batches; its serving counterpart is the predicted class share of the output mask | Quality gate and monitoring reference; no model |

## Risks / Trade-offs

- The Colab client is pinned to version 0.8.0. Decision 10 lists fallbacks for allocation and execution failures.
- The development control is 16 tiles and building rests on about 15,000 pixels → every score is shown with per-class pixel counts, and Section 7.2 says that small differences between models are not evidence.
- The rule or the forest beats the U-Net on 64 training tiles → reported as measured; `champion` follows the development score.
- EfficientNet-B4 fails or is slow on MPS → train on the CPU or remotely; the device is a logged parameter.
- `mlflow` and `dvc` cannot be resolved into one environment → move `mlflow` to its own dependency group used by the tracking commands; training needs only DVC.
- The MLflow image lacks a driver, rejects the `localhost:5001` host header, or exits with code 132 on Apple Silicon → the Dockerfile adds the drivers; set the server's allowed hosts; apply the `cryptography==46.0.5` line from the lab notes and say so in the README.
- The ImageNet weights change upstream → the encoder is loaded by its recorded Hugging Face commit. Legacy code uses an isolated offline cache mapped to that commit.
- `docker compose down -v` deletes MLflow's runs and model files → `runs/` keeps every result for `make import`; the forest retrains in minutes.
- Reproducing a U-Net version on a laptop CPU is slow → the README names the forest version as the reference reproduction and states the U-Net's measured time and tolerance.
- The forest is stored as a pickle → it is only ever produced on the machine that loads it.
- Recorded runs need committed code, and remote runs need a pushed commit → tasks mark where the author commits, pushes and signs in to Colab.

## Migration Plan

1. `docker compose down -v`, then `make up`: the new volume gets the `mlflow` database and the second bucket.
2. `make data` refills the store without downloading; reload the six batches with the README backfill command.

Rollback is reverting the change and repeating step 1. Nothing outside the local machine holds state.

## Open Questions

- The final U-Net settings. The values in Decision 4 are starting points; the operator may change them using development scores, and every change is a new run with logged parameters.
- The U-Net reproduction tolerance, which Decision 9 derives from measurement.

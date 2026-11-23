# Proposal

## Why

Lab 2 (steps 5–7) requires a rule-based baseline and one trained model compared on a leakage-free split, an experiment tracking server with a database and an object store, a registered model version that carries the data version and the code commit, and one command that reproduces a registered run. The repository has the versioned data and the ingestion pipeline from the first Lab 2 change, but no model code, no tracking server, and a design document whose Sections 5.3, 5.4 and 7.2 still describe training on OpenEarthMap, which the course does not ingest.

This is the second and last Lab 2 change. The author creates the `lab-2` tag and pushes.

## What Changes

- Add three segmentation models that share one data loader and one evaluation: a majority-class rule (the lab's rule-based baseline), a random forest on per-pixel texture features (the lab's trained model, exactly reproducible on a CPU), and a U-Net with an EfficientNet-B4 encoder (the stronger model).
- Add one training command. A training run is determined by three things only: the code commit, the DVC hash of `data/raw` and the logged parameters. It reads the raw files, never the warehouse, the object store or the tracking server, so the same command runs on the Mac and on a remote GPU.
- Add one split, by whole batch: 2017–2020 for training (pooled into one training set), 2021 as the development control, 2022 untouched.
- Add an MLflow 3.16.1 tracking server to the Compose stack, with PostgreSQL as the backend store and a bucket on `pgsty/silo` as the artifact store.
- Add commands that log a finished training run to MLflow with both lineage identifiers, register a run as a version of one registered model, move the `champion` alias, and reproduce a registered version from its identifiers.
- Add one command that trains the U-Net on a Colab GPU through the official Colab command-line client and brings the weights back. Only one launcher file is sent to the runtime; it clones the repository at the commit being trained.
- Revise `docs/design.md` Sections 5.3 and 5.4, fill Section 7.2 from the tracking server, update the training lane of the data-flow diagram, and make the consistency edits these decisions force in Sections 6.2, 6.4, 6.9 and 7.4.
- Extend the README with the commands above, the baseline and model scores side by side, the identifiers of the registered versions, the reproduction tolerance and the maturity scorecard (Lab 1 and Lab 2 rows).

Decisions settled with the author, each replacing a statement of the current design:

| Topic | Current design | This change |
|---|---|---|
| OpenEarthMap | Initial training and the eight-class controls use it | Not ingested in Lab 2. Models learn six classes from FLAIR-HUB; road and developed space are neither trained nor scored; the OEM-based approval rules stay as the product description |
| Training schedule | Four successive updates in acquisition-year order, each from the approved model | One training run per model on the pooled 2017–2020 batches; the update loop stays as the product description |
| Baseline | The random forest is called the baseline | The majority-class rule is the baseline; the random forest is the first trained model |
| Training exchange | Results saved to Google Drive, downloaded by hand, then imported | One command starts the run with the Colab client, downloads the result and imports it |
| MLflow access control | MLflow runs with authentication | No authentication in Lab 2; the port is bound to localhost. Authentication arrives in Lab 4 with the first read-only client |

Defaults proposed during exploration and not objected to: the development control alone decides the `champion`; the 2022 batch is not scored in Lab 2; the U-Net trains a fixed number of epochs without early stopping; the reproduction tolerance is set from measured repeat runs.

## Capabilities

### New Capabilities

- `model-training`: the split, the conditions a training run checks before it starts, the three models, the evaluation and the result a training run leaves behind.
- `experiment-tracking`: the tracking server, what every logged run carries, registration with lineage, the `champion` alias and the reproduction command.
- `remote-training`: starting a training run on a remote GPU from the local repository and returning its result.

### Modified Capabilities

None. The requirements of `raw-data-versioning` and `batch-ingestion-pipeline` do not change. They are still inside the unarchived change `add-lab2-data-pipeline`; archiving it first is recommended and does not block this change.

## Impact

- New code: `src/landcover/` modules for models, training and tracking; `scripts/remote_train.py`; unit tests of the evaluation, the rule and the pixel sampling.
- Changed stack: `docker-compose.yml` (an `mlflow` service, a second bucket), new `docker/mlflow/Dockerfile`, `sql/warehouse.sql` (an `mlflow` database), `.env.example` (client variables), `Makefile` (training, import, registration, promotion, reproduction and remote training targets), `.gitignore` (the local results directory).
- Changed dependencies: `pyproject.toml` and `uv.lock` gain `mlflow`, `scikit-learn` and `scikit-image`, plus `torch`, `segmentation-models-pytorch` and `timm` in a separate dependency group that `make setup` and CI do not install.
- Changed documents: `README.md`, `docs/design.md`, `docs/diagrams/data-flow.svg`, `docs/diagrams/deployment.svg`, and the affected passages of the local, ignored `docs/design.uk.md`.
- Existing local state: adding the `mlflow` database needs the PostgreSQL volume to be recreated, so the six batches are loaded again.
- External systems: Google Colab (the author's Colab Pro compute units) and Hugging Face (the sample and the ImageNet encoder weights) are used by remote training. A reviewer needs neither: the rule and the random forest train locally.
- Out of scope: OpenEarthMap ingestion, sequential model updates, scoring the 2022 batch, Feast, MLflow authentication, a Kaggle launcher, resuming an interrupted training run, the serving service (Lab 4), any change to the ingestion pipeline or its tables, and the `lab-2` tag.

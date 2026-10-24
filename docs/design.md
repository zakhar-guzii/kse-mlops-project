# Land-cover segmentation system design

This is the design of the KSE MLOps course project, written against [Lab 1](../labs/lab-1.pdf); the course PDF is a local file and is not distributed with the repository. The document describes the target service. Section 4 states the one constraint of the course setup: the same components run locally, and the cloud deployment is costed but not purchased.

## 1 Overview

GIS specialists need a first thematic land-cover layer for new overhead imagery, which they then check and edit into a map. The system accepts an RGB aerial image of arbitrary size and returns an eight-class OpenEarthMap (OEM) mask with a colour overlay, a legend and, for georeferenced GeoTIFF input, a GeoTIFF layer on the source grid. Many users can submit images at once: an authenticated API queues each upload as a job, and CPU workers scale with the queue. The model is trained on OEM and then fine-tuned on new expert-labelled batches in acquisition-year order; an operator reviews each candidate and approves it before it serves. The desired outcome is GIS exports that open without manual repair, and model updates that are reproducible, monitored and reversible.

## 2 Motivation

The system has two roles:

- **GIS user** (consumer): a cartographer or GIS specialist. When new imagery arrives for a project area, they upload it, wait for the job, import the package into QGIS and edit the layer there.
- **Operator**: the ML engineer who owns the system. They add training batches, review alerts and candidate models, approve or block a model version and roll back. In the course this is the author; the role never merges with the GIS user.

Assumption: 20 active GIS users submit 1000 images a month, about 2.3 images per user per working day. This is a small team; Section 6.7 prices a 2200-image case as well.

Errors have different costs. A wrong class costs the GIS user correction time in QGIS. A wrong grid or invented georeferencing places the layer in the wrong position, so the whole export is unusable. A model update that silently loses a class, for example roads, repeats the same error across every later map. A notebook cannot serve these users: requests arrive from many people at any time, every map must name the model that produced it, model updates need a reproducible comparison and an approval step, and quality must be watched on uploads that have no reference masks.

## 3 Success metrics

| Level | Metric and target | How it is checked |
|---|---|---|
| Decision / workflow | At least 9 of 10 predefined valid test images give a complete package that opens in QGIS on the correct grid without manual format or georeferencing repair | Fixed test set: PNG, JPEG, georeferenced GeoTIFF and three image sizes. This measures export usability, not cartographic accuracy |
| Model | The first neural model exceeds the random-forest baseline in OEM-8 mIoU; each later update passes the promotion rule in Section 5.4 | Frozen development controls; per-class IoU and support; final holdouts reported once |
| System | Job acknowledgement p95 ≤ 1 s after upload; completion p95 ≤ 5 min for a 4096×4096 image at the assumed load; at most 1% of valid jobs fail for system reasons per week | Load test (Section 6.3) and monitoring (Section 6.6) |

mIoU is the optimization metric: it is the score we try to improve. Export validity, p95 latency and resource limits are satisficing metrics: each must pass, and passing it by a larger margin earns nothing.

## 4 Requirements and constraints

**Functional requirements:**

- An authenticated GIS user uploads one 8-bit RGB PNG, JPEG or GeoTIFF and immediately receives a job ID. Uploading an image again creates a new valid job.
- The GIS user reads the status of their own jobs (`queued`, `running`, `succeeded`, `failed`, `expired`) and downloads their own results: a uint8 class mask (0–7, 255 for invalid input pixels), a colour overlay, a legend and JSON metadata with model and taxonomy versions.
- When the input GeoTIFF has a valid CRS and affine transform, the mask is also delivered as a GeoTIFF on the same grid. Otherwise it is a pixel-grid mask.
- Images of any size and aspect ratio are processed in overlapping tiles and stitched back to the source pixel grid.
- The operator ingests a labelled training batch, trains a candidate from the approved model, compares them, approves or blocks the candidate, and rolls back to an earlier approved version.
- The GIS assistant answers questions about the export from the project documentation and calls the same validated inspect, segment, validate and export functions. It cannot change models or infrastructure.

**Non-functional requirements:**

| Category | Requirement |
|---|---|
| Freshness | Applies to training batches only. A batch is new when its manifest contains at least one file checksum absent from committed batches. A batch with no new checksums fails before training and alerts the operator. A deliberate replay is allowed and adds no duplicates. Inference uploads have no freshness rule. Assumption: at most one labelled batch per month, because each update needs an operator review |
| Latency and throughput | Acknowledgement p95 ≤ 1 s; completion p95 ≤ 5 min for a 4096×4096 image at 1000 images/month with 20% of a day's jobs in the peak hour. 1–4 workers. Queue wait is measured separately from processing |
| Availability and fallback | The cloud service runs continuously. Jobs and results survive a host failure in PostgreSQL and object storage; an interrupted job is retried after its lease expires, up to 3 attempts. Without a loadable approved model, workers report not-ready and jobs stay queued; no mask is fabricated. An LLM provider outage returns an error, keeps the task state and allows a retry. No high-availability or uptime percentage is promised |
| Reproducibility | Every training run records data version, code commit, configuration, preprocessing, taxonomy version, parent model and seeds. Target: every registered model version can be rebuilt by one command from a clean clone; the same batch run twice gives identical row counts. Bit-identical GPU weights are not required |
| Adaptability | A new labelled batch fine-tunes the approved full checkpoint, mixed with older OEM training tiles so that the model does not forget learned classes. Assumption: the first experiments use 50% old tiles, an equal share so that neither source dominates; development-control results choose the final share. New architectures enter the same way. Only the operator activates a version (Section 5.5) |
| Observability without ground truth | Uploads have no true masks, so live IoU cannot be computed. The service monitors job failures, latency, per-image input statistics and predicted class shares in daily windows against a reference window (Section 6.6). IoU is computed only for labelled batches, at ingestion |
| Cost and resource ceilings | Cloud service: about $302/month at listed rates and $338 in a training month (Section 6.7). Per job: 128 MiB encoded upload, 64 megapixels decoded, one worker with 1 vCPU and 4 GiB RAM, 15-minute execution deadline |

**Course constraint:** the course runs the same components on one Mac (Apple M4 Pro, 24 GiB) under Minikube with one operator and $0 paid spend. Owned Colab Pro supplies training GPUs.

**In scope:** eight-class land-cover rasters, the GIS package, supervised model updates with operator approval, monitoring, and the GIS assistant. **Out of scope:** object detection and building counting, guaranteed accuracy in other geographies, invented georeferencing, area statistics in square metres, simulator terrain such as heights, materials or 3D, high availability, and training on user uploads.

**Conflicts:** a correct grid wins over a faster export. The cost ceiling wins over burst latency: at four workers extra jobs wait in the queue. The 24-hour privacy limit wins over inference reproducibility: an expired upload cannot be replayed without uploading it again.

## 5.1 Problem statement

The task is multiclass semantic segmentation: each valid RGB pixel receives exactly one of the eight OEM classes. The taxonomy below is version 1 of the product contract; ID 255 marks pixels that are ignored in training and invalid input pixels in the output.

| ID | OEM raw ID | Class |
|---:|---:|---|
| 0 | 1 | bareland |
| 1 | 2 | rangeland |
| 2 | 3 | developed space |
| 3 | 4 | road |
| 4 | 5 | tree |
| 5 | 6 | water |
| 6 | 7 | agriculture land |
| 7 | 8 | building |
| 255 | 0 | ignore / invalid |

**Rejected framing:** building-only (binary) segmentation. It is simpler and well studied, but the GIS layer must also separate roads, vegetation, water and agricultural land, so it would not deliver the requested map.

## 5.2 Data

| Source | Content | Role |
|---|---|---|
| [OpenEarthMap](https://arxiv.org/html/2210.10732) ([release](https://zenodo.org/records/7223446)) | 0.25–0.5 m RGB aerial images with human masks for the eight classes; 9.1 GB archive. xBD images are downloaded separately | Initial training of both models; development and final controls |
| [FLAIR-HUB](https://huggingface.co/datasets/IGNF/FLAIR-HUB) ([paper](https://arxiv.org/html/2506.07080v1)), IGN France | 0.2 m aerial RGB and NIR; CoSIA masks drawn by expert photo-interpreters; one archive per département and year | Supervised update batches in acquisition-year order; regional controls |
| [Utah NAIP](https://gis.utah.gov/products/sgid/aerial-photography/naip/) | Public-domain 0.6 m imagery without masks | Optional unlabelled inference and drift-monitoring stream |
| GIS user uploads | RGB images without masks | Serving only |

**Update timeline.** Only the RGB and CoSIA archives of six FLAIR-HUB domains are used: 4.88 GB compressed in total. Each domain is a different département, so all patches of one domain stay in one role.

| Order | Data | Role |
|---|---|---|
| 0 | OEM training regions | Initial training |
| 1 | D080-2017 | Update |
| 2 | D033-2018 | Update |
| 3 | D065-2019 | Update |
| 4 | D045-2020 | Update |
| — | OEM development regions; D017-2021 | Development controls: model selection and every promotion decision |
| — | OEM final regions; D073-2022 | Final holdouts: evaluated once, after the protocol and model are frozen |

This is a retrospective replay across acquisition years and regions. Each batch changes year and region together, so the scores measure transfer to later external acquisitions; they do not isolate change at one place, and they do not show what a model could have achieved in 2017, because OEM and the ImageNet encoder were published later. Adding a second 2022 domain to the final holdout is possible only if the list is frozen before any score is seen. Image–mask pairing, class histograms and overlap are checked in the first data pilot.

**Label mapping.** OEM raw IDs map 1–8 → 0–7 and 0 → 255 ([OEM class codes](https://raw.githubusercontent.com/bao18/open_earth_map/main/open_earth_map/utils.py)). FLAIR-HUB uses its own IDs 0–18, which differ from FLAIR-1/2 ([label configuration](https://github.com/IGNF/FLAIR-HUB/blob/main/configs/train/config_supervision.yaml)). Crosswalk version 1 maps only unambiguous classes:

| FLAIR-HUB class (ID) | OEM ID |
|---|---:|
| building (0) | 7 |
| bare soil (5) | 0 |
| water (6), swimming pool (2) | 5 |
| coniferous (13), deciduous (12) | 4 |
| herbaceous vegetation (8) | 1 |
| agricultural land (9), vineyard (11) | 6 |
| all other IDs, including pervious and impervious surfaces, brushwood and plowed land | 255 |

FLAIR therefore supervises six classes: 0, 1, 4, 5, 6 and 7. Its impervious class mixes roads, parking and construction, so road (3) and developed space (2) are learned and checked only on OEM. The model always keeps eight outputs.

**Lab 1 data checklist:**

1. **Time axis.** FLAIR-HUB domains carry real acquisition years from 2017 to 2022; one domain is ingested per batch in year order. The cost is that year and region shift together. OEM has no usable time axis; it supplies the base model and fixed controls.
2. **History and holdout.** Four update years (2017–2020) are followed by a 2021 development domain and a 2022 final domain. OEM is split by region before cropping, so neighbouring tiles of one scene never appear in two roles.
3. **Labels and delay.** FLAIR expert masks arrive with the images, so the delay at ingestion is zero. A Lab 4 exercise may withhold labels for one scheduled batch; that is a declared simulation. Uploads never receive masks.
4. **Corpus.** The retrieval corpus is named in the table below.

**Dates.** The fields `acquisition_start`, `acquisition_end`, `date_precision`, `label_reference_period`, `source_published_at` and `ingested_at` are all nullable. A missing date stays null and processing continues; a year never becomes an invented 1 January. Inference never needs a date.

**Manifest and freshness, by example.** A manifest is a JSON file that lists every file of a batch with its SHA-256 checksum, size, source ID and any known acquisition dates. Its digest is computed from content only, so the same files always give the same digest. The watermark is the last committed batch.

1. The operator ingests D065-2019. The pipeline validates it, commits dataset version 3 and only then moves the watermark to 3.
2. The next scheduled run points at the same folder again. The new manifest has no checksums that version 3 lacks, so the run fails before training with a stale-input alert. The watermark stays at 3.
3. The operator reruns D065-2019 with `replay=true`. The pipeline reuses version 3 and writes no duplicate rows.

A GIS user who uploads an image twice gets two results; this check never touches uploads.

**Storage and versioning:**

| Artifact | Format | Local | Cloud | Versioned by |
|---|---|---|---|---|
| Raw source archives, images and masks | Original ZIP, TIFF, PNG | Object storage (MinIO-compatible pgsty/silo) | Amazon S3 | DVC content hashes |
| Clean tiles and remapped masks | GeoTIFF or PNG, uint8 masks | Object storage | S3 | DVC; one `.dvc` pointer per dataset version in Git |
| Manifests, split lists, taxonomy and crosswalk | JSON | Git | Git | Git commit |
| Jobs, users, batches, watermark | PostgreSQL tables | PostgreSQL 16 | RDS for PostgreSQL | Schema migrations in Git |
| Runs, metrics, model versions, serving alias | MLflow metadata in PostgreSQL, files in object storage | MLflow | MLflow on EC2 with RDS and S3 | MLflow model versions |
| Uploads and results | Original file; GeoTIFF, PNG and JSON results | Temporary bucket | Temporary S3 bucket without versioning | Not versioned; deleted 24 h after acceptance |
| Retrieval corpus | Source snapshots; text chunks with pgvector embeddings | Object storage, PostgreSQL | S3, RDS | Snapshot SHA-256, `doc_version`, index version |

Raster bytes stay in raster formats; converting pixels to CSV or Parquet would only add a conversion step. There is no separate feature table: tensors are computed from the tiles during training and inference. Per-job statistics for monitoring are PostgreSQL rows.

**Git, DVC and Git LFS.** Git stores code, configuration, documentation, `uv.lock`, small JSON manifests and DVC pointer files. DVC stores large raster and checkpoint files in object storage under content hashes; `dvc pull` restores exactly the data version a commit points to. Git LFS also keeps large files out of Git history, but it only stores and fetches them. DVC adds pipeline stages that know when derived data must be rebuilt, and it uses the same object storage as the rest of the system, so Git LFS is not used. Manifests are JSON because they are small, readable and diffable in Git.

**Retrieval corpus:**

| `doc_id` | Document |
|---|---|
| `oem-paper` | [OpenEarthMap paper](https://arxiv.org/html/2210.10732): class definitions (S1), data and splits (2.2) |
| `flair-hub` | [FLAIR-HUB paper](https://arxiv.org/html/2506.07080v1) and the pinned [label configuration](https://github.com/IGNF/FLAIR-HUB/blob/main/configs/train/config_supervision.yaml) |
| `naip-dictionary` | [USGS NAIP data dictionary](https://www.usgs.gov/centers/eros/science/national-agriculture-imagery-program-naip-data-dictionary): dates, bands, resolution |
| `qgis-raster` | [QGIS 3.44 raster properties](https://docs.qgis.org/3.44/en/docs/user_manual/working_with_raster/raster_properties.html) |
| `export-contract` | Sections 5.1 and 6.8 of this document |

Each snapshot records source URL, access date, SHA-256 and `doc_version`; every chunk references `doc_id`, `doc_version` and a section locator, so answers cite exact sources.

## 5.3 Techniques

**Baseline: random forest on RGB texture features.** [`skimage.feature.multiscale_basic_features`](https://scikit-image.org/docs/stable/api/skimage.feature.html#skimage.feature.multiscale_basic_features) computes intensity, edge and texture features at scales 1, 2, 4 and 8 pixels. A scikit-learn [`RandomForestClassifier`](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html) with 100 trees and maximum depth 12 is fitted on at most 10,000 sampled valid pixels per class from the OEM training regions, with a fixed seed. It returns the same eight-class mask on CPU without pretrained weights. The classifier is fitted directly after removing ID 255, because [`skimage.future.fit_segmenter`](https://scikit-image.org/docs/stable/api/skimage.future.html#skimage.future.fit_segmenter) treats label 0 as unlabelled and would drop bareland. Assumption: these starting parameters fit in a few minutes on CPU, because the sample is capped at 80,000 pixels.

The baseline could remain the production model if its per-class IoU and the GIS users' correction effort were acceptable. We expect it to confuse classes that differ by context rather than colour, such as road versus developed space and agriculture versus rangeland.

**Candidate: U-Net with an EfficientNet-B4 encoder.** It is built with [segmentation_models_pytorch](https://github.com/qubvel-org/segmentation_models.pytorch) 0.5.0:

```python
smp.Unet(encoder_name="tu-tf_efficientnet_b4.in1k", encoder_weights="imagenet",
         in_channels=3, classes=8, activation=None)
```

The encoder starts from the [timm ImageNet checkpoint](https://huggingface.co/timm/tf_efficientnet_b4.in1k) (Apache-2.0). Preprocessing divides RGB by 255 and normalizes with mean (0.485, 0.456, 0.406) and standard deviation (0.229, 0.224, 0.225). Training and serving use 512×512 tiles with the same overlap and padding. In the OEM benchmark this architecture reached 68.20 mIoU with 20.3 M parameters and the best result with 10% of labels ([OEM Tables 3 and 5](https://arxiv.org/html/2210.10732)). That score is architecture evidence: it does not establish the accuracy or CPU speed of our checkpoint.

ImageNet weights initialize only the first OEM training run. Every update resumes the approved full checkpoint, including decoder and head, and trains on the new batch mixed with replayed OEM tiles. No teacher model is needed: every training batch has expert masks, and unlabelled images serve only inference and monitoring.

**Features and their serving-time sources:**

| Input | Training source | Serving source |
|---|---|---|
| RGB pixels, 8-bit | OEM and FLAIR adapters; FLAIR's NIR band is dropped | Uploaded file, same channel order |
| Normalization and tiling | Configuration stored with the checkpoint | The same configuration, loaded from the model version |
| Random-forest texture features | Computed from training tiles | Computed from the upload with the same feature configuration |
| Masks | OEM and FLAIR labels after remapping | None; inference does not need them |
| CRS and affine | Not a model input | Read from the uploaded GeoTIFF and copied to the output |
| Augmentation | Random flips and rotations, applied to image and mask together | None |

RGB pixels show how a source can differ between paths: in training they come from curated archives through a fixed adapter, at serving time from whatever file the user uploads. The first version accepts only 8-bit RGB. A later adapter converts known 16-bit and other containers to canonical 8-bit RGB; an image whose band meaning is unknown is rejected unless the user states which bands are red, green and blue.

**Model alternatives, revisited after the first implementation:**

| Model | Evidence | Trade-off for this system |
|---|---|---|
| [FT-UNetFormer / Swin-B](https://arxiv.org/abs/2109.08937) ([GeoSeg code](https://github.com/WangLibo1995/GeoSeg)) | 69.13 OEM mIoU in the same benchmark | +0.93 points for about 4.7× the parameters; GPL-3.0 research code pinned to Python 3.8; backbone weights without stated terms |
| [SatlasPretrain Aerial Swin-v2-Base](https://arxiv.org/abs/2211.15660) ([package](https://github.com/allenai/satlaspretrain_models)) | Pretrained on NAIP aerial imagery; ships a segmentation head | No published OEM-8 result; larger backbone; ODC-BY weight terms; documented for 0.5–2 m imagery, coarser than FLAIR's 0.2 m |

Both are compared on architecture, pretraining, taxonomy fit, benchmark protocol, CPU and RAM fit, licensing and independence from our controls.

## 5.4 Experimentation and validation

A random split would place neighbouring tiles of one scene in both training and evaluation and overstate accuracy. The split is therefore by region and, for FLAIR, by acquisition year.

1. **Split.** Assign whole OEM regions, before cropping, to training, development and final roles. Assumption: 70%, 15% and 15% of regions, stratified so that every class appears in each role. FLAIR domains take the roles in Section 5.2. Freeze both final holdout lists before any model is scored.
2. **Train.** Fit the random forest and train the first U-Net on the OEM training regions. Each update fine-tunes the approved model on the next FLAIR batch with OEM replay. Replay share and learning rate are selected on the development controls only.
3. **Compute the metric.** Sum one 8×8 confusion matrix over all valid reference pixels of a control; do not average per tile. Class IoU = TP / (TP + FP + FN). A prediction of road on a FLAIR tree pixel counts as a false negative for tree and a false positive for road. Every report lists the scored class IDs, pixel support, ignored fraction and the number of classes in the mean. A control that lacks support for a class it should cover makes the evaluation incomplete, and no decision is taken on it. OEM-8 mIoU and the six-class regional mIoU are reported separately and never averaged.
4. **First neural approval.** Compare the random forest and the first U-Net on the same OEM development control. The U-Net is eligible when its OEM-8 mIoU exceeds the random forest's and it passes the export and resource checks. Its regional score is reported but not gated.
5. **Update approval.** Compare each candidate with the currently approved model, not with the baseline, on the same frozen development manifests. Under the **selected policy** a candidate is eligible when all of these hold:
   1. OEM-8 mIoU is at least the approved model's value.
   2. Regional mIoU is higher than the approved model's value.
   3. No OEM class loses more than **2 percentage points** of IoU. Exactly 2 points is allowed; the difference is absolute IoU, not a relative percentage.
   4. Class coverage, export validity and resource checks pass.
6. **Strict alternative.** The same rules, except that no OEM class may lose any IoU. It protects every class but blocks an update whose regional gain costs a small loss elsewhere. The 2-point tolerance is a starting policy; experiments on the development controls may tighten it.
7. **Final evaluation.** After the last update, evaluate the approved model once on the OEM final regions and D073-2022. Final holdouts are never used for tuning, replay selection or promotion decisions.

Hypothetical examples (illustration, not measurements):

| Model | OEM mIoU | Regional mIoU | Largest OEM class loss | Selected policy | Strict alternative |
|---|---:|---:|---:|---|---|
| Approved model | 60.0% | 50.0% | — | — | — |
| Candidate A | 60.4% | 52.0% | 1.5 pp | Eligible | Fails |
| Candidate B | 60.4% | 52.0% | 0 pp | Eligible | Eligible |
| Candidate C | 60.1% | 51.0% | 2.0 pp | Eligible | Fails |
| Candidate D | 60.6% | 50.0% | 0 pp | Fails: no regional gain | Fails |

Passing a gate makes a candidate eligible for review; it does not activate it (Section 5.5).

## 5.5 Human in the loop

**Promotion** means moving the MLflow registry alias `champion` to a new model version; the service always loads its model through that alias.

- **Drift and failure alerts** go to the operator by email. The operator checks the report and sample overlays, then fixes the cause, schedules a labelled batch or records that the alert needs no action.
- **Candidate review.** The operator receives the comparison report from Section 5.4 and up to five example overlays. They approve by moving `champion` to the candidate version. A blocked candidate stays a run artifact and never becomes the base of the next update.
- **Override.** The operator can block a candidate that passes every gate, for example when overlays show tiling seams in exports, or roll back by moving `champion` to any earlier approved version.
- **Rollout.** Workers resolve `champion` once at start-up, load that immutable version and record it on every job. After an alias change the operator triggers a rolling restart: old workers finish their current jobs, new workers load the new version. A running job always finishes with its recorded version.
- **GIS users** cannot promote models. They may correct a mask in QGIS; that edit stays in their own map and does not enter training in the first version.

Lifecycle artifacts: training run → registered candidate version → `champion` alias → monitoring reports → next candidate. Every approved version stays in the registry for audit and rollback.

## 6.1 High-level design

![System context: OEM, IGN FLAIR-HUB, USGS/UGRC NAIP and documentation publishers feed the land-cover service; the GIS user exchanges images and map packages; the operator receives alerts and sends batches and approvals](diagrams/context.svg)

*Figure 1. System context. Everything outside the box belongs to someone else.*

![Seven-layer data flow from ingestion to monitoring, with the version point, the quality gate, the offline and online sides of the feature layer, the registry alias and the retraining loop](diagrams/data-flow.svg)

*Figure 2. Data flow on the seven layers. Training batches pass the freshness check; uploads never do.*

![Deployment draft: the local Minikube components with the managed AWS equivalent under each, the LLM runtime on the Mac host and Colab Pro as the training resource](diagrams/deployment.svg)

*Figure 3. Deployment, first draft. Lab 4 replaces it with the real cluster topology. The selected cloud deployment is in Section 6.2.*

## 6.2 Infra

| Component | Local (course) | Selected cloud | Managed equivalent | Reason for the cloud choice |
|---|---|---|---|---|
| Segmentation service: API, web UI, workers | FastAPI and worker containers in Minikube | ECS on EC2: core host plus burst group | EKS | ECS adds no control-plane fee; EKS costs $73/month more and brings no availability by itself |
| GIS assistant | Container in Minikube | ECS on EC2, core host | EKS | Same host as the API |
| Object storage | pgsty/silo (MinIO-compatible) | Amazon S3 | Amazon S3 | S3 is cheaper per GB than a disk and adds managed durability |
| Data versioning (DVC remote in object storage) | DVC with object-storage remote | DVC with S3 remote | S3 remote | Same tool in both places |
| PostgreSQL + pgvector | PostgreSQL 16 with pgvector | RDS for PostgreSQL db.t4g.small, Single-AZ, with pgvector | RDS for PostgreSQL; OpenSearch Serverless for vectors | Managed backups and patching for $23.60/month more than self-hosting |
| Airflow (orchestrator) | Airflow 3.3.1, LocalExecutor | Self-hosted Airflow on the core host | Amazon MWAA | A few scheduled DAGs do not justify $358/month |
| MLflow (tracking and registry) | MLflow 3.16.1 with authentication | Self-hosted MLflow on the core host | SageMaker AI serverless MLflow App | Keeps the course's pinned version and alias permissions |
| Monitoring | Prometheus, Grafana, Alertmanager, Evidently job | Same, self-hosted; CloudWatch alarms and SNS for host and health-check alerts | CloudWatch; SageMaker Model Monitor | Model Monitor is closed to new customers and tabular; a monitor on a failed host cannot report its own failure |
| LLM and embeddings | Host-native llama-server (Metal): Gemma 4 12B QAT Q4_0; Qwen3-Embedding-0.6B | Bedrock: Claude Sonnet 5.5; Titan Text Embeddings V2 | Amazon Bedrock | One always-on GPU costs $587.50/month before disks; the API costs $124.82 at the assumed load |
| Identity | Pre-provisioned per-user tokens with roles | Amazon Cognito | Amazon Cognito | A self-hosted identity server adds a database and patching |
| Minikube and container registry | Minikube with its registry | ECS on EC2; Amazon ECR | EKS; ECR | As above |
| Training resource | Colab Pro (owned); Mac for small runs | EC2 g6.xlarge on demand, 40 h budget | SageMaker Training | Pay only for training hours |
| Feature store | Not needed | Not needed | SageMaker Feature Store | No entity features to look up online; tensors come from the image with versioned preprocessing |

Two application services have readiness checks. The segmentation service is ready only when it has loaded the `champion` model and its preprocessing configuration; a missing model fails the probe. The assistant is ready only when its LLM endpoint and corpus index respond.

**Training exchange.** Colab cannot reach the local MLflow, and it does not need to. A training run writes to Google Drive `model.pt` (weights), `checkpoint.pt` (optimizer, scheduler, epoch and RNG state, for resuming an interrupted run), `metrics.json` and `run.json` (commit, dataset digest, configuration, seed, SHA-256 of the weights). The operator downloads the folder, and an import command verifies the hashes, rebuilds the model on CPU from the recorded code and configuration, logs the run to MLflow and registers a model version.

**MLflow and W&B.** MLflow is the authoritative record of runs, artifacts, model versions, approval and traces; Lab 2 names it. [W&B](https://coreweave.com/forge-pricing) may additionally stream live training curves from Colab:

| | MLflow | W&B (optional) |
|---|---|---|
| Role | Runs, registry, `champion` alias, traces | Live curves during a Colab run |
| Cost and access | Self-hosted, no account | Account; free plan has 5 GB storage |
| Authority | Promotion decisions | None |

**LLM choices.** Locally the assistant uses [Gemma 4 12B QAT Q4_0](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) through [llama.cpp](https://github.com/ggml-org/llama.cpp) on the Mac host with Metal, because Docker containers on the Mac have no GPU; its 6.98 GB weight file leaves room in 24 GiB. In the cloud it uses [Claude Sonnet 5.5 on Bedrock](https://platform.claude.com/docs/en/models/overview). [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) is a separately integrated and evaluated alternative; there is no automatic failover between providers. Embeddings use [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) locally and [Titan Text Embeddings V2](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html) in the cloud, provided it passes the Ukrainian-to-English retrieval evaluation. Changing the embedding model rebuilds the index under a new version. Lab 3 and Lab 5 evaluations decide whether these models are good enough.

**Cloud placement.** One always-on m6a.xlarge core host (4 vCPU, 16 GiB) runs the HTTPS proxy, both APIs, Airflow, MLflow, Prometheus and Grafana and one inference worker. A burst Auto Scaling group of 0–1 identical hosts adds up to three workers. RDS is private and reachable only from the hosts. The hosts sit in a public subnet without a NAT gateway: ECS tasks use bridge networking, IMDS is blocked for containers, and each task has its own IAM role. S3 traffic uses a free gateway endpoint. A Route 53 record points to an Elastic IP that a replacement core host re-associates at boot.

## 6.3 Performance

**Batch versus online.** Each upload is processed online as an asynchronous job. A nightly batch would make the GIS user wait a day; a synchronous request would hold an HTTP connection for minutes on a large raster. The API stores the job and returns its ID; workers claim jobs from a PostgreSQL table with `FOR UPDATE SKIP LOCKED`, so adding workers adds throughput.

| Item | Assumption and reason |
|---|---|
| Load | 20 active users, 1000 images and 1000 assistant tasks a month; 20% of a day's jobs arrive in the peak hour. 2200 images is the growth case |
| Reference image | 4096×4096 RGB; 50 MB upload and 50 MB results on average |
| Service time | 60 s per reference image on one worker with 1 vCPU, covering decode, tiling, inference, stitching and export. This is the capacity input until the first measurement |
| Worker ceiling | 1 CPU thread, 4 GiB RAM, 512×512 tiles, batch size 1; 1–4 workers |
| Input bounds | 128 MiB encoded, 64 megapixels decoded, 15-minute execution deadline, never later than the upload's expiry. They bound disk, decoding memory and work time; the 4096×4096 example is not a limit |

**Worker count.** Peak arrivals are 1000 / 22 working days × 0.2 = 9.09 jobs per hour. At a target utilization of 0.6, ceil(9.09 × 60 / (3600 × 0.6)) = 1 worker covers the mean load; bursts scale to four. The autoscaler targets at most 2 queued jobs per worker, with a 10-minute scale-in cooldown. On the core host the services and one worker reserve 3.25 of 4 vCPU and 12.125 of 16 GiB; a burst host fits three workers. The mean-load formula gives no p95; the load test does.

**Measurement method.** Run the worker image with exactly 1 vCPU and 4 GiB. Measure cold start separately, then 5 warm-up and 30 measured runs at 1024×1024 and 4096×4096, recording decode, inference, stitching and export times and peak memory. Then replay twice the peak arrival rate for one hour and read acknowledgement p95, queue wait and completion p95. If completion p95 exceeds 5 minutes, try ONNX Runtime or larger tiles, then more workers within the cost ceiling, before relaxing the target.

## 6.4 Security

- **Authentication.** In the cloud, users sign in with Cognito; the API checks the token's issuer, audience, signature and expiry. Locally, pre-provisioned per-user tokens map to the `gis_user` and `operator` roles.
- **Authorization.** A GIS user creates jobs and reads only their own jobs and results. Only the operator ingests training batches, starts training and changes the registry. MLflow runs with authentication; only the operator credential can move `champion`, and workers have read-only access.
- **Secrets.** Locally in an ignored `.env` file; in the cloud in SSM Parameter Store SecureString with KMS, read through per-task IAM roles. Secrets never enter Git, images or logs.
- **Network.** Only the HTTPS proxy is public. PostgreSQL, Airflow, MLflow and Grafana are private and reached through SSM.
- **Input checks.** The API enforces the size bounds from Section 6.3 before decoding the whole image, generates object keys itself, rejects archives and rejects images with unknown band meaning.
- **Assistant.** User requests and retrieved documents are data, not instructions. Every tool call is validated in code and runs with the calling user's permissions; no tool can promote a model or change infrastructure.

## 6.5 Data privacy

Uploads may show private property, people and vehicles, and a GeoTIFF reveals its location, so each upload is visible only to its owner and the operator.

- **Uploads and results** expire at `expires_at = accepted_at + 24 h`. After expiry, access is denied, signed URLs are never valid past `expires_at`, a queued job does not start and a running job is cancelled; a late output is discarded and cannot extend the expiry. Deletion is due at `expires_at` and is monitored (Section 6.6). The temporary bucket has no object versioning, so no old copies remain.
- **Logs and metrics** are kept for 30 days and contain user and job IDs, sizes, timings and errors; they contain no image bytes, file names, coordinates or secrets.
- **Training data** comes only from the public datasets in Section 5.2 and is kept for the life of the project with source attribution. OEM label licences default to CC BY-NC-SA 4.0 and FLAIR-HUB uses Etalab Open Licence 2.0; the project does not redistribute either dataset.
- **No user feedback** enters training in the first version: user images and QGIS corrections are never added to training data.

## 6.6 Monitoring and alarms

All alerts go to the operator by email: Alertmanager for application rules, CloudWatch and SNS for rules that must work when the host is down. Each alert has an event key, so one incident sends one email.

| Signal | Window and threshold | Reason | Action |
|---|---|---|---|
| Job failures | Rolling 1 h: ≥ 3 system failures, or > 1% of valid jobs per week | 1% is the system target in Section 3; 3 in an hour indicates a fault, not chance | Operator reads job errors and worker logs |
| Latency | Rolling 15 min: completion p95 > 5 min, or the oldest queued job waits > 10 min while 4 workers run | The p95 target; a long queue at full scale means the ceiling is too low | Operator checks worker health and limits |
| Service health | External HTTPS check every minute fails 3 times; or a worker reports not-ready because `champion` cannot be loaded | Host or model loss stops all jobs | Operator replaces the host or rolls back the alias |
| Training batch gate | Every run: any invalid file (format, image–mask grid mismatch, unknown class ID), or zero new checksums | Catches a bad batch and a repeated old batch; the watermark does not move | Run fails; operator fixes or replaces the batch |
| Input drift | Daily, last 7 days against the reference window: Population Stability Index > 0.25 on per-image channel means or image size, with at least 50 images | Assumption: 0.25 is the conventional level for a large shift; a reference-against-reference comparison calibrates it once two windows exist. Below 50 images the report says "insufficient data" | Operator reviews sample overlays and may schedule a labelled batch |
| Predicted class shares | Daily against the reference window: any class share over valid pixels changes by > 10 percentage points, with at least 50 images | The model can behave differently even when input statistics look stable | As for input drift |
| Expiry cleanup | Hourly: any upload or result older than `expires_at` + 1 h | The 24-hour privacy guarantee | Operator runs the cleanup and checks the job |

Accuracy needs reference masks: when a labelled batch arrives, the pipeline first scores the approved model on it. That IoU is the only accuracy measurement on new data; between batches, the signals above are the proxies.

## 6.7 Cost

Prices are AWS us-east-1 On-Demand rates in USD, read on 2026-10-23, for a 730-hour month, before tax and operator time. Sources: [EC2](https://aws.amazon.com/ec2/pricing/on-demand/), [RDS](https://aws.amazon.com/rds/postgresql/pricing/), [S3 and internet transfer](https://aws.amazon.com/s3/pricing/), [VPC IPv4](https://aws.amazon.com/vpc/pricing/), [ECR](https://aws.amazon.com/ecr/pricing/), [Route 53](https://aws.amazon.com/route53/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [SNS](https://aws.amazon.com/sns/pricing/), [SES](https://aws.amazon.com/ses/pricing/), [Cognito](https://aws.amazon.com/cognito/pricing/), [KMS](https://aws.amazon.com/kms/pricing/), [Bedrock](https://aws.amazon.com/bedrock/pricing/).

**Workload assumptions:**

- 20 active users, 1000 images and 1000 complete assistant tasks a month (Section 2).
- Each image stores 0.1 GB (upload and results) for one day out of thirty: ceil(1000 × 0.1 GB × 1/30) = 4 GB on average. With 100 GB of persistent data (OEM and FLAIR archives, extracted copies, tiles, checkpoints, reports) S3 holds 104 GB.
- 60 GB internet output: 50 GB of results and 10 GB of API traffic. 10,000 S3 PUT and 100,000 GET requests.
- An assistant task makes five sequential model calls (inspect, segment, validate, export, explain); the conversation history grows with each call, giving 32,000 input and 4,000 output tokens per task. With 20% for retries and evaluation: 38.4 M input and 4.8 M output tokens, $124.80 with Sonnet 5.5 at $2 and $10 per million. Titan embeddings for 1.1 M tokens add $0.022.
- A training month adds 20 burst CPU-host hours and 40 g6.xlarge GPU hours. These are budgets, not measured training times.

| Component | Basis | USD/month |
|---|---|---:|
| Core EC2 host, disk, public IPv4 | m6a.xlarge 730 h × $0.1728; 50 GB gp3 × $0.08; IPv4 730 h × $0.005 | 133.794 |
| RDS for PostgreSQL | db.t4g.small Single-AZ 730 h × $0.032; 20 GB gp3 × $0.115 | 25.660 |
| S3 | 104 GB × $0.023; requests | 2.482 |
| ECR | 5 GB × $0.10 | 0.500 |
| DNS, domain, health check | Hosted zone and 0.1 M queries; .com $16/year; HTTPS check | 3.373 |
| CloudWatch, SNS, SES | 5 GB logs; 5 custom metrics; 7 alarms; 100 SNS and 1000 SES emails | 5.390 |
| Cognito, KMS | 20 MAU; 10,000 requests | 0.330 |
| Internet output | 60 GB × $0.09 | 5.400 |
| Sonnet 5.5 and Titan V2 | 38.4 M × $2 + 4.8 M × $10 per million; 1.1 M × $0.02 | 124.822 |
| **Steady month** | | **301.75** |
| Burst CPU host, training month | 20 h × (m6a.xlarge + IPv4 + 50 GB disk share) | 3.666 |
| GPU training, training month | 40 h × (g6.xlarge $0.8048 + IPv4 + 100 GB disk share) | 32.830 |
| **Training month** | | **338.25** |

When the account's recurring free allowances are unused, they cover $12.52: the first 100 GB of internet output, the CloudWatch volumes above, Cognito MAU, the health check, KMS requests and SNS emails.

| Scenario | Steady | Steady with allowances | Training month | Training month with allowances |
|---|---:|---:|---:|---:|
| 1000 images and tasks | $301.75 | **$289.23** | $338.25 | **$325.73** |
| 2200 images and tasks | $460.29 | $444.17 | $496.79 | $480.67 |

The 2200 case keeps users, model and retention, and scales storage to 108 GB, requests to 22,000 and 220,000, internet output to 120 GB, logs to 11 GB and LLM cost to $274.58. The LLM is 41% of the steady month, so agent token use is the assumption most likely to make this estimate wrong; Lab 3 records tokens per task.

The earlier public AWS Calculator estimate ($1,229.81) priced the superseded EKS, MWAA and legacy-MLflow design and no longer applies. A replacement calculator estimate with these inputs is pending; its link will be added here once it is saved. Actual course spend is $0.

## 6.8 Integration points

No public publisher promises us freshness or availability. We pin each source's revision and checksums and define our own acceptance rules.

| Boundary | Payload and format | Timing | Responsibility and failure behaviour |
|---|---|---|---|
| OEM authors → ingestion | Zenodo release: RGB images, masks, metadata; xBD images from xview2.org | Once, for the initial batch | We record the release ID and checksums, remap labels, and reject a batch with mismatched grids or unknown IDs as a whole |
| IGN (FLAIR-HUB) → ingestion | One domain per batch: `AERIAL_RGBI` and `AERIAL_LABEL-COSIA` ZIP archives at a pinned Hugging Face revision | When the operator starts an update, at most monthly | Same checks plus the freshness rule; a missing archive fails the run and the watermark stays put |
| USGS / UGRC (NAIP) → monitoring | 4-band GeoTIFF tiles; the adapter keeps RGB | Optional, per selected year | Used only for inference and drift reports; never treated as labelled data |
| Documentation publishers → corpus | Pages and PDFs listed in Section 5.2 | Snapshotted when the corpus is built | We store snapshots with SHA-256; a changed page becomes a new `doc_version`, never an in-place edit |
| GIS user → API | One 8-bit RGB PNG, JPEG or GeoTIFF per request, within the bounds in Section 6.3 | Any time | We return a job ID within 1 s, or a validation error that names the problem |
| API → GIS user | Job status; uint8 mask (0–7, 255 invalid), overlay, legend, JSON metadata; GeoTIFF on the source grid when CRS and affine are valid | p95 ≤ 5 min; downloadable for 24 h | Metadata names the taxonomy and model versions. A failed job returns its reason and no partial package. Coordinates are never invented |
| Service ↔ operator | Alerts and candidate reports by email; batch, approval and rollback commands | Alerts as they fire; reviews per candidate | Each alert names the batch, run or model and the rule that fired. Only the operator changes `champion` |

Example: a GIS user uploads a 4096×4096 georeferenced GeoTIFF and gets a job ID. When the job succeeds, the mask GeoTIFF has the same width, height, CRS and affine transform, its metadata names taxonomy v1 and model version 4, and the legend maps IDs to class names in QGIS. A 16-bit image is rejected with "unsupported bit depth: 16; convert to 8-bit RGB" until the conversion adapter exists.

## 6.9 Risks and uncertainties

| Risk | Mitigation |
|---|---|
| FLAIR batches mix year and region shift, and their labels cover 6 of 8 classes | OEM-8 and regional scores are reported separately; road and developed space are judged on OEM controls |
| The crosswalk misreads a class, e.g. herbaceous versus grazed agriculture | Inspect class histograms and sample masks in the pilot before freezing crosswalk v1; ambiguous classes stay 255 |
| Evaluation leakage through neighbouring tiles or reused pretraining images | Split by region before cropping; never use the official OEM lightweight weights, which were trained on train and validation data |
| An update forgets road or developed space | OEM replay in every update and the 2-point per-class gate on the OEM development control |
| CPU inference is slower than the 60 s assumption | Measure first (Section 6.3); then ONNX Runtime, then more workers within the cost ceiling |
| A large or malformed raster exhausts worker memory | Size bounds before decoding, tile-by-tile processing and a 4 GiB container limit; the job fails with a reason |
| The export lands in the wrong place | CRS and affine are copied only from a valid input and checked by a QGIS round trip; otherwise a pixel-grid mask |
| The core host or the RDS zone fails | Jobs live in RDS and S3, leases return interrupted jobs to the queue, and an external health check alerts the operator |
| Agent tokens exceed the estimate | Cap turns and context per task and record tokens per run in Lab 3; Claude Haiku 5.5 is the cheaper candidate if it passes the evaluation |
| The assistant follows instructions embedded in a document | Code validates every tool argument; no tool can promote models or change infrastructure |
| A Colab session ends mid-training | `checkpoint.pt` is written to Drive every epoch and the run resumes from it |

## 7.1 Alternatives

| Alternative | Pros | Cons | Decision |
|---|---|---|---|
| Building-only segmentation | Simpler labels and model | Misses roads, vegetation, water and agriculture | Rejected framing (Section 5.1) |
| Synchronous HTTP inference | No job table or queue | Minutes-long requests time out and cannot scale across workers | Rejected; asynchronous jobs |
| Teacher pseudo-labels on unlabelled NAIP | Same-place image history | Agreement with a teacher does not measure accuracy; the official OEM weights saw our controls | Rejected; supervised FLAIR updates |
| Chesapeake LULC with NAIP as the update source | Same places in three periods | Semi-automated labels revised in later editions; scripted access to the 2024 edition unverified | Alternative if same-place history matters more ([USGS](https://www.usgs.gov/data/chesapeake-bay-land-useland-cover-lulc-database-2024-edition)) |
| FT-UNetFormer or Satlas as the first candidate | Higher published score; aerial pretraining | Larger models, harder dependencies, weight terms (Section 5.3) | Revisit after the first implementation |
| Richer taxonomy (e.g. FLAIR's coniferous and deciduous) or open-vocabulary segmentation | More classes; new concepts without a new head | A new taxonomy changes the head, legend, crosswalk and controls; a text prompt is not a validated class | Keep OEM-8; add classes when a concrete GIS need appears |
| W&B instead of MLflow | Hosted live dashboards | Account and storage limits; Lab 2 names MLflow | Optional addition only |
| MWAA and a legacy managed MLflow server | No Airflow or MLflow operations | About $797/month together | Self-hosted on the core host |
| High availability: second host, RDS Multi-AZ, load balancer | Survives one host or zone failure | About +$190/month and failover tests | Not selected; continuous single-host service |
| Learning from GIS users' corrections | Real labels for new regions | Needs consent and image licences; an "OK" click confirms the model's own errors; needs a review interface | Not in the first version |

## 7.2 Placeholder

Lab 2 fills this section with the baseline and update-candidate experiment results.

## 7.3 Placeholder

Lab 4 fills this section with deployed throughput, p50 and p95 latency and resource measurements.

## 7.4 Milestones

- **Lab 2** adds versioned data pulls, idempotent batch ingestion with a failing bad-batch gate, the random-forest baseline and U-Net candidate, and MLflow runs and models with data version and commit.
- **Lab 3** adds the versioned retrieval corpus and prompts, and evaluates the assistant with and without retrieval, logging tokens, cost and p50/p95.
- **Lab 4** deploys the segmentation service and assistant on Minikube with health probes, scheduled drift reports and an injected shift whose alert reaches the operator.
- **Lab 5** gives the assistant inspect, segment, validate and export tools, with persisted traces and ten tasks evaluated twice.

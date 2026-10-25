# Land-cover segmentation system design

This is the design of the KSE MLOps course project, written against [Lab 1](../labs/lab-1.pdf).

## 1 Overview

GIS specialists need a first land-cover layer for new aerial imagery, which they then check and edit in QGIS. The service turns an 8-bit RGB aerial image into an eight-class OpenEarthMap (OEM) mask with a colour overlay, a legend and, for a georeferenced GeoTIFF, a GeoTIFF layer on the source grid. Authenticated users submit images of different sizes, within fixed upload limits, as asynchronous jobs, and CPU workers scale with the queue. The model is trained on OEM and fine-tuned on expert-labelled batches in acquisition-year order; an operator approves each new version before it serves. The desired outcome is GIS exports that open without manual repair, and model updates that are reproducible, monitored and reversible.

## 2 Motivation

The system has two roles:

- **GIS user** (consumer): a cartographer or GIS specialist who uploads new imagery of a project area, waits for the result, imports the package into QGIS and edits the layer there.
- **Operator**: the ML engineer who owns the system. They add training batches, review alerts and candidate models, approve or block model versions and roll back. In the course this is the author; the role never merges with the GIS user.

Assumption: 20 active GIS users submit 1000 images and run 1000 assistant tasks a month; Section 6.7 also prices a 2200-image case.

A wrong class costs correction time in QGIS; a wrong grid or invented georeferencing makes the export unusable. Losing a class, such as roads, in a model update repeats the error in every later map.

A notebook is unsuitable for a continuous multi-user service. Each result needs a model version, each update a reproducible comparison and approval, and uploads without reference masks need monitoring.

## 3 Success metrics

| Level | Metric and target | How it is checked |
|---|---|---|
| Decision / workflow | At least 9 of 10 predefined valid test images give a complete package that opens in QGIS on the correct grid without manual format or georeferencing repair | Fixed test set: PNG, JPEG, georeferenced GeoTIFF and three image sizes. It measures export usability, not cartographic accuracy |
| Model | The first neural model exceeds the random-forest baseline in OEM-8 mIoU; each later update passes the promotion rule | Development controls; final holdouts once (Section 5.4) |
| System | Job acknowledgement p95 ≤ 1 s after upload; completion p95 ≤ 5 min for a 4096×4096 image at the assumed load; at most 1% of valid jobs fail for system reasons per week | Load test (Section 6.3) and monitoring (Section 6.6) |

mIoU is the optimization metric: the score we try to improve. Export validity, p95 latency and resource limits are satisficing metrics: each must pass, and a larger margin earns nothing.

## 4 Requirements and constraints

**Functional requirements:**

- An authenticated GIS user uploads one 8-bit RGB PNG, JPEG or GeoTIFF and immediately receives a job ID; uploading an image again creates a new job.
- The GIS user reads the status of their own jobs (`queued`, `running`, `succeeded`, `failed`, `expired`) and downloads their own results: a uint8 class mask (0–7, 255 for invalid input pixels), a colour overlay, a legend and JSON metadata with model and taxonomy versions.
- A GeoTIFF with a valid CRS and affine transform also yields a GeoTIFF mask on the same grid; otherwise the mask uses the pixel grid. Coordinates are never invented.
- Images of different sizes and aspect ratios, within the ceilings below, are processed in overlapping tiles and stitched back to the source pixel grid.
- The operator ingests a labelled batch, trains a candidate from the approved model, compares them, approves or blocks the candidate, and rolls back to an earlier approved version.
- The GIS assistant answers questions about the export from the project documentation with cited sources, and calls the same validated inspect, segment, validate and export functions.

**Non-functional requirements:**

| Category | Requirement |
|---|---|
| Freshness | Training batches only: a batch that adds no new file checksum fails before training (Section 5.2). Assumption: at most one labelled batch a month, because each update needs an operator review |
| Latency and throughput | Acknowledgement p95 ≤ 1 s; completion p95 ≤ 5 min for a 4096×4096 image at the assumed load (Section 6.3), with 1–4 workers; queue wait is measured separately |
| Availability and fallback | The cloud service runs continuously. Jobs and results survive a host failure in PostgreSQL and object storage; an interrupted job is retried after its lease expires, up to 3 attempts. Without a loadable approved model, jobs wait in the queue and no mask is fabricated. An LLM provider outage returns an error and keeps the task for a retry |
| Reproducibility | Every training run records data version, code commit, configuration, preprocessing, taxonomy version, parent model and seeds. Target: one command rebuilds any registered model version from a clean clone, and the same batch run twice gives identical row counts; bit-identical GPU weights are not required |
| Adaptability | New batches and architectures enter as candidates trained from the approved model (Section 5.3). Assumption: the first experiments replay 50% old OEM tiles so that neither source dominates; development controls choose the final share |
| Observability without ground truth | Uploads have no reference masks, so live IoU cannot be computed; the service monitors failures and latency, and checks input statistics and predicted class shares daily (Section 6.6). IoU is computed only on labelled batches, when they arrive |
| Cost and resource ceilings | Cloud service: about $302/month at listed rates, $338 in a training month (Section 6.7). Per job: 128 MiB encoded upload, 64 megapixels decoded, one worker with 1 vCPU and 4 GiB RAM, and a 15-minute deadline that never runs past the upload's expiry; these bound disk, decoding memory and work time |

**Course constraint:** the same components run on one Mac (Apple M4 Pro, 24 GiB) under Minikube with one operator. The author's existing Colab Pro subscription supplies training GPUs, and the course adds no paid spend.

**In scope:** eight-class land-cover rasters, the GIS package, supervised model updates with operator approval, monitoring and the GIS assistant. **Out of scope:** object detection and building counting, guaranteed accuracy in other geographies, area statistics in square metres, simulator terrain (heights, materials, 3D), high availability or an uptime percentage, and training on user uploads.

**Conflicts:** a correct grid wins over a faster export. The cost ceiling wins over burst latency: beyond four workers, jobs wait in the queue. The 24-hour privacy limit wins over inference reproducibility: an expired upload must be uploaded again.

## 5.1 Problem statement

The task is multiclass semantic segmentation: each valid RGB pixel receives one of the eight OEM classes. The taxonomy below is product-contract version 1; ID 255 marks pixels ignored in training and invalid input pixels in the output.

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

**Rejected framing:** building-only (binary) segmentation. It is simpler and well studied, but the GIS layer must also separate roads, vegetation, water and agricultural land.

## 5.2 Data

| Source | Content | Role |
|---|---|---|
| [OpenEarthMap](https://arxiv.org/html/2210.10732) ([release](https://zenodo.org/records/7223446)) | 0.25–0.5 m RGB aerial images with human masks for the eight classes; 9.1 GB, plus separately downloaded xBD images | Initial training; development and final controls |
| [FLAIR-HUB](https://huggingface.co/datasets/IGNF/FLAIR-HUB) ([paper](https://arxiv.org/html/2506.07080v1)), IGN France | 0.2 m aerial RGB and NIR with CoSIA masks drawn by expert photo-interpreters; one archive per département and year | Supervised update batches; regional controls |
| [Utah NAIP](https://gis.utah.gov/products/sgid/aerial-photography/naip/) 2018, 2021, 2024 | Public-domain 0.6 m imagery without masks | Optional drift-monitoring stream |
| GIS user uploads | RGB images without masks | Serving only |

More NAIP was considered, Utah back to 2003 (coarser before 2018) and the Chesapeake states for 2010–2023 ([Planetary Computer](https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip)), but none has human OEM-8 masks. NAIP therefore adds no update batches, and only the 0.6 m Utah vintages, closest to OEM's resolution, are kept.

**Update timeline.** Six FLAIR-HUB domains, RGB and CoSIA archives only (4.88 GB compressed). Each is a different département, so a domain stays in one role.

| Order | Data | Role |
|---|---|---|
| 0 | OEM training regions | Initial training |
| 1 | D080-2017 | Update |
| 2 | D033-2018 | Update |
| 3 | D065-2019 | Update |
| 4 | D045-2020 | Update |
| — | OEM development regions; D017-2021 | Development controls (Section 5.4) |
| — | OEM final regions; D073-2022 | Final holdouts (Section 5.4) |

**Lab 1 data checklist:**

1. **Time axis.** FLAIR-HUB domains carry real acquisition years and are ingested one per batch in year order. Year and region change together, so scores measure transfer to later acquisitions elsewhere, not change at one place, nor what a 2017 model could achieve, since OEM and the ImageNet encoder were published later. OEM has no usable time axis.
2. **History and holdout.** Four update years, then 2021 for development and 2022 for the final holdout (table above).
3. **Labels and delay.** FLAIR masks arrive with the images, so the label delay is zero; a Lab 4 exercise may withhold one batch's labels as a declared simulation. User uploads have no reference masks.
4. **Corpus.** The retrieval corpus below.

**Label mapping.** OEM raw IDs map 1–8 → 0–7 and 0 → 255 ([OEM class codes](https://raw.githubusercontent.com/bao18/open_earth_map/main/open_earth_map/utils.py)). FLAIR-HUB's own IDs 0–18 differ from FLAIR-1/2 ([label configuration](https://github.com/IGNF/FLAIR-HUB/blob/main/configs/train/config_supervision.yaml)); crosswalk version 1 maps only unambiguous classes:

| FLAIR-HUB class (ID) | OEM ID |
|---|---:|
| building (0) | 7 |
| bare soil (5) | 0 |
| water (6), swimming pool (2) | 5 |
| coniferous (13), deciduous (12) | 4 |
| herbaceous vegetation (8) | 1 |
| agricultural land (9), vineyard (11) | 6 |
| all other IDs, including pervious and impervious surfaces, brushwood and plowed land | 255 |

FLAIR therefore supervises six classes: 0, 1, 4, 5, 6 and 7. Its impervious class mixes roads, parking and construction, so road (3) and developed space (2) are learned and checked only on OEM; the model always keeps eight outputs.

**Dates.** `acquisition_start`, `acquisition_end`, `date_precision`, `label_reference_period`, `source_published_at` and `ingested_at` are nullable: a missing date stays null, processing continues, and a year never becomes an invented 1 January. Inference needs no date.

**Manifest and freshness, by example.** A manifest is a JSON list of a batch's files with SHA-256 checksum, size, source ID and any known acquisition dates; its digest depends only on content. The watermark is the last committed batch.

1. The operator ingests D065-2019; the pipeline validates it, commits dataset version 3 and only then moves the watermark to 3.
2. The next scheduled run reads the same folder: the manifest has no checksum that version 3 lacks, so the run fails before training with a stale-input alert, and the watermark stays at 3.
3. The operator reruns D065-2019 with `replay=true`; the pipeline reuses version 3 and writes no duplicate rows.

**Storage and versioning:**

| Artifact | Format | Local | Cloud | Versioned by |
|---|---|---|---|---|
| Raw archives, images and masks | Original ZIP, TIFF, PNG | Object storage (pgsty/silo) | Amazon S3 | DVC content hashes |
| Clean tiles and remapped masks | GeoTIFF or PNG; uint8 masks | Object storage | S3 | DVC; one `.dvc` pointer per dataset version |
| Manifests, splits, taxonomy, crosswalk | JSON | Git | Git | Git commit |
| Jobs, users, batches, watermark, monitoring statistics | PostgreSQL tables | PostgreSQL 16 | RDS | Migrations in Git |
| Runs, metrics, model versions, alias | MLflow: metadata in PostgreSQL, files in object storage | MLflow | MLflow on EC2 with RDS and S3 | MLflow model versions |
| Uploads and results | Original file; GeoTIFF, PNG, JSON | Temporary bucket | Temporary S3 bucket, no versioning | Not versioned; expire after 24 h (Section 6.5) |
| Retrieval corpus | Source snapshots; chunks with pgvector embeddings | Object storage, PostgreSQL | S3, RDS | Snapshot SHA-256, `doc_version`, index version |

Raster bytes stay in raster formats; CSV or Parquet would only add a conversion step.

**Git, DVC and Git LFS.** Git stores code, configuration, documentation, `uv.lock`, JSON manifests and DVC pointers.

DVC stores rasters and checkpoints under content hashes in object storage; `dvc pull` restores the data version a commit names.

Git LFS only stores and fetches large files. DVC also tracks pipeline stages and rebuilds stale derived data, so Git LFS is not used. Manifests use JSON because it is small, readable and diffable.

**Retrieval corpus:**

| `doc_id` | Document |
|---|---|
| `oem-paper` | [OpenEarthMap paper](https://arxiv.org/html/2210.10732): class definitions (S1), data and splits (2.2) |
| `flair-hub` | [FLAIR-HUB paper](https://arxiv.org/html/2506.07080v1) and the pinned [label configuration](https://github.com/IGNF/FLAIR-HUB/blob/main/configs/train/config_supervision.yaml) |
| `naip-dictionary` | [USGS NAIP data dictionary](https://www.usgs.gov/centers/eros/science/national-agriculture-imagery-program-naip-data-dictionary): dates, bands, resolution |
| `qgis-raster` | [QGIS 3.44 raster properties](https://docs.qgis.org/3.44/en/docs/user_manual/working_with_raster/raster_properties.html) |
| `export-contract` | Sections 5.1 and 6.8 of this document |

Each snapshot records source URL, access date, SHA-256 and `doc_version`; each chunk references `doc_id`, `doc_version` and a section locator.

## 5.3 Techniques

**Baseline: random forest on RGB texture features.** Each pixel is classified from intensity, edge and texture features, producing an eight-class mask on CPU without pretrained weights.

- [`multiscale_basic_features`](https://scikit-image.org/docs/stable/api/skimage.feature.html#skimage.feature.multiscale_basic_features) at scales 1, 2, 4 and 8 px.
- scikit-learn [`RandomForestClassifier`](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html): 100 trees, depth 12, fixed seed.
- At most 10,000 valid pixels per class from OEM training regions; remove ID 255.

Fit directly, without [`fit_segmenter`](https://scikit-image.org/docs/stable/api/skimage.future.html#skimage.future.fit_segmenter): label 0 (bareland) is a valid class. Assumption: fitting takes minutes on CPU with at most 80,000 pixels.

The baseline could remain in production if its per-class IoU and users' correction effort were acceptable. It will likely confuse context-dependent classes: road and developed space, or agriculture and rangeland.

**Candidate: U-Net with an EfficientNet-B4 encoder** ([segmentation_models_pytorch](https://github.com/qubvel-org/segmentation_models.pytorch) 0.5.0):

```python
smp.Unet(encoder_name="tu-tf_efficientnet_b4.in1k", encoder_weights="imagenet",
         in_channels=3, classes=8, activation=None)
```

The encoder starts from the [timm ImageNet checkpoint](https://huggingface.co/timm/tf_efficientnet_b4.in1k) (Apache-2.0).

Preprocessing divides RGB by 255 and normalizes with mean (0.485, 0.456, 0.406) and standard deviation (0.229, 0.224, 0.225). Training and serving use 512×512 tiles with the same overlap and padding.

On the [OEM benchmark, Tables 3 and 5](https://arxiv.org/html/2210.10732), it reached 68.20 mIoU with 20.3 M parameters and led with 10% of labels. This supports the architecture choice, not our checkpoint's accuracy or CPU speed.

ImageNet weights initialize only the first OEM run. Updates resume the approved full checkpoint, including decoder and head, on the new batch mixed with OEM replay to retain learned classes.

**Features and their serving-time sources:**

| Input | Training source | Serving source |
|---|---|---|
| RGB pixels, 8-bit | OEM and FLAIR adapters; FLAIR's NIR is dropped | Uploaded file, same channel order |
| Normalization and tiling | Configuration stored with the checkpoint | Same configuration, loaded with the model version |
| Random-forest features | Computed from training tiles | Computed from the upload, same configuration |
| Masks | OEM and FLAIR labels after remapping | None |
| CRS and affine | Not a model input | Copied from a valid uploaded GeoTIFF to the output |
| Augmentation | Random flips and rotations of image and mask together | None |

Serving accepts only 8-bit RGB. A future adapter will convert known 16-bit and other containers to 8-bit RGB. An image with unknown band meanings is rejected unless the user identifies its red, green and blue bands.

**Model alternatives, revisited after the first implementation:**

| Model | Evidence | Trade-off for this system |
|---|---|---|
| [FT-UNetFormer / Swin-B](https://arxiv.org/abs/2109.08937) ([GeoSeg code](https://github.com/WangLibo1995/GeoSeg), [backbone weights](https://drive.google.com/drive/folders/1ELpFKONJZbXmwB5WCXG7w42eHtrXzyPn)) | 69.13 OEM mIoU, same benchmark | +0.93 points for about 4.7× the parameters; GPL-3.0 research code pinned to Python 3.8; backbone weights only, without stated terms |
| [SatlasPretrain Aerial Swin-v2-Base](https://arxiv.org/abs/2211.15660) ([package](https://github.com/allenai/satlaspretrain_models), [`aerial_swinb_si.pth`](https://huggingface.co/allenai/satlas-pretrain/blob/main/aerial_swinb_si.pth)) | Pretrained on NAIP aerial imagery; includes a segmentation head | No OEM-8 result or checkpoint; larger backbone; ODC-BY weights; documented for 0.5–2 m imagery, coarser than FLAIR's 0.2 m |

## 5.4 Experimentation and validation

A random split would put neighbouring tiles of one scene in training and evaluation and overstate accuracy, so the split is by region and, for FLAIR, by acquisition year.

1. **Split.** Assign whole OEM regions, before cropping, to training, development and final roles. Assumption: 70/15/15% of regions, stratified so that every class appears in each role. FLAIR domains take their Section 5.2 roles. Freeze both final holdout lists, including any second 2022 domain, before any model is scored.
2. **Train.** Fit the random forest and the first U-Net on the OEM training regions; updates follow Section 5.3, with replay share and learning rate chosen on development controls only.
3. **Compute the metric.** Sum one 8×8 confusion matrix over all valid reference pixels of a control, without averaging per tile; class IoU = TP / (TP + FP + FN). A road prediction on a FLAIR tree pixel is a false negative for tree and a false positive for road. Each report lists the scored class IDs, the support (reference pixels per class), the ignored fraction and the number of classes in the mean. A control lacking support for a class it should cover makes the evaluation incomplete, and no decision is taken. OEM-8 and six-class regional mIoU are reported separately, never averaged.
4. **First neural approval.** On the same OEM development control, the U-Net is eligible when its OEM-8 mIoU exceeds the random forest's and it passes the export and resource checks; its regional score is reported, not gated.
5. **Update approval.** Each candidate is compared with the approved model, not the baseline, on the same frozen development manifests. Under the **selected policy** it is eligible when:
   1. OEM-8 mIoU is at least the approved model's.
   2. Regional mIoU is higher than the approved model's.
   3. No OEM class loses more than **2 percentage points** of IoU; exactly 2 is allowed, and the difference is absolute IoU, not relative.
   4. Class coverage, export validity and resource checks pass.
6. **Strict alternative.** The same rules, but no OEM class may lose any IoU. It protects every class but blocks an update whose regional gain costs a small loss elsewhere. The 2-point tolerance is a starting policy that development experiments may tighten.
7. **Final evaluation.** After the last update, evaluate the approved model once on the OEM final regions and D073-2022; final holdouts never drive tuning, replay selection or promotion.

Hypothetical examples (illustration, not measurements):

| Model | OEM mIoU | Regional mIoU | Largest OEM class loss | Selected policy | Strict alternative |
|---|---:|---:|---:|---|---|
| Approved model | 60.0% | 50.0% | — | — | — |
| Candidate A | 60.4% | 52.0% | 1.5 pp | Eligible | Fails |
| Candidate B | 60.4% | 52.0% | 0 pp | Eligible | Eligible |
| Candidate C | 60.1% | 51.0% | 2.0 pp | Eligible | Fails |
| Candidate D | 60.6% | 50.0% | 0 pp | Fails: no regional gain | Fails |

Passing a gate makes a candidate eligible for review, not active (Section 5.5).

## 5.5 Human in the loop

**Promotion** moves the MLflow registry alias `champion` to a new model version; the service always loads its model through that alias.

- **Drift and failure alerts** (Section 6.6): the operator checks the report and sample overlays, then fixes the cause, schedules a labelled batch or records that no action is needed.
- **Candidate review.** The operator receives the Section 5.4 report and up to five example overlays; only the operator promotes, by moving `champion` to the candidate. A blocked candidate stays a run artifact and never becomes the base of the next update.
- **Override.** The operator can block a candidate that passes every gate, for example when overlays show tiling seams, or roll back by moving `champion` to any earlier approved version.
- **Rollout.** Workers resolve `champion` at start-up, load that immutable version and record it on every job. After an alias change the operator triggers a rolling restart: old workers finish their jobs, new workers load the new version.
- **GIS edits** stay in the user's own maps (Section 6.5).

Lifecycle: training run → registered candidate → `champion` alias → monitoring reports → next candidate. Every approved version stays in the registry for audit and rollback.

## 6.1 High-level design

![System context: data, label and documentation sources on the left; the GIS user and the operator on the right](diagrams/context.svg)

*Figure 1. System context.*

![Seven-layer data flow with training and upload lanes, the version point, the quality gate, the manual Colab import, the registry alias and the retraining loop](diagrams/data-flow.svg)

*Figure 2. Data flow on the seven layers.*

![Deployment draft: local components with their managed AWS equivalents, the host-native LLM and Colab Pro](diagrams/deployment.svg)

*Figure 3. Deployment, first draft.*

## 6.2 Infra

| Component | Local (course) | Selected cloud | Managed equivalent | Reason for the cloud choice |
|---|---|---|---|---|
| Segmentation service: API, web UI, workers | FastAPI and worker containers in Minikube | ECS on EC2: core host plus burst group | EKS | EKS adds a $73/month control plane without more availability |
| GIS assistant | Container in Minikube | ECS on EC2, core host | EKS | Same host as the API |
| Object storage | pgsty/silo (MinIO-compatible) | Amazon S3 | Amazon S3 | Cheaper per GB than a disk, with managed durability |
| Data versioning | DVC with object-storage remote | DVC with S3 remote | S3 remote | Same tool in both places |
| PostgreSQL + pgvector | PostgreSQL 16 with pgvector | RDS for PostgreSQL db.t4g.small, Single-AZ, with pgvector | RDS for PostgreSQL; OpenSearch Serverless for vectors | Managed backups and patching for $23.60/month more than self-hosting |
| Airflow (orchestrator) | Airflow 3.3.1, LocalExecutor | Self-hosted on the core host | Amazon MWAA | A few scheduled DAGs do not justify $358/month |
| MLflow (tracking and registry) | MLflow 3.16.1 with authentication | Self-hosted on the core host | SageMaker AI serverless MLflow App | Keeps the course's pinned version and alias permissions |
| Monitoring | Prometheus, Grafana, Alertmanager, Evidently job | Same, self-hosted; CloudWatch alarms and SNS for host and health-check alerts | CloudWatch; SageMaker Model Monitor | Model Monitor is closed to new customers and tabular; a monitor on a failed host cannot report its own failure |
| LLM and embeddings | Host-native llama-server (Metal): Gemma 4 12B QAT Q4_0; Qwen3-Embedding-0.6B | Bedrock: Claude Sonnet 5.5; Titan Text Embeddings V2 | Amazon Bedrock | An always-on GPU costs $587.50/month before disks; the API costs $124.82 at the assumed load |
| Identity | Pre-provisioned per-user tokens with roles | Amazon Cognito | Amazon Cognito | A self-hosted identity server adds a database and patching |
| Minikube and container registry | Minikube with its registry | ECS on EC2; Amazon ECR | EKS; ECR | As above |
| Training resource | Colab Pro (owned); Mac for small runs | EC2 g6.xlarge on demand, 40 h budget | SageMaker Training | Pay only for training hours |
| Feature store | Not needed | Not needed | SageMaker Feature Store | No entity features to look up online; tensors come from the image with versioned preprocessing |

The segmentation service is ready only after loading the `champion` model and its preprocessing configuration, so a missing model fails the readiness probe; the assistant is ready only when its LLM endpoint and corpus index respond.

**Training exchange.** The operator starts each training run in Colab Pro, which cannot reach local MLflow.

Google Drive receives `model.pt`, `checkpoint.pt` (optimizer, scheduler, epoch and RNG state), `metrics.json` and `run.json` (commit, dataset digest, configuration, seed and weights SHA-256).

The operator downloads the folder. The import command verifies hashes, rebuilds the model on CPU from the recorded code and configuration, logs the run and registers a version in MLflow.

MLflow holds runs, versions, approvals and traces; W&B is only for live Colab curves (Section 7.1).

**LLM choices.** [Gemma 4 12B QAT Q4_0](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) runs through [llama.cpp](https://github.com/ggml-org/llama.cpp) with Metal on the Mac host, because Docker on this Mac has no GPU access.

Assumption: its 6.98 GB weights and context cache fit beside Minikube in 24 GiB; Lab 3 measures peak memory.

Cloud: [Claude Sonnet 5.5 on Bedrock](https://platform.claude.com/docs/en/models/overview). [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) needs separate integration and evaluation, without automatic failover.

Embeddings use [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) locally.

The cloud uses [Titan Text Embeddings V2](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html) if it passes the Ukrainian-to-English retrieval evaluation.

Changing the embedding model rebuilds the index under a new version.

**Cloud placement.** The always-on m6a.xlarge core host (4 vCPU, 16 GiB) runs the HTTPS proxy, both APIs, Airflow, MLflow, Prometheus, Grafana and one worker. A burst Auto Scaling group of 0–1 identical hosts adds up to three workers.

Hosts use a public subnet without a NAT gateway; S3 traffic uses a free gateway endpoint. Route 53 points to an Elastic IP that a replacement core host re-associates at boot, restoring its TLS certificate from a backup.

A retry gets a new attempt ID, preventing a worker with an expired lease from publishing over it.

## 6.3 Performance

**Batch versus online.** Each upload is an asynchronous online job: a nightly batch would make the GIS user wait a day, and a synchronous request would hold an HTTP connection for minutes. The API stores the job and returns its ID; workers claim jobs from a PostgreSQL table with `FOR UPDATE SKIP LOCKED`, so adding workers adds throughput.

| Item | Assumption and reason |
|---|---|
| Load | Section 2; 20% of a day's jobs arrive in the peak hour |
| Reference image | 4096×4096 RGB; 50 MB upload and 50 MB results on average |
| Service time | 60 s per reference image on one worker (decode, tiling, inference, stitching, export); the capacity input until measured |
| Worker | One CPU thread, 512×512 tiles, batch size 1, within the Section 4 ceilings |

**Worker count.** Peak arrivals are 1000 / 22 working days × 0.2 = 9.09 jobs per hour. At utilization 0.6, ceil(9.09 × 60 / (3600 × 0.6)) = 1 worker covers the mean load.

Bursts scale to four workers, targeting at most 2 queued jobs per worker with a 10-minute scale-in cooldown. The core services and one worker reserve 3.25 of 4 vCPU and 12.125 of 16 GiB; a burst host fits three workers.

The mean-load formula gives no p95; the load test does.

**Measurement method.** Limit a worker to 1 vCPU and 4 GiB. Time cold start, then 30 runs at 1024×1024 and 4096×4096 after 5 warm-ups, recording stage times and peak memory.

Replay twice the peak rate for an hour and record p95 and queue wait. Above 5 minutes, try ONNX Runtime or larger tiles, then more workers within the cost ceiling, before relaxing the target.

## 6.4 Security

- **Authentication.** Cloud users sign in with Cognito; the API checks the token's issuer, audience, signature and expiry. Locally, pre-provisioned per-user tokens map to the `gis_user` and `operator` roles.
- **Authorization.** A GIS user creates jobs and reads only their own jobs and results. Only the operator ingests batches, starts training and changes the registry: MLflow runs with authentication, only the operator credential moves `champion`, and workers have read-only access.
- **Secrets.** An ignored `.env` file locally; SSM Parameter Store SecureString with KMS in the cloud, read through per-task IAM roles. Secrets never enter Git, images or logs.
- **Network.** Only the HTTPS proxy is public; PostgreSQL, Airflow, MLflow and Grafana are private and reached through SSM.
- **Input checks.** Before decoding the whole image, the API enforces the size bounds (Section 4) and the 8-bit RGB rule (Section 5.3); it generates object keys itself and rejects archives.
- **Assistant.** User requests and retrieved documents are data, not instructions. Every tool call is validated in code and runs with the caller's permissions; no tool can promote a model or change infrastructure.

## 6.5 Data privacy

Uploads may show private property, people and vehicles, and a GeoTIFF reveals its location, so each upload is visible only to its owner and the operator.

- **Uploads and results** expire at `expires_at = accepted_at + 24 h`. Then access is denied, signed URLs never outlive `expires_at`, a queued job does not start, a running job is cancelled, and a late output is discarded without extending the expiry. Deletion is due at `expires_at` and monitored (Section 6.6); the temporary bucket has no object versioning, so no old copies remain.
- **Logs and metrics** are kept for 30 days with user and job IDs, sizes, timings and errors, but no image bytes, file names, coordinates or secrets.
- **Training data** comes only from the public datasets in Section 5.2 and is kept for the project's life with attribution. OEM labels default to CC BY-NC-SA 4.0 and FLAIR-HUB uses Etalab Open Licence 2.0; the project redistributes neither.
- **No user feedback** enters training in the first version: user images and QGIS corrections are never training data.

## 6.6 Monitoring and alarms

All alerts email the operator: Alertmanager for application rules, CloudWatch and SNS for rules that must work when the host is down. Each alert has an event key, so one incident sends one email.

Assumption: drift reports compare the last 7 days with frozen snapshots of per-job statistics.

Input statistics use the first 14 days of service; the operator replaces this reference only after accepting a reviewed shift as normal. Model-dependent class shares use the first 7 days after each `champion` activation.

With fewer than 50 images or an incomplete reference, the report says "insufficient data".

| Signal | Window and threshold | Reason | Action |
|---|---|---|---|
| Job failures | Rolling 1 h: ≥ 3 system failures, or > 1% of valid jobs per week | 1% is the Section 3 target; 3 in an hour indicates a fault, not chance | Operator reads job errors and worker logs |
| Latency | Rolling 15 min: completion p95 > 5 min, or the oldest queued job waits > 10 min while 4 workers run | The p95 target; a long queue at full scale means the ceiling is too low | Operator checks worker health and limits |
| Service health | The external HTTPS check fails 3 one-minute probes in a row, or a worker cannot load `champion` | Host or model loss stops all jobs | Operator replaces the host or rolls back the alias |
| Training batch gate | Every run: any invalid file (format, image–mask grid mismatch, unknown class ID), or no new checksum | Catches bad and repeated batches; the watermark does not move | Run fails; operator fixes or replaces the batch |
| Input drift | Daily: Population Stability Index (PSI) > 0.25 on per-image channel means or image size | Assumption: 0.25 is the conventional large-shift level, checked against the PSI between the reference's two 7-day halves | Operator reviews sample overlays and may schedule a labelled batch |
| Predicted class shares | Daily: any class share of valid pixels moves by > 10 percentage points | The model can change behaviour while inputs look stable | As for input drift |
| Expiry cleanup | Hourly: any upload or result older than `expires_at` + 1 h | The 24-hour privacy guarantee | Operator runs the cleanup and checks the job |

## 6.7 Cost

Prices are AWS us-east-1 On-Demand USD rates read on 2026-10-23, for a 730-hour month, before tax and operator time. Sources: [EC2](https://aws.amazon.com/ec2/pricing/on-demand/), [RDS](https://aws.amazon.com/rds/postgresql/pricing/), [S3 and internet transfer](https://aws.amazon.com/s3/pricing/), [VPC IPv4](https://aws.amazon.com/vpc/pricing/), [ECR](https://aws.amazon.com/ecr/pricing/), [Route 53](https://aws.amazon.com/route53/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [SNS](https://aws.amazon.com/sns/pricing/), [SES](https://aws.amazon.com/ses/pricing/), [Cognito](https://aws.amazon.com/cognito/pricing/), [KMS](https://aws.amazon.com/kms/pricing/), [Bedrock](https://aws.amazon.com/bedrock/pricing/).

**Workload assumptions** (load from Section 2):

- Each image keeps 0.1 GB (upload and results) for one day of thirty: ceil(1000 × 0.1 GB × 1/30) = 4 GB on average. With 100 GB of persistent data (archives, extracted copies, tiles, checkpoints, reports) S3 holds 104 GB.
- 60 GB internet output (50 GB results, 10 GB API traffic); 10,000 S3 PUT and 100,000 GET requests.
- An assistant task makes five sequential model calls (inspect, segment, validate, export, explain) over a growing conversation: 32,000 input and 4,000 output tokens. With 20% for retries and evaluation, a month uses 38.4 M input and 4.8 M output tokens, plus 1.1 M Titan embedding tokens.
- A training month adds budgets, not measured times, of 20 burst CPU-host hours and 40 g6.xlarge GPU hours.

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

Unused recurring free allowances cover $12.52: the first 100 GB of internet output, the CloudWatch volumes above, Cognito MAU, the health check, KMS requests and SNS emails.

| Scenario | Steady | Steady with allowances | Training month | Training month with allowances |
|---|---:|---:|---:|---:|
| 1000 images and tasks | $301.75 | **$289.23** | $338.25 | **$325.73** |
| 2200 images and tasks | $460.29 | $444.17 | $496.79 | $480.67 |

The 2200 case uses 108 GB storage, 22,000 PUT and 220,000 GET requests, 120 GB internet output, 11 GB each of ingested and stored logs, and $274.58 of LLM calls. All other quantities stay fixed.

LLM calls are 41% of the steady month, so agent token use is the assumption most likely to make this estimate wrong.

[Saved AWS Pricing Calculator estimate](https://calculator.aws/#/estimate?id=5149b216245db885ab6f9aa1f752302f6d636b13), verified on 2026-10-25: $299.48 for the base group and $36.17 for training, or $335.65 together per month.

The [verification log](verification.md) reconciles differences in domain charges, allowances, log storage and training disk/IPv4 accounting with the listed-rate totals above.

## 6.8 Integration points

No public publisher promises us freshness or availability, so we pin each source's revision and checksums and set our own acceptance rules.

| Boundary | Payload and format | Timing | Responsibility and failure behaviour |
|---|---|---|---|
| OEM authors → ingestion | Zenodo release: images, masks, metadata; xBD images from xview2.org | Once, for the initial batch | We record release ID and checksums, remap labels, and reject a whole batch with mismatched grids or unknown IDs |
| IGN (FLAIR-HUB) → ingestion | Per batch, one domain's `AERIAL_RGBI` and `AERIAL_LABEL-COSIA` ZIPs at a pinned Hugging Face revision | When the operator starts an update | The same checks and the freshness rule (Section 5.2); a missing archive fails the run and the watermark stays |
| USGS / UGRC (NAIP) → monitoring | 4-band GeoTIFF tiles; the adapter keeps RGB | Optional, per vintage (Section 5.2) | We record tile IDs and checksums; tiles feed drift reports only |
| Documentation publishers → corpus | Pages and PDFs listed in Section 5.2 | Snapshotted when the corpus is built | Snapshots carry SHA-256; a changed page becomes a new `doc_version`, never an in-place edit |
| GIS user → API | One image per request, in the Section 4 formats and bounds | Any time | We return a job ID, or a validation error naming the problem |
| API → GIS user | Job status and the result package (Section 4) | Completion p95 as in Section 3; available until `accepted_at` + 24 h, including queue and processing time | A failed job returns its reason and no partial package |
| Service ↔ operator | Alerts and candidate reports (Section 6.6); batch, approval and rollback commands | Alerts as they fire; reviews per candidate | Each alert names the batch, run or model and the rule that fired |

Example: a GIS user uploads a 4096×4096 georeferenced GeoTIFF and gets a job ID. The successful job's mask GeoTIFF has the same width, height, CRS and affine transform.

Its metadata names taxonomy v1 and model version 4; the legend maps IDs to class names in QGIS. A 16-bit image is rejected with "unsupported bit depth: 16; convert to 8-bit RGB" until the conversion adapter exists.

## 6.9 Risks and uncertainties

| Risk | Mitigation |
|---|---|
| FLAIR scores mix year and region shift and cover 6 of 8 classes | Separate OEM-8 and regional scores; road and developed space judged on OEM (Section 5.4) |
| The crosswalk misreads a class, e.g. herbaceous versus grazed agriculture | Inspect image–mask pairs, class histograms and sample masks in the first data pilot before freezing crosswalk v1; ambiguous classes stay 255 |
| Evaluation leakage through neighbouring tiles or reused pretraining images | The region split (Section 5.4); the official OEM lightweight weights, trained on train and validation data, are never used |
| An update forgets road or developed space | OEM replay (Section 5.3) and the 2-point per-class gate (Section 5.4) |
| CPU inference is slower than the 60 s assumption | Measure first, then the fallbacks in Section 6.3 |
| A large or malformed raster exhausts worker memory | Bounds checked before decoding (Section 6.4) and tile-by-tile processing; the job fails with a reason |
| The export lands in the wrong place | Georeferencing only from a valid input (Section 4), checked by the QGIS test set (Section 3) |
| The core host or the RDS zone fails | Durable job state and leases (Section 4) and the external health check (Section 6.6) |
| Agent tokens exceed the estimate | Cap turns and context per task and record tokens per run in Lab 3; Claude Haiku 5.5 is the cheaper candidate if it passes the evaluation |
| The assistant follows instructions embedded in a document | Code validates every tool argument (Section 6.4) |
| A Colab session ends mid-training | `checkpoint.pt` is written to Drive every epoch and the run resumes from it |

## 7.1 Alternatives

| Alternative | Pros | Cons | Decision |
|---|---|---|---|
| Building-only segmentation | Simpler labels and model | Misses most GIS classes | Rejected framing (Section 5.1) |
| Synchronous HTTP inference | No job table or queue | Minutes-long requests time out | Rejected; asynchronous jobs (Section 6.3) |
| Teacher pseudo-labels on unlabelled NAIP | Same-place image history | Agreement with a teacher does not measure accuracy; the official OEM weights saw our controls | Rejected: every training batch has expert masks, so no teacher is needed |
| Chesapeake LULC with NAIP as the update source | Same places in three periods | Semi-automated labels revised in later editions; scripted access to the 2024 edition unverified | Alternative if same-place history matters more ([USGS](https://www.usgs.gov/data/chesapeake-bay-land-useland-cover-lulc-database-2024-edition)) |
| FT-UNetFormer or Satlas as the first candidate | Higher published score; aerial pretraining | Section 5.3 | Revisit after the first implementation |
| Richer taxonomy (e.g. FLAIR's coniferous and deciduous) or open-vocabulary segmentation | More classes; new concepts without a new head | A new taxonomy changes the head, legend, crosswalk and controls; a text prompt is not a validated class | Keep OEM-8; add classes when a concrete GIS need appears |
| W&B instead of MLflow | Hosted live dashboards | An account and a [5 GB free storage limit](https://coreweave.com/forge-pricing); Lab 2 names MLflow | Optional live curves only |
| MWAA and a legacy managed MLflow server | No Airflow or MLflow operations | About $797/month together | Self-hosted (Section 6.2) |
| High availability: second host, RDS Multi-AZ, load balancer | Survives one host or zone failure | About +$190/month and failover tests | Not selected; continuous single-host service |
| Learning from GIS users' corrections | Real labels for new regions | Needs consent and image licences; an "OK" click confirms the model's own errors; needs a review interface | Not in the first version (Section 6.5) |

## 7.2 Placeholder

Lab 2 fills this section with the baseline and update-candidate experiment results.

## 7.3 Placeholder

Lab 4 fills this section with deployed throughput, p50 and p95 latency and resource measurements.

## 7.4 Milestones

- **Lab 2** adds versioned data pulls, idempotent batch ingestion with a failing bad-batch gate, the random-forest baseline and U-Net candidate, and MLflow runs and models with data version and commit.
- **Lab 3** adds the versioned retrieval corpus and prompts, and evaluates the assistant with and without retrieval, logging tokens, cost and p50/p95.
- **Lab 4** deploys the segmentation service and assistant on Minikube with health probes, scheduled drift reports and an injected shift whose alert reaches the operator.
- **Lab 5** gives the assistant inspect, segment, validate and export tools, with persisted traces and ten tasks evaluated twice.

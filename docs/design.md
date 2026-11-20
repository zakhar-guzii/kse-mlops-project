# Land-cover segmentation system design

This design follows the KSE MLOps Lab 1 assignment.

## 1 Overview

GIS specialists need a first land-cover layer for new aerial imagery, which they then check and edit in QGIS. The service turns an 8-bit RGB aerial image into an eight-class OpenEarthMap (OEM) mask and returns a colour overlay and legend; for a georeferenced GeoTIFF, it also creates a GeoTIFF mask on the same pixel grid as the input image. Authenticated users submit images of different sizes, within fixed upload limits, as asynchronous jobs, and CPU workers scale with the queue. The model is trained on OEM and fine-tuned on expert-labelled batches in acquisition-year order; an operator approves each new version before it serves. The desired outcome is GIS exports that open without manual repair, and model updates that are reproducible, monitored and reversible.
## 2 Motivation

A GIS specialist needs a land-cover layer when preparing a map from new aerial imagery. Creating this layer by hand means marking areas and assigning classes such as roads, buildings, water and vegetation. The project provides a starting layer: the user uploads an image, receives a segmentation mask and supporting files, then checks and edits the layer in QGIS. The aim is to make these results usable in the specialist's mapping workflow.

The system has two roles:

- **GIS user** (consumer): a cartographer or GIS specialist who uploads new imagery of a project area, waits for the result, imports the package into QGIS and edits the layer there.
- **Operator**: the ML engineer responsible for the system. They add training batches, review alerts and candidate models, approve or block model versions, and roll back to an earlier approved version when needed. In the course, the project author is the operator. Operator and GIS-user permissions remain separate.

A GIS user asks, “Make a QGIS mask from my GeoTIFF and explain what 255 means.” The assistant calls `predict` with the user's authorized upload and reports the queued job ID. While a worker makes the map, `retrieve` finds the taxonomy in the project documentation. On success the assistant returns the caller's package, the model version recorded by the worker and a cited explanation. A value of 255 marks an invalid input pixel. A value of 0 means valid bareland (`export-contract`, §5.1). In QGIS the user displays 255 as NoData and keeps bareland visible.

If the user asks only “What does 0 mean in the legend?”, the assistant calls the Lab 3 retriever once and cites the same taxonomy entry. A legend question needs no upload or job.

Assumption: 20 active GIS users together submit 1000 images and run 1000 assistant tasks a month. The product scenario assumes that the service runs in AWS. For the course, the same components run locally under the constraints in Sections 4 and 6.2. A shared service gives users a common way to submit work and receive results, while the operator can track jobs and manage model updates.

Errors affect the usefulness of the map. A wrong class takes time to correct in QGIS. A wrong grid or invented georeferencing makes the export unusable. If a new model stops recognising a class, such as roads, the error can appear in every later map created with that model.

The service therefore records the model version in each result's metadata, so the operator can identify which model produced the mask. Before an update, the operator compares the candidate with the approved model on the same labelled control data and reviews the results before approving it. This comparison can be repeated using the recorded data and training settings. User uploads have no reference masks, so the service monitors failures, processing time, input statistics and predicted class shares. These signals help the operator notice changes that need investigation; model accuracy is measured separately on labelled data.

## 3 Success metrics

We check success at three levels: the GIS user's workflow, model quality and system operation.

IoU measures overlap between the predicted and reference areas of one class. It divides the shared pixel count by the number of pixels in either area, counting each pixel once. mIoU is the mean IoU across the classes being evaluated. Higher values mean better overlap.

| Level | Metric and target | How it is checked |
|---|---|---|
| Decision / workflow | At least 9 of 10 predefined valid test images produce a complete package. The package opens in QGIS on the correct grid without manual format or georeferencing repair | A fixed test set includes PNG, JPEG, georeferenced GeoTIFF and three image sizes. This checks whether the export is usable; it does not measure cartographic accuracy |
| Model | The first neural model exceeds the random-forest baseline in OEM-8 mIoU. Each later update must meet the promotion rule (Section 5.4) | Control sets for development; final holdouts are evaluated once |
| System | Job acknowledgement p95 ≤ 1 s after upload; completion p95 ≤ 5 min for a 4096×4096 image at the assumed load. At most 1% of valid jobs fail for system reasons per week | Load test (Section 6.3) and monitoring (Section 6.6) |

Here, p95 is a time limit met by at least 95% of the relevant measurements. Acknowledgement means that the service returns a job ID after upload. Completion means that the result is ready.

mIoU is the **optimization** metric: the score we try to improve. Export validity, p95 latency and resource limits are **satisficing** metrics: each has a required limit that the system must meet. A higher mIoU does not replace meeting these limits.
## 4 Requirements and constraints

**Functional requirements:**

- An authenticated GIS user uploads one 8-bit RGB PNG, JPEG or GeoTIFF and immediately receives a job ID; uploading an image again creates a new job.
- The GIS user reads the status of their own jobs (`queued`, `running`, `succeeded`, `failed`, `expired`) and downloads their own results: a uint8 class mask (0–7, 255 for invalid input pixels), a colour overlay, a legend and JSON metadata with model and taxonomy versions.
- A GeoTIFF with a valid CRS and affine transform also yields a GeoTIFF mask on the same grid; otherwise the mask uses the pixel grid. Coordinates are never invented.
- Images of different sizes and aspect ratios, within the ceilings below, are processed in overlapping tiles and stitched back to the source pixel grid.
- The operator ingests a labelled batch, trains a candidate from the approved model, compares them, approves or blocks the candidate, and rolls back to an earlier approved version.
- The GIS assistant answers questions about the export from the project documentation with cited sources, through the Lab 3 retriever and submits authorized images to the Lab 4 prediction service. Only these two tools are allowed, with four attempts per task across retries and resumes. Workers decode, segment, check the grid and export the package.

**Non-functional requirements:**

| Category | Requirement |
|---|---|
| Freshness | Reprocessing an accepted logical interval succeeds with the same dataset version and feature rows. A discovery scan that expects new checksums and finds none reports stale input. Assume at most one new labelled batch per month for operator review |
| Latency and throughput | This requirement concerns the speed of processing user uploads. The API returns a job ID with p95 ≤ 1 s after upload. For a 4096×4096 image, the result is ready with p95 ≤ 5 min at the assumed load (Section 6.3). Jobs run on 1–4 workers; queue wait is also measured separately |
| Availability and fallback | The cloud service runs continuously. Job state is stored in PostgreSQL and files in object storage, so this data survives a host failure. A lease is the period during which a worker has the right to run a job. Once it expires, an interrupted job is retried, with up to 3 attempts in total. If the approved model cannot be loaded, jobs remain in the queue and the service does not produce a mask without a model. During an LLM outage, chat reports unavailability and preserves the pending job ID and attempt count until expiry. Direct upload, status and download continue through the ML API |
| Reproducibility | This covers two requirements: repeating training and ingesting a batch again without duplicate data. Every training run records data version, code commit, configuration, preprocessing, taxonomy version, parent model and seeds. The target is to repeat the build of any registered model version with one command from a clean clone, using those data and settings. Ingesting the same batch again does not create duplicate dataset records. Bit-identical GPU weights are not required. For user images, uploading again creates a new job; files are deleted after 24 hours. This requirement does not promise to return a saved mask |
| Adaptability | This requirement concerns how model updates are tested. For a new batch, the operator trains a candidate model from the approved model (Section 5.3). A new architecture is also tested as a candidate first. Assumption: old OEM training tiles make up 50% of the training mix in the first experiments. This keeps either source from dominating. The operator chooses the final share based on results on the development controls |
| Observability without ground truth | Count invalid uploads separately. A valid dark image receives a warning with its package and still contributes to the input window. Compare per-image brightness, RGB means and predicted class fractions with matching training references (§6.6). Measure IoU only against independent reference masks |
| Cost and resource ceilings | The hypothetical cloud estimate at the dated rates is about $302/month, or $338 in a training month (Section 6.7). For one job, the uploaded file is limited to 128 MiB and the decoded image to 64 megapixels. One worker with 1 vCPU and 4 GiB RAM runs the job. The job has a 15-minute deadline, which must not run past the upload's expiry. These limits bound disk space, decoding memory and work time |

**Course constraint.** The reviewer path uses a local CPU for training and prediction, Minikube for the services and a configurable host-native text model. On the course Mac (M4 Pro, 24 GiB), the cluster and model share that memory budget. All graded demonstrations must run with zero additional paid spend. Existing Colab access is optional for larger neural experiments.

**In scope:** eight-class land-cover rasters, the GIS package, supervised model updates with operator approval, monitoring and the GIS assistant. **Out of scope:** object detection and building counting, guaranteed accuracy in other geographies, area statistics in square metres, simulator terrain, high availability or an uptime percentage, and training on user uploads.

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

Examples of `developed space` are sidewalks and parking lots. OEM labels the lanes between parking lots as `road` ([class definitions](https://openaccess.thecvf.com/content/WACV2023/supplemental/Xia_OpenEarthMap_A_Benchmark_WACV_2023_supplemental.pdf)).

**Rejected framing:** building-only (binary) segmentation. It is simpler and well studied, but the GIS layer must also separate roads, vegetation, water and agricultural land.

## 5.2 Data

**Image resolution.** Ground sampling distance (GSD) is the size of the ground area represented by one image pixel. A GSD of 0.25–0.5 m means that one pixel covers roughly 25–50 cm on each side; it does not describe height.

| Source | Content | Role |
|---|---|---|
| [OpenEarthMap](https://arxiv.org/html/2210.10732) ([release](https://zenodo.org/records/7223446)) | RGB aerial images with GSD 0.25–0.5 m and masks for the eight classes, annotated by people; 9.1 GB, plus separately downloaded xBD images | Initial training; development and final controls |
| [FLAIR-HUB](https://huggingface.co/datasets/IGNF/FLAIR-HUB) ([paper](https://arxiv.org/html/2506.07080v1)), IGN France | Aerial RGB and NIR images with GSD 0.2 m and CoSIA masks drawn by expert photo-interpreters; one archive per département and year | Supervised update batches; regional controls |
| [Utah NAIP](https://gis.utah.gov/products/sgid/aerial-photography/naip/) 2018, 2021, 2024 | Public-domain images with GSD 0.6 m, without masks | Optional drift-monitoring stream |
| GIS user uploads | RGB images without masks | Serving only |

We also considered NAIP images for Utah back to 2003 (with coarser resolution before 2018) and the Chesapeake states for 2010–2023 ([Planetary Computer](https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip)). None of these datasets has OEM-8 masks annotated by people, so NAIP supplies no training update batches. We keep only the Utah images with GSD 0.6 m for optional drift monitoring, because their resolution is closest to OEM's.

**Update timeline.** We use six FLAIR-HUB datasets, each for a different département (an administrative region of France) and acquisition year. FLAIR-HUB calls such a dataset a domain. We download only the RGB images and CoSIA masks: 4.88 GB of compressed archives in total. Each whole domain has one role: model updates, development checks or final evaluation. This prevents the same region from being used for both training updates and controls.

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

1. **Time axis.** The operator downloads one FLAIR-HUB domain per batch into the training pipeline, in order of the actual acquisition years. OEM is used for initial training and has no usable time axis.
2. **History and holdout.** The 2017–2020 batches provide four successive updates; the 2021 dataset is used only to choose settings and check candidates. The 2022 dataset is reserved for a single final evaluation (table above).
3. **Labels and delay.** When the operator downloads a FLAIR-HUB batch into the pipeline, its reference masks are already available with the images, so there is no wait between image availability and mask availability for that run. This zero delay does not apply to user uploads, which have no reference masks.
4. **Corpus.** The GIS assistant uses a retrieval corpus of saved copies of the OEM and FLAIR-HUB papers, the NAIP dictionary, QGIS documentation and sections of this design. The exact sources are listed below.

The FLAIR sequence changes both year and region, so its scores measure transfer to later images of other places. They do not measure change at one place or what a model available in 2017 could have achieved: OEM and the ImageNet encoder were published later. The zero label delay above describes access to an existing image-and-mask pair, not the time from image acquisition or the time needed to create a mask. A Lab 4 exercise may withhold one batch's labels as a declared simulation.

**Label mapping.** Before training, we replace the numeric IDs of pixels in each original OEM mask with the service's internal IDs: 1–8 → 0–7 and 0 → 255 ([OEM class codes](https://raw.githubusercontent.com/bao18/open_earth_map/main/open_earth_map/utils.py)). For example, OEM ID `1` (bareland) becomes internal ID `0`; the class itself stays the same. The code `255` means `ignore`: these pixels are excluded from training and evaluation. In service outputs, `255` also marks invalid input pixels (Section 5.1).

FLAIR-HUB uses its own IDs 0–18, which differ from FLAIR-1/2 ([label configuration](https://github.com/IGNF/FLAIR-HUB/blob/main/configs/train/config_supervision.yaml)). Crosswalk version 1 replaces these with the corresponding internal OEM-8 IDs only for unambiguous classes:

| FLAIR-HUB class (ID) | Internal OEM-8 ID |
|---|---:|
| building (0) | 7 |
| bare soil (5) | 0 |
| water (6), swimming pool (2) | 5 |
| coniferous (13), deciduous (12) | 4 |
| herbaceous vegetation (8) | 1 |
| agricultural land (9), vineyard (11) | 6 |
| all other IDs, including pervious and impervious surfaces, brushwood and plowed land | 255 |

FLAIR masks therefore provide training labels for six classes: 0, 1, 4, 5, 6 and 7. The FLAIR impervious class combines roads, parking and construction, so road (3) and developed space (2) are learned and checked only on OEM. The model always keeps eight outputs.

**Dates.** The fields `acquisition_start`, `acquisition_end`, `date_precision`, `label_reference_period`, `source_published_at` and `ingested_at` may be null. A missing date stays null and processing continues. If only a year is known, we do not use 1 January in place of the unknown exact date. Inference needs no date.

**Sample retrieval.** For sources over 200 MB, Lab 2 will freeze a reviewer sample before tiling. Within the assigned regions, sort paired scene IDs, select the first configured number per region and record the limit, IDs, archive members, release or revision, source URLs, sizes and SHA-256 digests in the JSON manifest alongside known acquisition dates. Sample only pairs accessible to a reviewer from the original publisher. Download each pinned archive with `curl -fL "$source_url" -o "$archive"` using the manifest values. Run `shasum -a 256 -c archives.sha256`, extract the listed members, then run `shasum -a 256 -c pairs.sha256` before ingestion. The manifest and checksum lists travel with the Git revision. Raw rasters stay in object storage.

**One interval, four outcomes.** An Airflow logical batch ID binds a domain and interval to a frozen manifest digest. The watermark records the last accepted batch and DVC dataset version. The feature table in PostgreSQL stores one row per tile and feature version: the tile key consists of the source raster checksum and tile window (pixel offset and dimensions). Each row stores the raster object reference, per-channel means on valid pixels and `feature_version` identifying the extraction and tiling configuration. A unique constraint on tile key and feature version makes retries safe.

| Run | Gate and outcome | Watermark and feature rows |
|---|---|---|
| Ingest D065-2019 for the first time | Verify file hashes, formats, image/mask grids and class IDs. Stage the DVC snapshot and tile features | After storage succeeds, commit the accepted batch, feature rows and watermark together. Suppose the version is 3 and the table has N rows |
| Rerun the same D065-2019 interval | Resolve the same manifest and reuse version 3. A changed digest under the same ID is a conflict | Success, watermark 3 and N rows again |
| Discover expected new files | Every checksum is already in the accepted dataset. Report stale input and stop before training | Watermark 3, N rows |
| Ingest a new interval with a deliberately mismatched mask grid | Fail the quality gate with the offending pair. Publish no dataset or features | Watermark 3, N rows. A corrected batch can be submitted |

**Storage and versioning:**

| Artifact | Format | Local | Cloud | Versioned by |
|---|---|---|---|---|
| Raw archives, images and masks | Original ZIP, TIFF, PNG | Floci (S3 API) | Amazon S3 | DVC content hashes |
| Clean tiles and remapped masks | GeoTIFF or PNG; uint8 masks | Object storage | S3 | DVC; one `.dvc` pointer per dataset version |
| Manifests, splits, taxonomy, crosswalk | JSON | Git | Git | Git commit |
| Jobs, users, batches, watermark, tile features, monitoring statistics | PostgreSQL tables | PostgreSQL 16 | RDS | Migrations in Git |
| Runs, metrics, model versions, alias | MLflow: metadata in PostgreSQL, files in object storage | MLflow | MLflow on EC2 with RDS and S3 | MLflow model versions |
| Uploads and results | Original file; GeoTIFF, PNG, JSON | Temporary bucket | Temporary S3 bucket, no versioning | Not versioned; expire after 24 h (Section 6.5) |
| Retrieval corpus | Saved document copies; chunks with pgvector embeddings | Object storage, PostgreSQL | S3, RDS | Copy SHA-256, `doc_version`, index version |

Images and masks stay in raster formats. Converting them to CSV or Parquet would add an unnecessary step.

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

For each saved copy of a document, we record its source URL, access date, SHA-256 and `doc_version`. For each chunk, we record `doc_id`, `doc_version` and a locator for the source section.

In Lab 3, one versioned retrieval configuration will select the corpus revision, chunking, embedding model and top-k for evaluation and serving. A planned `make retrieval-index` command will rebuild the index and print its document count. Version both the plain and retrieval-augmented prompts and log their hashes with the index and configuration in MLflow. Compare answers on at least 30 paraphrased questions with reference answers and expected source sections. At three or more top-k settings, report retrieval hit@k and mean reciprocal rank (MRR) and compare answer correctness against the plain-prompt baseline. Record resources or cost and p50/p95 latency over at least ten calls per configuration. Lab 4 will deploy the selected configuration unchanged.

## 5.3 Techniques

**Majority-class rule.** Count all valid pixels once on the OEM training source grids before tiling or class-balanced sampling. Predict the most frequent internal class at every valid pixel (lowest ID breaks a tie) and preserve 255 at invalid pixels. This gives the first comparator for the learned CPU baseline.

**Baseline: random forest on RGB texture features.** Each pixel is classified from intensity, edge and texture features, producing an eight-class mask on CPU without pretrained weights.

- [`multiscale_basic_features`](https://scikit-image.org/docs/stable/api/skimage.feature.html#skimage.feature.multiscale_basic_features) at scales 1, 2, 4 and 8 px.
- scikit-learn [`RandomForestClassifier`](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html): 100 trees, depth 12, fixed seed.
- At most 10,000 valid pixels per class from OEM training regions; remove ID 255.

Fit directly, without [`fit_segmenter`](https://scikit-image.org/docs/stable/api/skimage.future.html#skimage.future.fit_segmenter): label 0 (bareland) is a valid class.

Lab 2 will register the reproducible `oem8-rf` run as a version of the shared `land-cover` model in MLflow. The same registry entry can hold a later approved B4 version. Tag each MLflow run and registered version with the DVC data hash and Git SHA, and save the split, seed, pixel sampling, feature settings and locked dependencies. The planned clean-clone command is `make reproduce-rf GIT_SHA=<recorded-commit> DATA_VERSION=<recorded-dvc-hash>`. It will use that revision and dataset, refit the RF and rescore the same development manifest. Accept an absolute OEM-8 mIoU difference of at most 0.001 on the 0–1 scale. Lab 2 will supply the command and record both scores.

The baseline could remain in production if its per-class IoU and users' correction effort were acceptable. It will likely confuse context-dependent classes: road and developed space, or agriculture and rangeland.

**Candidate: U-Net with an EfficientNet-B4 encoder** ([segmentation_models_pytorch](https://github.com/qubvel-org/segmentation_models.pytorch) 0.5.0):

```python
smp.Unet(encoder_name="tu-tf_efficientnet_b4.in1k", encoder_weights="imagenet",
         in_channels=3, classes=8, activation=None)
```

For the first training run, we load the encoder weights from the [timm ImageNet checkpoint](https://huggingface.co/timm/tf_efficientnet_b4.in1k) (Apache-2.0).

Preprocessing divides the pixel values in each RGB channel by 255. It then normalizes each channel using mean (0.485, 0.456, 0.406) and standard deviation (0.229, 0.224, 0.225), in red, green and blue order. Training and serving use 512×512 tiles with the same overlap and padding.

On the [OEM benchmark, Tables 3 and 5](https://arxiv.org/html/2210.10732), this architecture reached 68.20 mIoU with 20.3 M parameters. It also led the comparison that used 10% of labels. These published results support the architecture choice. We still need to measure our model's accuracy and CPU speed.

ImageNet weights initialize only the first OEM training run. For each update, we resume training from the full approved checkpoint, including the decoder and head. **OEM replay** means mixing old OEM training tiles with the new batch. This helps retain the learned classes. Ingestion replay in §5.2 reuses one accepted data snapshot. OEM training replay changes the examples used to fit the next neural candidate.

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

A random split could place neighbouring tiles from the same scene in both training and evaluation. This would overstate accuracy. We therefore split data by region and, for FLAIR, by acquisition year.

1. **Split.** Before cropping images into tiles, assign whole OEM regions to training, development and final evaluation. Assumption: 70/15/15% of regions, stratified so that every class appears in each role. Assign FLAIR domains the roles listed in Section 5.2. Version the scene assignments with the sampled manifest. Freeze the final holdout lists for OEM and D073-2022 before scoring any model.
2. **Train.** Fit the majority rule and CPU random forest on the same OEM training regions, then score both on the same development scenes. The first neural candidate uses those same splits. For updates, follow Section 5.3. The operator chooses the replay share and learning rate using results on development controls only.
3. **Compute the metric.** For each control, accumulate one 8×8 confusion matrix. Stitch predictions onto each source grid before counting. A bareland reference (OEM 1 → internal 0) predicted as 0 adds one to cell [0,0], even where two tiles cover it. A reference of 255 or a padded or invalid pixel contributes nothing. Count every other eligible source pixel exactly once.

   Class IoU = TP / (TP + FP + FN). TP (true positives) counts correctly predicted pixels of the class. FP (false positives) counts pixels wrongly assigned to the class. FN (false negatives) counts reference pixels of the class that the model missed.

   A road prediction on a FLAIR tree pixel is a false negative for tree and a false positive for road. Each report lists the scored class IDs, the support (reference pixels per class), the ignored fraction and the number of classes in the mean. If a required class has no reference pixels, the evaluation is incomplete. Do not take a decision from an incomplete evaluation. Report OEM-8 mIoU and six-class regional mIoU separately. Never average them together.
4. **First neural approval.** Evaluate the U-Net and random forest on the same OEM development control. The U-Net is eligible for approval when its OEM-8 mIoU exceeds the random forest's and it passes the export and resource checks. Include its regional score in the report; that score is not an approval condition.
5. **Update approval.** Compare each candidate with the approved model, not the baseline. Use the same frozen development manifests for both models. Under the **selected policy** it is eligible when:
   1. OEM-8 mIoU is at least the approved model's.
   2. Regional mIoU is higher than the approved model's.
   3. No OEM class loses more than **2 percentage points** of IoU; exactly 2 is allowed, and the difference is absolute IoU, not relative.
   4. Class coverage, export validity and resource checks pass.
6. **Final evaluation.** After the last update, evaluate the approved model once on the OEM final regions and D073-2022. Never use final holdouts for tuning, replay selection or promotion.

## 5.5 Human in the loop

In the MLflow registry, the alias `champion` is a name that points to an approved model version. The service uses this name to find the model to load. **Promotion** means changing `champion` to point to a newly approved version. Only the operator can approve this change.

- **Drift and failure alerts.** A single dark image gets a user-facing QA warning. A population threshold crossing emails the operator, who reviews the affected feature or class, source mix and permitted sample overlays. The current model continues serving. The operator may record no action, investigate a fault or request a labelled batch through ingestion. Evidence from labelled controls informs a decision to block promotion or roll back.
- **Candidate review.** The operator receives the Section 5.4 report and up to five example overlays. If the operator approves the candidate, they change `champion` to point to it. A blocked candidate stays a run artifact and never becomes the base of the next update.
- **Override.** The operator can block a candidate even if it passes every gate, for example when overlays show tiling seams. The operator can also roll back by changing `champion` to point to any earlier approved version.
- **Rollout.** At start-up, each worker reads which model version `champion` points to and loads that immutable version. The worker records the version ID in every job's metadata. After changing the alias, the operator starts a rolling restart. Old workers finish their current jobs; new workers load the new version.
- **Assistant decisions.** A request to promote a model is refused before any tool runs. Only the operator can change the alias. For a queued or running prediction, the controller checks status on the accepted job ID without another LLM call or submission. On failure it reports the reason without a package. On expiry it reports `expired` and denies access to previous result references.
- **GIS edits** stay in the user's own maps (Section 6.5).

Lifecycle: training run → registered candidate → `champion` alias → monitoring reports → next candidate. Every approved version stays in the registry for audit and rollback.
## 6.1 High-level design

![System context: data, label and documentation sources on the left; the GIS user and the operator on the right](diagrams/context.svg)

*Figure 1. System context.*

![Seven-layer data flow with training and upload lanes, the version point, the quality gate, the CPU training path, the registry alias and the retraining loop](diagrams/data-flow.svg)

*Figure 2. The assistant retrieves citations from the Lab 3 corpus and submits predictions to the same ML API as a direct upload. Acceptance queues the job before a worker decodes, tiles, predicts and exports. A drift email can prompt the operator to send a new labelled batch through ingestion and the quality gate before training.*

![Deployment draft: local components with their managed AWS equivalents, local CPU training, the host-native LLM and optional Colab](diagrams/deployment.svg)

*Figure 3. Local deployment, first draft. AWS names show managed equivalents for reference. Section 6.2 describes the hypothetical cloud deployment.*

## 6.2 Infra

The local column is the course deployment. The cloud columns describe the hypothetical AWS workload costed in §6.7.

| Component | Local (course) | Selected cloud | Managed equivalent | Reason for the cloud choice |
|---|---|---|---|---|
| Segmentation service: API, web UI, workers | FastAPI and worker containers in Minikube | ECS on EC2: core host plus burst group | EKS | EKS adds a $73/month control plane without more availability |
| GIS assistant | Thin text service and project retriever in Minikube | ECS on EC2, core host | EKS | Same host as the API |
| Object storage | Floci (S3 API) | Amazon S3 | Amazon S3 | Cheaper per GB than a disk, with managed durability |
| Data versioning | DVC with S3 remote | DVC with S3 remote | S3 remote | Same tool in both places |
| PostgreSQL + pgvector | PostgreSQL 16 with pgvector | RDS for PostgreSQL db.t4g.small, Single-AZ, with pgvector | RDS for PostgreSQL; OpenSearch Serverless for vectors | Managed backups and patching for $23.60/month more than self-hosting |
| Airflow (orchestrator) | Airflow 3.3.1, LocalExecutor | Self-hosted on the core host | Amazon MWAA | A few scheduled DAGs do not justify $358/month |
| MLflow (tracking and registry) | MLflow 3.16.1 with authentication | Self-hosted on the core host | SageMaker AI serverless MLflow App | Keeps the course's pinned version and alias permissions |
| Monitoring | Prometheus, Pushgateway, Grafana, Alertmanager, Evidently job | Same, self-hosted; CloudWatch alarms and SNS for host and health-check alerts | CloudWatch; SageMaker Model Monitor | Model Monitor is closed to new customers and is designed for tabular data; a monitor cannot report a failure of the host it runs on |
| LLM and embeddings | Host-native llama-server (Metal): Gemma 4 12B QAT Q4_0; Qwen3-Embedding-0.6B | Bedrock: Claude Sonnet 5.5; Titan Text Embeddings V2 | Amazon Bedrock | An always-on GPU costs $587.50/month before disks; the API costs $124.82 at the assumed load |
| Identity | Pre-provisioned per-user tokens with roles | Amazon Cognito | Amazon Cognito | A self-hosted identity server adds a database and patching |
| Minikube and container registry | Minikube with its registry | ECS on EC2; Amazon ECR | EKS; ECR | As above |
| Training resource | Local CPU for review, optional existing Colab for neural experiments | EC2 g6.xlarge on demand, 40 h budget | SageMaker Training | Pay only for training hours |
| Feature store | Not needed | Not needed | SageMaker Feature Store | No entity features to look up online; tensors come from the image with versioned preprocessing |

**Local S3 development.** [Floci](https://github.com/floci-io/floci/blob/2.3.0/docs/services/s3.md) provides the S3 API locally for datasets, model artifacts, corpus files and temporary uploads and results. This lets the author develop and test S3 requests before using AWS. The application will use the same standard S3 operations in both environments, with a local endpoint, region and test credentials configured for Floci. In AWS, it will use the S3 endpoint and the task's IAM role. The SDK supports [environment-specific endpoint configuration](https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html); DVC remote and MLflow artifact settings will be checked separately in Lab 2.

Floci will use [persistent disk storage](https://github.com/floci-io/floci/blob/2.3.0/docs/configuration/storage.md), mounted on a persistent volume, so completed uploads survive restarts. Its default memory mode would lose the data. Datasets and model artifacts will be stored separately from temporary uploads and results, which retain the expiry rules in Section 6.5.

**Planned storage checks.** Lab 2 will verify S3 upload, read, list and delete operations and file checksums, including a 128 MiB file, multipart archives and completed objects after a restart. It will check valid, expired and altered signed URLs with [signature verification](https://github.com/floci-io/floci/blob/2.3.0/docs/services/s3.md#signature-verification) enabled, plus DVC push/pull and MLflow artifact upload/download. Endpoint access will be checked from the Mac in Lab 2 and from Minikube in Lab 4. These checks have not yet been run.

This selection covers S3. Passing local API checks will not establish AWS IAM permissions, networking, durability or scaling; these need checks in AWS before migration.

In Lab 4, a single documented startup command will deploy separate ML and thin text-LLM services with in-cluster MLflow on Minikube. Images carry the Git commit tag. Configuration supplies the ML, registry and host LLM endpoints and the retrieval configuration selected in Lab 3. Both services expose liveness and readiness probes. The smoke prediction will check the immutable version in the completed job. Withhold the model to demonstrate readiness failure, then change the alias to another approved version, restart and check that the next result reports that version.

The segmentation service is ready only after it loads the `champion` model and its preprocessing configuration. Without the model, the readiness probe reports that the service is not ready. The assistant is ready only when its LLM endpoint and corpus index respond.

**Training and registration.** The reviewer will fit the majority rule and RF locally and register the CPU model directly in MLflow. The B4 candidate can run on a sampled dataset on CPU. Supply the approved CPU version through the same registry alias for the serving demonstration. If the operator uses existing Colab access for a larger neural run, save `model.pt`, `checkpoint.pt`, `metrics.json` and `run.json` to Drive. On import the operator verifies hashes, rebuilds the model on CPU from the recorded configuration and registers the verified artifact. MLflow holds the course record. W&B charts are optional for Colab runs.

**LLM choices.** [Gemma 4 12B QAT Q4_0](https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf) runs through [llama.cpp](https://github.com/ggml-org/llama.cpp) with Metal on the Mac host, because Docker on this Mac has no GPU access.

The initial local choice assumes the 6.98 GB weights, context cache and Minikube fit in 24 GiB. Lab 3 will measure their combined peak usage and can select a smaller text model through configuration and repeat the same evaluation if necessary.

The hypothetical cloud deployment uses [Claude Sonnet 5.5 on Bedrock](https://platform.claude.com/docs/en/models/overview). Using [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) requires separate integration and evaluation. The service does not switch to it automatically.

[Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) creates embeddings locally. The cloud uses [Titan Text Embeddings V2](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html) if it passes the evaluation for finding English documents with Ukrainian queries. After the embedding model changes, the corpus index is rebuilt and saved under a new version.

**Cloud placement.** The always-on m6a.xlarge core host (4 vCPU, 16 GiB) runs the HTTPS proxy, both APIs, Airflow, MLflow, Prometheus, Grafana and one worker. A burst Auto Scaling group of 0–1 identical hosts adds up to three workers.

Hosts use a public subnet without a NAT gateway. S3 traffic uses a free gateway endpoint. Route 53 points to an Elastic IP. When a replacement core host boots, it re-associates that address and restores its TLS certificate from a backup.

Each job retry gets a new attempt ID. A worker with an expired lease cannot publish the result of the previous attempt over the result of the new attempt.

## 6.3 Performance

**Batch versus online.** Each upload is an asynchronous online job. A nightly batch would make the GIS user wait a day. A synchronous request would keep an HTTP connection open for minutes. The API stores the job and returns its ID. Workers claim jobs from a PostgreSQL table with `FOR UPDATE SKIP LOCKED`, so adding workers increases throughput.

| Item | Assumption and reason |
|---|---|
| Load | Section 2; 20% of a day's jobs arrive in the peak hour |
| Reference image | 4096×4096 RGB; 50 MB upload and 50 MB results on average |
| Service time | 60 s per reference image on one worker (decode, tiling, inference, stitching, export); an initial assumption for calculating the required worker count until measurements are available |
| Worker | One CPU thread, 512×512 tiles, batch size 1, within the Section 4 ceilings |

**Worker count.** Peak arrivals are 1000 / 22 working days × 0.2 = 9.09 jobs per hour. At utilization 0.6, ceil(9.09 × 60 / (3600 × 0.6)) = 1 worker covers the mean load.

During bursts, the system scales to four workers. The queue target is at most 2 waiting jobs per worker. The system waits 10 minutes before reducing the worker count (scale-in cooldown). The core services and one worker reserve 3.25 of 4 vCPU and 12.125 of 16 GiB; a burst host fits three workers.

The mean-load formula does not determine p95 completion time. A load test measures it.

**Measurement method.** Limit a worker to 1 vCPU and 4 GiB. Measure cold start separately. For each image size, 1024×1024 and 4096×4096, perform 5 warm-up runs followed by 30 measured runs. Record the time spent at each stage and peak memory use.

Replay twice the peak arrival rate for an hour. Record p95 completion time and queue wait. If the measured p95 completion time exceeds 5 minutes, first try ONNX Runtime or larger tiles. Then try more workers within the cost ceiling and the four-worker limit. Consider relaxing the target only after these steps.
## 6.4 Security

- **Authentication.** Cloud users sign in with Cognito; the API checks the token's issuer, audience, signature and expiry. Locally, pre-provisioned per-user tokens map to the `gis_user` and `operator` roles.
- **Authorization.** A GIS user creates jobs and reads only their own jobs and results. Only the operator ingests batches, starts training and changes the registry: MLflow runs with authentication. Changing the `champion` reference requires operator credentials; workers have read-only access to the registry.
- **Secrets.** An ignored `.env` file locally. In the cloud, secrets are stored as SSM Parameter Store SecureString with KMS; tasks read them through their own IAM roles. Secrets never enter Git, images or logs.
- **Network.** Only the HTTPS proxy is public; PostgreSQL, Airflow, MLflow and Grafana are private and reached through SSM.
- **Input checks.** Before decoding the whole image, the API enforces the size bounds (Section 4) and the 8-bit RGB rule (Section 5.3); it generates object keys itself and rejects archives.
- **Assistant permissions.** The controller treats retrieved text and prompts as untrusted data, validates structured tool arguments, and allows only `predict` and `retrieve`. At submission, resume and download the API checks the authenticated owner and original expiry. A foreign job yields no data or usable link. The assistant has no operator credentials.
- **Attempts and retries.** Four tool attempts are available across the whole task, including failures. The combined request uses two, leaving two for transient failures. Persist the remaining count and submission request ID across resume. After a timeout with unknown outcome, reconcile that ID with the ML API before retrying: follow an existing job, retry only a confirmed unaccepted submission under the same ID, or stop if the outcome cannot be established. An explicit re-upload starts a new job.
- **Termination.** Record success after all requested outputs are available, inability for a failed or expired job or missing evidence, and refusal for an unauthorized action. If the task needs another tool call after four attempts, stop and record budget exhaustion. Following an already accepted job uses ordinary status reads and can still complete after the fourth attempt.

## 6.5 Data privacy

Uploads may show private property, people and vehicles. A georeferenced GeoTIFF contains the coordinates of the area shown. Each upload is therefore visible only to its owner and the operator.

- **Uploads and results** are kept until `expires_at = accepted_at + 24 h`, which is 24 hours after the upload is accepted. At `expires_at`, access is denied. An authenticated download checks the owner even for a previously issued link. Any internal signed URL expires no later than `expires_at`. A queued job does not start, and a running job is cancelled. Any late output is discarded without extending the expiry. Files must be deleted at `expires_at`, and deletion is monitored (Section 6.6). The temporary bucket has no object versioning, so no old copies remain.
- **Logs and metrics** are kept for 30 days with user and job IDs, sizes, timings and errors, but no image bytes, file names, coordinates or secrets.
- **Assistant traces** record ordered attempts, redacted inputs and results, elapsed time or tokens, cost and stop reason. Durable traces retain no private imagery, filenames, coordinates, access tokens or usable artifact links. Conversation history stores an opaque job ID for authenticated lookup. Resume and previously issued links inherit the source upload's original 24-hour expiry. Public evaluation fixtures let reviewers inspect tool inputs and results.
- **Training data** comes only from the public datasets in Section 5.2 and is kept for the project's life with attribution. OEM labels default to CC BY-NC-SA 4.0 and FLAIR-HUB uses Etalab Open Licence 2.0; the project redistributes neither.
- **No user feedback** enters training in the first version: user images and QGIS corrections are never training data.

## 6.6 Monitoring and alarms

The operator receives all alerts by email. Alertmanager sends alerts for application rules. CloudWatch and SNS send alerts for rules that must still work when the host is down. Each alert has an event key, which allows the alerting system to send one email per incident.

Measure each source image once, before model normalization. Compute its three channel means over valid 8-bit pixels. Brightness is the average of those means, on a 0–255 scale. Compute each predicted class fraction on the finished source grid as its pixel count divided by all valid pixels in that image. On both sides exclude invalid pixels, padding and duplicate tile overlap. Average class fractions across completed images so that a large image carries the same weight as a small one.

| Signal | Observation and reference | Provisional rule | Action |
|---|---|---|---|
| Invalid input | One upload against the input contract | Unsupported format or depth, decode failure or zero valid pixels | Reject at acceptance or fail the job with its reason. Count validation failures separately. Produce no mask or drift observation |
| Unusually dark image | One valid image against training brightness | Below the training first percentile | Finish the job, attach a QA warning and include the observation in the input window |
| Input drift | Distribution of per-image brightness and each RGB mean against frozen training histogram bins | Daily, over the last seven days, any feature has Population Stability Index (PSI) > 0.25 | Record the feature and PSI, publish the report and email the operator |
| Prediction drift | Mean per-image fraction for each class against predictions from the same model and taxonomy on training images | Daily, over the last seven days, an absolute difference > 10 percentage points | Record the class, both fractions and their difference, publish the report and email the operator |
| Suspected quality loss | Predictions paired with independent labelled control masks | Evaluate eligible controls under §5.4 | Report per-class IoU and mIoU to the operator for a promotion or rollback decision |

Freeze a reference from the **training split** for each dataset, preprocessing configuration, taxonomy and immutable model version. Save brightness percentiles and histogram bin edges and counts for all four input features. Run that model on the same training images to save its per-class mean fractions. Build current observations from actual prediction endpoint traffic using precisely those feature definitions and bins. During a rollout, group by the recorded worker version and compare each group to its own reference.

Each population comparison needs at least 50 eligible images on **each** side. A missing reference or too few observations yields `insufficient_data` for that signal and version. Each report identifies the signal, measured value, threshold, window, both sample counts, immutable model version and reference version.

**Planned Lab 4 demonstration.** Pin the model, held-out fixture IDs, replay seed and window dates. Submit unmodified fixtures via the prediction endpoint into the first seven-day window (at least 50 eligible images). Submit a single valid darkened GeoTIFF to demonstrate a warning and a usable QGIS export. In a separate seven-day window of at least 50 eligible endpoint images, darken a recorded fraction by a recorded intensity multiplier while preserving valid pixels. Keep the two populations separate in the scheduled reports. Grafana will show both windows and the crossed threshold. Retain the operator's received alert email with the signal and report window. If the injection misses the threshold, record the result and repeat in a fresh window with a documented stronger shift.

In Lab 4, Prometheus will scrape service metrics and the Pushgateway, where the scheduled drift job will publish each report's metrics. Keep timestamp, safe input summaries, predicted class fractions, outcome and versions for each request under §6.5. Grafana and Alertmanager will use the reported signals for the dashboard and email.

| Operational signal | Window and threshold | Reason | Action |
|---|---|---|---|
| Job failures | Over the last 1 h: ≥ 3 system failures, or > 1% of valid jobs per week | 1% is the Section 3 target; 3 failures in an hour indicate a fault rather than an isolated failure | The operator reads job errors and worker logs |
| Latency | Over the last 15 min: completion p95 > 5 min, or the oldest queued job waits > 10 min while 4 workers run | Completion exceeds the p95 target; a long queue with all 4 workers running indicates that the capacity limit is too low | The operator checks worker health and limits |
| Service health | The external HTTPS check, run once per minute, fails 3 times in a row, or a worker cannot load `champion` | Host or model loss stops all jobs | The operator replaces the host or rolls back the alias |
| Training batch gate | Each new batch must pass checksum, format, grid and class-ID validation. Expected-new discovery also requires additions | A failed gate preserves the last committed version and feature rows | Notify the operator with the reason. A rerun of an accepted interval succeeds (§5.2) |
| Expiry cleanup | Hourly: any upload or result remains after `expires_at` + 1 h | The 24-hour privacy guarantee requires deletion at `expires_at`. The extra 1 h is only the alert threshold and does not extend the storage period | The operator runs the cleanup and checks the job |
## 6.7 Cost

The course reviewer path adds $0 in paid services. The figures below describe only the hypothetical AWS deployment. Prices are AWS us-east-1 On-Demand USD rates read on 2026-10-23, for a 730-hour month, before tax and operator time. Sources: [EC2](https://aws.amazon.com/ec2/pricing/on-demand/), [RDS](https://aws.amazon.com/rds/postgresql/pricing/), [S3 and internet transfer](https://aws.amazon.com/s3/pricing/), [VPC IPv4](https://aws.amazon.com/vpc/pricing/), [ECR](https://aws.amazon.com/ecr/pricing/), [Route 53](https://aws.amazon.com/route53/pricing/), [CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [SNS](https://aws.amazon.com/sns/pricing/), [SES](https://aws.amazon.com/ses/pricing/), [Cognito](https://aws.amazon.com/cognito/pricing/), [KMS](https://aws.amazon.com/kms/pricing/), [Bedrock](https://aws.amazon.com/bedrock/pricing/).

**Workload assumptions** (load from Section 2):

- For each image and its results, we allow 0.1 GB of storage for one day out of thirty: ceil(1000 × 0.1 GB × 1/30) = 4 GB on average. With 100 GB of persistent data (archives, extracted copies, tiles, checkpoints, reports) S3 holds 104 GB.
- 60 GB internet output (50 GB results, 10 GB API traffic); 10,000 S3 PUT and 100,000 GET requests.
- The hypothetical AWS workload budgets five model calls per assistant task for costing. Tool use follows the user's request and the separate four-attempt budget in §6.4. The five-call workload allowance totals 32,000 input and 4,000 output tokens. With 20% for retries and evaluation, the monthly estimate is 38.4 M input and 4.8 M output tokens, plus 1.1 M Titan embedding tokens.
- For a month with training, we also budget 20 burst CPU-host hours and 40 g6.xlarge GPU hours. These are time allowances, not measured runtimes.

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

In this estimate, LLM calls account for 41% of steady-month costs. If the agent uses a different number of tokens, actual costs may differ from the estimate. Token use is therefore the main assumption that could make the estimate inaccurate.

[Saved AWS Pricing Calculator estimate](https://calculator.aws/#/estimate?id=5149b216245db885ab6f9aa1f752302f6d636b13), verified on 2026-10-25: $299.48 for the base group and $36.17 for training, or $335.65 together per month.

The calculator is $2.27 below the listed-rate steady-month total because it omits the domain charge, applies some allowances, and uses different log-storage and rounding assumptions. Its training increment is $0.33 lower because of temporary IPv4, disk prorating and rounding.

## 6.8 Integration points

Public data providers do not guarantee that their data stays up to date or remains available. We therefore pin each source's revision, record file checksums and set our own rules for accepting data.

| Boundary | Payload and format | Timing | Responsibility and failure behaviour |
|---|---|---|---|
| OEM authors → training-data ingestion pipeline | Zenodo release: images, masks, metadata; xBD images from xview2.org | Once, for the initial batch | We record the release ID and checksums, remap labels, and reject the whole batch if grids do not match or IDs are unknown |
| IGN (FLAIR-HUB) → training-data ingestion pipeline | Each batch contains one domain's `AERIAL_RGBI` and `AERIAL_LABEL-COSIA` ZIPs at a pinned Hugging Face revision | When the operator starts an update | Bind the logical interval to its frozen manifest. Reuse an accepted version on replay. On a missing archive or invalid pair, fail before publishing feature rows or advancing the watermark (§5.2) |
| USGS / UGRC (NAIP) → monitoring | 4-band GeoTIFF tiles; the adapter keeps RGB | Optional, separately for each imagery vintage (Section 5.2) | We record tile IDs and checksums; the tiles are used only in drift reports |
| Documentation authors → corpus | Pages and PDFs listed in Section 5.2 | We save copies when building the corpus | Each copy has a SHA-256 checksum. A changed page gets a new `doc_version`; the saved version is not edited |
| GIS user → API | One image per request, in the Section 4 formats and bounds | Any time | We return a job ID, or a validation error that explains the problem |
| API → GIS user | Job status and the result package (Section 4) | Completion p95 as in Section 3; available until `accepted_at` + 24 h, including queue and processing time | A failed job returns its reason and no partial package |
| Assistant → Lab 3 retriever (`retrieve`) | Question text → relevant passages with `doc_id`, `doc_version` and section locator | Once for a legend question or the explanation in a combined request | Cite the passage supporting the answer. If no source supports it, report that limitation |
| Assistant → Lab 4 ML endpoint (`predict`) | Caller-scoped image reference and submission request ID → job ID and state | On an explicit prediction request | The API checks ownership and accepts the job into the queue. The controller follows that job under the caller's identity. The worker decodes, tiles, predicts, stitches, checks the grid and exports |
| Service ↔ operator | Alerts and candidate reports (Section 6.6); commands to add a batch, approve a candidate or roll back | Alerts when a rule fires; a review for each candidate | Each alert names the batch, run or model and the rule that fired |

For the request in §2, suppose a 4096×4096 georeferenced GeoTIFF is accepted as job J17. The assistant shows `queued`, then `running` while the CPU worker processes it. When J17 succeeds, the owner gets a download link for the mask, overlay, legend and JSON metadata until the original upload expiry. The GeoTIFF mask preserves the source dimensions, CRS and affine transform. If the worker recorded model version 4 and taxonomy v1, the answer reports version 4 even if the alias has since moved. The accompanying citation identifies the retrieved revision of `export-contract`, §5.1, for the meanings of 255 and 0.

Suppose J17 has valid pixels but falls below the training brightness percentile in §6.6. Its package carries a warning and its brightness counts toward version 4’s window. If the seven-day window later has 60 images and brightness PSI reaches 0.31 against an eligible version 4 reference, the operator receives a drift email. The operator can keep version 4 serving and request labelled controls to check IoU. These numbers illustrate the defense walkthrough. Lab 4 will collect the measurements.

Lab 5 will exercise the same two tools on a versioned set of at least ten tasks, each with explicit pass criteria, including a legend question, a combined prediction, an operator-only refusal and retry failures. Run every task at least twice. Report pass rate, mean tool attempts and mean cost per run, explain differences between repeats, and retain an ordered public-fixture trace ending in budget exhaustion (§§6.4–6.5). For local evaluation, apply a declared shadow price of $0.01 per minute of elapsed run time to every run, including failures.

## 6.9 Risks and uncertainties

| Risk | Mitigation |
|---|---|
| FLAIR scores combine changes in year and region and cover 6 of 8 classes | Report OEM-8 and regional scores separately. Evaluate road and developed space on OEM (Section 5.4) |
| The crosswalk assigns the wrong class, for example herbaceous vegetation instead of grazed agriculture | Inspect image–mask pairs, class histograms and sample masks in the first data pilot before freezing crosswalk v1. Keep ambiguous classes at 255 |
| Evaluation images or neighbouring tiles enter training and make accuracy look better than it is | Split the data by region (Section 5.4) |
| Evaluation reuses images that were used in pretraining | Never use the official OEM lightweight weights, which were trained on train and validation data |
| An update reduces accuracy for road or developed space | Use OEM replay (Section 5.3). Allow a loss of no more than 2 percentage points of IoU for each OEM class (Section 5.4) |
| A dark region triggers a warning or a gradual shift goes undetected | In Lab 4 declare the acceptable false-alarm rate and the cost of missing a shift before calibration. Measure false alarms on unchanged held-out traffic and detection at the recorded fraction and strength of darkening (§6.6). Inspect the source mix and use independent labelled controls before attributing an IoU loss |
| CPU inference is slower than the assumed 60 s | Measure inference time first, then use the fallback steps in Section 6.3 |
| A large or malformed raster exhausts worker memory | Check the limits before decoding (Section 6.4) and process one tile at a time. If processing fails, mark the job as failed and record the reason |
| The export appears in the wrong location on the map | Use georeferencing only from a valid input (Section 4). Check it with the QGIS test set (Section 3) |
| The core host or the RDS availability zone fails | Persist job state and use leases, which give a worker temporary ownership of a job (Section 4). Use the external health check (Section 6.6) |
| The agent uses more tokens than estimated | Limit turns and context per task, and record tokens per run in Lab 3. Claude Haiku 5.5 is the cheaper candidate if it passes the evaluation |
| The assistant follows instructions embedded in a document | Validate every tool argument in code (Section 6.4) |
| A Colab session ends during training | Write `checkpoint.pt` to Drive every epoch and resume the run from it |

## 7.1 Alternatives

| Alternative | Pros | Cons | Decision |
|---|---|---|---|
| Building-only segmentation | Simpler labels and model | Misses most GIS classes | Rejected framing (Section 5.1) |
| Synchronous HTTP inference | No job table or queue | HTTP requests that take minutes may exceed the timeout | Rejected; asynchronous jobs (Section 6.3) |
| Teacher pseudo-labels on unlabelled NAIP | Same-place image history | Agreement with a teacher does not measure accuracy; the model with official OEM weights was trained on data from our control sets | Rejected: every training batch has expert masks, so no teacher is needed |
| Chesapeake LULC with NAIP as the update source | Same places in three periods | Semi-automated labels revised in later editions; scripted access to the 2024 edition unverified | Alternative if same-place history matters more ([USGS](https://www.usgs.gov/data/chesapeake-bay-land-useland-cover-lulc-database-2024-edition)) |
| FT-UNetFormer or Satlas as the first candidate | Higher published score; aerial pretraining | Section 5.3 | Revisit after the first implementation |
| Richer taxonomy (e.g. FLAIR's coniferous and deciduous) or open-vocabulary segmentation | More classes; new concepts without a new head | A new taxonomy changes the head, legend, crosswalk and controls; a text prompt is not a validated class | Keep OEM-8; add classes when a concrete GIS need appears |
| W&B instead of MLflow | Provider-hosted dashboards that update during training | An account and a [5 GB free storage limit](https://coreweave.com/forge-pricing); Lab 2 names MLflow | Optional graphs of metrics during training only |
| MWAA and a legacy managed MLflow server | No Airflow or MLflow operations | About $797/month together | Self-hosted (Section 6.2) |
| High availability: second host, RDS Multi-AZ, load balancer | Survives one host or zone failure | About +$190/month and failover tests | Not selected; continuous single-host service |
| Learning from GIS users' corrections | Real labels for new regions | Needs consent and image licences; an "OK" click confirms the model's own errors; needs a review interface | Not in the first version (Section 6.5) |

## 7.2 Placeholder

Lab 2 fills this section with the baseline and update-candidate experiment results.

## 7.3 Placeholder

Lab 4 fills this section with deployed throughput, p50 and p95 latency and resource measurements.

## 7.4 Milestones

- **Lab 2** will show repeatable sampled ingestion, a failed gate and a successful DAG, then compare the majority rule with a reproducible CPU RF tagged with the DVC hash and Git SHA.
- **Lab 3** will rebuild and count the corpus index, compare plain and retrieved answers across retrieval settings, and publish the chosen configuration and prompt hashes for serving.
- **Lab 4** will start the two services, check alias loading, readiness and a versioned smoke prediction, and demonstrate two endpoint replay windows on the dashboard with a delivered drift email.
- **Lab 5** will run at least ten versioned tasks twice against the Lab 3 retriever and Lab 4 prediction endpoint, reporting pass rate, steps, cost and traces for refusal and budget exhaustion.

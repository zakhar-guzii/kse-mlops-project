# Design

## Context

See [proposal.md](proposal.md) for motivation and scope. The existing English design already has the correct 22 numbered headings and three Mermaid diagrams. Its content still describes majority-class prediction, a ResNet18 candidate, teacher-labelled Utah updates, single-user/on-demand operation and a $1,229.81 cloud scenario. The Ukrainian translation mirrors these choices and begins with a stray `e`. README repeats the automatic-annotation lifecycle and old diagram/calculator claims.

The inputs are [Lab 1](../../../labs/lab-1.pdf), [review G and 1–35](../../../docs/reviews/design-round-1.md), and the five validated research notes: [writing principles](../../../docs/research/design-doc-principles.md), [datasets](../../../docs/research/landcover-finetuning-datasets.md), [models](../../../docs/research/landcover-models.md), [LLM/tracking](../../../docs/research/llm-training-tracking.md), and [cloud costs](../../../docs/research/cloud-deployment-cost.md). The user's selections supersede recommendations where they differ, notably 24-hour rather than seven-day upload retention. The user also explicitly confirmed Gemma locally, Sonnet in the cloud and Sol as an alternative without automatic failover.

There is no application implementation or existing capability specification to migrate. This is a documentation-only change with `skip_specs: true`. The English document remains canonical; Ukrainian is a synchronized translation. Research, reviews, the PDF and the translation currently match ignore rules, so the tracked English document must include its own concise rationale and direct primary-source links.

## Goals / Non-Goals

**Goals:**

- Give each decision one authoritative section, then use consistent terms, actors and quantities in tables, diagrams and the translation.
- Turn the review into concrete, checkable documentation changes while keeping Lab 1's scope and structure.
- Preserve the user's selected alternatives as comparisons, without turning optional experiments into additional first-version dependencies.
- Make cost and quality examples reproducible and visibly distinguish examples, initial assumptions and actual evidence.

**Non-Goals:**

- Implement any pipeline, API, authentication, model, runtime, deployment or feedback feature described in the target design.
- Train or benchmark models, download imagery/weights, install a new stack, create paid resources, publish a calculator estimate or commit changes as part of this proposal.
- Change `.gitignore`, the archived change, research findings, or unrelated README verification history.

## Decisions

### 1. Rewrite within the lab's existing section contract

Replace prose by topic rather than patching old sentences. One opening sentence identifies the course project; the rest describes the intended system directly. Keep short justified `Assumption:` statements where numbers are provisional. Remove process transcripts, repeated disclaimers, slash-chain lists and remarks about unavailable future-lab instructions. Explain promotion, old-data replay and monitoring without reference masks once, in ordinary language.

| Required English heading | Content after the rewrite |
|---|---|
| 1 Overview | Three to five sentences: GIS input/output and supervised model-update lifecycle. |
| 2 Motivation | GIS consumer, useful output and consequences of incorrect maps; separate consumer and operator. |
| 3 Success metrics | Workflow/export target, model-quality gates and service budgets. Keep the 9/10 valid-export target; do not call it measured cartographic accuracy. |
| 4 Requirements and constraints | Functional behavior, exactly seven NFR categories, target-service limits and one concise local-course constraint. |
| 5.1 Problem statement | Eight-class semantic segmentation, canonical IDs 0–7 and ignore=255. Reject building-only segmentation because the GIS task also needs roads, vegetation, water and other cover types. |
| 5.2 Data | Sources, chronological roles, native-to-OEM mapping, nullable dates, manifest/freshness example, storage/versioning table and named retrieval corpus. Answer all four data-checklist questions. |
| 5.3 Techniques | RF baseline, exact U-Net/EfficientNet-B4 implementation/initialization, serving-time feature sources and model alternatives. |
| 5.4 Experimentation and validation | Numbered split/train/evaluate/compare protocol; separate development/final controls; full confusion counts; both promotion policies and examples. |
| 5.5 Human in the loop | Operator reviews alerts/candidates, blocks or approves activation, rolls back; GIS users receive and may externally edit exports. |
| 6.1 High-level design | Three shared SVGs: context, seven-layer data flow and simple deployment placement. |
| 6.2 Infra | Minimal component table: local implementation, managed equivalent, selected cloud deployment and one-line reason. Colab exchange and optional W&B belong here. |
| 6.3 Performance | Async/batch decision, load and reference raster, resource ceilings, worker calculation and short measurement method. |
| 6.4 Security | Authentication, per-user job ownership, operator-only registry mutation, secrets and key input/tool boundaries. |
| 6.5 Data privacy | 24-hour ordinary-upload/result expiry, separate logs/training artifacts and no first-version user-feedback ingestion. |
| 6.6 Monitoring and alarms | Compact signal/window/threshold/recipient/action table; operational failures, training freshness and selected distribution signals. |
| 6.7 Cost | Justified workload, compact complete cloud table, before/after recurring allowances and calculator status. |
| 6.8 Integration points | External data owners, authenticated GIS user and operator; payload/format, timing, responsibility and failure behavior. |
| 6.9 Risks and uncertainties | System-specific risks and one concrete mitigation each; no lab task list. |
| 7.1 Alternatives | At least two reasoned alternatives; include the requested model comparisons and optional W&B. |
| 7.2 Placeholder | One useful sentence identifying the later Lab 2 extension. |
| 7.3 Placeholder | One useful sentence identifying the later Lab 4 extension. |
| 7.4 Milestones | One sentence each for Labs 2, 3, 4 and 5. |

Use the lab's seven NFR categories: freshness; latency and throughput; availability and fallback; reproducibility; adaptability; observability without ground truth; cost and resource ceilings. Every row contains a number or explicit assumption. Retain §7.2–7.4 because the assignment requires them, despite the review's request to remove their verbose contents.

### 2. Adopt supervised FLAIR-HUB updates and keep OEM-8

Use OEM for initial training and reserve separate scene/region-grouped development and final controls before cropping. Use the proposed RGB/CoSIA FLAIR-HUB subset: D080-2017 → D033-2018 → D065-2019 → D045-2020 for updates, D017-2021 for development, and D073-2022 for final regional evaluation. Freeze any final-domain extension before examining model scores. Pairing, class coverage and overlap checks are future pilot prerequisites, not results of the document rewrite.

Describe this as retrospective transfer across acquisition years and regions. It does not isolate temporal change at the same place or establish what a model available in 2017 could have achieved. Expert masks arrive with downloaded images, giving zero label delay at project ingestion; a simulated one-batch delay is explicitly labelled as such if used later.

Keep the eight-output contract and OEM raw remap 1–8→0–7, 0→255. FLAIR-HUB's native IDs differ from FLAIR-1/2. Its conservative crosswalk supervises OEM IDs 0, 1, 4, 5, 6 and 7; road/developed retention is evaluated on OEM controls. Regional and OEM mIoU are separate metrics. Construct full 8×8 confusion counts on valid reference pixels so an unsupported-class prediction remains an error. Record scored IDs, support, ignored fraction and mean denominator; missing required class coverage makes evaluation incomplete.

NAIP expansion remains documented as an optional inference/monitoring stream. It is not a teacher-based training dependency. Chesapeake is an alternative for repeated-place history, with its semi-automated/revised labels and access limitations stated accurately. Richer taxonomy and open-vocabulary models remain alternatives, not additional validated product classes.

### 3. Select one model while preserving meaningful alternatives

| Role/option | Treatment in the document | Reason and trade-off |
|---|---|---|
| RGB/texture random forest | Selected CPU baseline producing the same eight-class mask contract | Real mapping without pretrained weights. Fit directly through scikit-learn with ignore filtering; the scikit-image helper treats label 0 as unlabelled. |
| SMP U-Net/EfficientNet-B4 | Selected neural candidate; explicit `tu-tf_efficientnet_b4.in1k` initialization and corresponding preprocessing | OEM architecture evidence and a maintained PyTorch path. Published scores do not establish this checkpoint's accuracy or CPU speed. |
| FT-UNetFormer/Swin-B | Concise comparison with paper/code/checkpoint links; revisit after the first implementation | Higher published OEM score, substantially more parameters, older research dependencies and weight-term checks. |
| Satlas Aerial Swin-v2-Base | Concise comparison with links; possible later aerial-pretraining experiment | Aerial pretraining and supplied segmentation head; larger model, NAIP overlap/scale questions, and ODC-BY weight terms distinct from metadata tags. |

Pretrained encoder weights initialize only the first OEM training run; this project does not perform ImageNet pretraining. Each update resumes the approved full segmentation checkpoint, including decoder/head, and mixes selected old OEM training examples with the new labelled batch. Replay share and learning rate are experimental settings selected using development controls. Do not add a required teacher: unlabelled inputs are inference/monitoring-only in the selected first version.

Compare alternatives by architecture/pretraining, taxonomy fit, benchmark protocol, CPU/RAM fit, dependency/licensing and control independence. Preserve the user's intention to revisit them after implementation without adding training of all candidates to this documentation change.

### 4. Explain both promotion policies with calculated examples

For the first neural approval, compare the RF baseline and initial U-Net on the same OEM development control. The neural candidate must exceed RF OEM-8 mIoU and pass the export/resource checks. Report its regional score separately. The subsequent update policies compare against the approved model, not against RF.

The selected initial policy makes a candidate eligible for operator review when all of these hold on the same frozen development manifests:

1. OEM-8 mIoU is at least the currently approved model's value.
2. Mapped regional mIoU is greater than the approved model's value.
3. No supported OEM class loses more than **2 percentage points**. Exactly 2 pp is allowed; the quantity is an absolute IoU difference, not a relative percentage.
4. Required class coverage, export validity and declared resource checks are satisfied.

The strict alternative retains the same mean/regional requirements but permits no supported OEM class to decrease. Explain why it protects every class more strongly and may block useful adaptation. The 2 pp tolerance is a selected starting policy, not an experimentally calibrated constant.

Use these **hypothetical examples**, never present them as measurements:

| Model | OEM mIoU | Regional mIoU | Largest OEM class decrease | Selected bounded policy | Strict alternative |
|---|---:|---:|---:|---|---|
| Approved reference | 60.0% | 50.0% | — | — | — |
| Candidate A | 60.4% | 52.0% | 1.5 pp | Eligible | Fails |
| Candidate B | 60.4% | 52.0% | 0 pp | Eligible | Eligible |

An unchanged regional mean fails both policies. Never use either final holdout for tuning, replay selection or repeated promotion decisions. Passing a gate does not automatically activate a model: the operator can block it, switch the approved registry alias, or roll back. Workers resolve and record an immutable version, and explicit reload/rollout activates a changed alias for new jobs while in-flight jobs keep their recorded model.

### 5. Keep training/tracking simple and name the chosen LLMs

Owned Colab Pro is the main available training resource; the Mac supports small/debug runs. Describe exchange as exporting weights, metrics and recorded data/code/config lineage, then importing into local MLflow. Retain a full training checkpoint for interrupted-run resumption separately from a serving export. Do not introduce inbound tunnels or a second tracking migration pipeline.

MLflow is authoritative for runs, artifacts, registry, approval and traces. Optional W&B curves provide a live Colab view but add an account/destination and storage limits. Show the difference in one compact comparison; W&B is neither required nor a second promotion authority. A complete replacement is not selected because Lab 2 explicitly names MLflow.

The user confirmed host-native **Gemma 4 12B QAT Q4_0 with llama.cpp/Metal** locally and **Bedrock Sonnet 5.5** in the cloud. **GPT-6.1 Sol** is a separately integrated/evaluated alternative, without automatic provider failover. Preserve task/error state and allow a retry during a provider outage. Use Qwen3-Embedding-0.6B locally; Titan V2 is the researched cloud option conditional on Ukrainian-to-English retrieval evaluation. Changing embedding models rebuilds/version-controls the index. No project tool-quality or concurrent-memory result is claimed.

### 6. Describe a coherent small service, with concrete assumptions

Keep local application containers CPU-only and the local LLM runtime on the Mac host. Local Minikube remains the course deployment; the chosen cloud deployment is ECS on EC2. Distinguish the two application services needed by the later scorecard: segmentation/job service and assistant service. Use a small shared vocabulary across §6.2 and the deployment diagram: applications/workers, object storage, PostgreSQL/pgvector, Airflow, MLflow, monitoring, training resource, identity and LLM/embeddings. Name managed equivalents while separately indicating the actually selected cloud component.

Cloud: one m6a.xlarge core host, a burst group for additional CPU workers, RDS PostgreSQL Single-AZ, S3, proxy/EIP ingress, Cognito, and self-hosted Airflow/MLflow/monitoring. Task and instance scaling are distinct. The NAT-free topology requires the researched bridge networking/task-role/host-IMDS isolation approach; keep its technical detail in supporting rationale rather than expanding the deployment placement diagram. Queue leases, retry fencing, worker draining and EIP/certificate recovery must be described as mechanisms to implement later. Continuous service is the selected goal; HA and a numerical uptime guarantee are not selected.

Use a compact assumption set in §§4/6.3; keep capacity inputs separate from measured outcomes:

| Item | Initial design assumption and reason |
|---|---|
| Load | 20 active users, 1000 images and complete agent tasks/month; a small team workload. 2200 is a sensitivity case. |
| Reference image/runtime | 4096×4096 RGB; average 50 MB input and 50 MB output. A 60-second service time on one 1-vCPU worker is the initial capacity input. |
| Response targets | Job acknowledgement p95 ≤1 second after upload completion; end-to-end p95 ≤5 minutes for the reference image at the stated load. Measure queue time separately. Targets must later be verified under cold-start/burst conditions. |
| Worker resource ceiling | One CPU thread, 4 GiB RAM, 512×512 tiles and batch size 1 initially; 1–4 workers across core/burst capacity. Tiling bounds model input; actual peak memory requires the exact implementation check. |
| Input/execution bounds | Initially 128 MiB encoded input, 64 megapixels decoded and a 15-minute execution deadline, always capped by the upload's expiry. These bound disk/decoding/work time; they are configurable pilot assumptions, not restrictions inferred from the 4096 example. |

At 20% of daily jobs in the peak hour, arrivals are `1000/22×0.2 = 9.09/hour`; with target utilization 0.6, `ceil(9.09×60/(3600×0.6)) = 1` worker. Bursts can scale to four. Preserve the research's core budget of 3.25/4 vCPU and 12.125/16 GiB, including one worker; the burst node holds three workers. Do not infer p95 from this mean-capacity formula.

Authentication and per-user result ownership apply locally and in the cloud. A small local demo can use pre-provisioned per-user tokens mapped to GIS/operator roles; cloud user identity is delegated to Cognito. Administrative/registry credentials are separate, MLflow authentication is enabled, and the assistant cannot promote models or change infrastructure. Secrets stay outside Git/logs. Explain only the essential upload bounds, valid channel mapping and deterministic tool checks. Known bit-depth/container conversion is a post-baseline adapter; unknown band meaning is never guessed.

### 7. Apply 24-hour retention and recalculate the estimate

Set `expires_at = accepted_at + 24h` for ordinary uploads/results. Deny access and new work after expiry; bound signed URLs by that timestamp and prevent late outputs from extending retention. Cleanup is due at expiry and monitored; an object-store lifecycle rule alone does not prove exact-clock physical deletion. Keep temporary objects separate from long-lived dataset/model artifacts and avoid retaining old temporary-object versions. Do not add user images or QGIS corrections to training in the first version. Keep the existing separate 30-day technical-log assumption, without image bytes, secrets or unnecessary identifying metadata.

At unchanged workload and published 2026-10-23 regional rates, only retained user-object storage changes:

- Main case: `ceil(1000×0.1 GB×1/30) = 4 GB` temporary, plus 100 GB persistent = **104 GB**. S3 storage/requests: `104×0.023 + 10×0.005 + 100×0.0004 = $2.482`.
- Growth case: `ceil(2200×0.1×1/30) = 8 GB` temporary, total **108 GB**; requests scale to 22k PUT/220k GET, giving **$2.682** storage/requests.
- The old seven-day research scenarios use 124/152 GB. Subtract only storage differences of **$0.460/$1.012**; do not scale transferred bytes, model tokens or requests by the retention change.

Compact main-case listed-rate reconciliation:

| Component group | Monthly USD before recurring allowances |
|---|---:|
| Core EC2, 50 GB gp3 and one IPv4 | 133.794 |
| RDS PostgreSQL, 20 GB gp3 | 25.660 |
| S3 retained objects and requests | 2.482 |
| ECR | 0.500 |
| DNS, amortized domain and HTTPS health check | 3.373333… |
| CloudWatch, SNS and SES | 5.390050 |
| Cognito and KMS | 0.330 |
| Internet output | 5.400 |
| Sonnet and Titan | 124.822 |
| **Steady listed total** | **301.75** |

The same 20 burst CPU-node hours cost $3.6655890411 and 40 G6 hours cost $32.8303561644. They are optional active-month budgets, not measured training requirements. Main recurring allowances deduct $12.52005 when available; growth deducts $16.12005 under the research's larger log/egress quantities.

| Scenario | Steady listed | Steady with allowances | Active listed | Active with allowances |
|---|---:|---:|---:|---:|
| 1000 tasks; 24h retention | $301.75 | **$289.23** | $338.25 | **$325.73** |
| 2200-task sensitivity; 24h retention | $460.29 | $444.17 | $496.79 | $480.67 |

Retain full-history token accounting: five sequential calls, 32k input/4k output tokens per task before 20% allowance; 1000 tasks produce 38.4M input/4.8M output and $124.80 Sonnet cost. Titan's separate 1.1M-token allowance is $0.022. USD, us-east-1, 730 hours, before tax/operator labour; account allowances are conditional and actual course cloud spend remains $0.

Use the [cloud note's dated rate sources](../../../docs/research/cloud-deployment-cost.md#52-live-unit-rates-and-reproducible-provenance) and [LLM derivation](../../../docs/research/llm-training-tracking.md#4-cost-the-full-conversation) to reproduce the compact table. Link primary rate pages directly from the rewritten document. The old public estimate belongs to the old $1,229.81 scenario. Prepare/reconcile the replacement calculator inputs during apply; publish a new share link only after the exact estimate is reviewed and explicitly authorized. If publication remains pending, say so and do not claim the revised calculator requirement has been completed.

### 8. Use three shared SVGs and keep translation/README aligned

Create `docs/diagrams/context.svg`, `data-flow.svg` and `deployment.svg`, referenced by both documents. Use English component labels consistently, with localized captions/alt text. Add SVG titles/descriptions, explicit readable colors/background and sensible view boxes. Render and visually inspect all three; check embedding in both Markdown documents. No additional diagram framework or duplicate Mermaid source is necessary.

- Context: one system boundary, upstream image/label/document owners, GIS user, operator/alert recipient and labelled payload arrows. Colab is infrastructure, not a merged external user.
- Data flow: seven numbered layers, explicit version point and quality gate, offline/online divergence, registry alias and monitoring-to-training loop. Show ordinary re-upload separately from expected-new training freshness. Retain the feature layer while explaining that no separate feature-store service is needed.
- Deployment: simple local placement boxes with managed-equivalent names, matching §6.2. Follow the appendix's uncluttered no-arrow placement style; put cloud network/accounting detail in §6.7 rather than tangling the drawing.

Translate after the English sections and numbers stabilize. Preserve numbering, tables, conditions, links and the English-authoritative notice. Fix the leading `e` and use `../labs/lab-1.pdf` for the local assignment link; identify that the ignored course PDF is not distributed in a clean clone. Direct public references support the design without relying solely on ignored research links.

Update README only where it mirrors changed content: the five-sentence overview, current design/diagram/cost references, and the canonical-English/translation statement. Preserve valid historical setup/lint/CI evidence with its original dates; do not relabel old Mermaid rendering or the old saved calculator as verification of the new assets/estimate. Do not change the user's ignore rules to publish local materials.

### 9. Close every review item through document acceptance checks

| Review items | Required closure |
|---|---|
| G | Concise full rewrite; concrete actors/methods; justified assumptions; no process transcripts or repeated hedges. |
| 1, 20, 21 | Separate consumer/operator; define alias promotion, actual rollout, candidate veto and rollback. User mask correction is external editing, not first-version training ingestion. |
| 2, 11, 13 | Re-uploads succeed; nullable dates; training-only freshness, stable manifest/checksums, intentional idempotent replay and commit-before-watermark example. |
| 3, 4, 7, 28 | Multi-user queue/workers, continuous recoverable service, assumed resource/latency budgets and coherent cost; local hardware is an execution constraint. |
| 5, 19 | Explain old-data mixing, development/final split, metric computation, selected 2 pp gate and strict alternative examples. |
| 6, 31 | Plain meaning of absent reference masks; compact monitoring with concrete windows/thresholds, reason and operator recipient. |
| 8 | Baseline canonical RGB; known format/bit-depth conversion as a later adapter; no guessed bands. |
| 9, 10, 12 | Labelled FLAIR timeline, NAIP expansion, OEM-8 mapping, honest retrospective meaning; remove unsupported teacher-agreement compensation. |
| 14, 15 | Concrete artifact/format/local/cloud/versioning table and clear Git versus DVC versus LFS explanation. |
| 16, 17, 18 | Real RF baseline, selected U-Net/EfficientNet-B4, explicit FT-UNetFormer/Satlas comparison and no required teacher. |
| 22, 26 | Simple training export/import, authoritative MLflow, optional W&B and named local/cloud LLM choices. |
| 23, 24, 27 | Three readable SVG views, consistent minimal infrastructure table, concise readiness contract and no architecture filler. |
| 25, 32 | Selected self-hosted/managed trade-offs, named equivalents, complete recalculation and truthful calculator status. |
| 29, 30 | Authentication/ownership/secrets, 24-hour private-data expiry, no automatic feedback training. |
| 33 | External owner/consumer contracts; taxonomy/corpus/training exchange moved to their proper sections. |
| 34 | Concrete current risks with one mitigation each; remove future-lab task lists. |
| 35 and review extras | Keep minimal required placeholders/milestones; fix the local Lab link and translation's leading character. |

Final document checks cover 22 headings in each language, seven NFR categories, three success-metric levels, four data-checklist answers, three SVGs, at least two reasoned alternatives, and four later-lab milestones. Recompute examples/costs, inspect local links, reconcile vocabulary/quantities across both documents and README, and visually inspect every SVG. Runtime tests and new backend tests are inappropriate for this documentation-only change.

## Risks / Trade-offs

- **FLAIR year/region confounding and partial labels** → State the transfer question and class mapping, retain full OEM development/final controls and report the two evaluations separately.
- **Paper results mistaken for project evidence** → Attribute published protocols; label hypothetical examples and resource/quality assumptions once at their point of use.
- **Chosen CPU/LLM stack exceeds resources** → Keep exact future measurement criteria and declared limits; do not claim compatibility or performance from file sizes or wheel metadata.
- **Doc growth recreates the review's problem** → Keep operational implementation detail in research/planning rationale; the working design contains only each section's required decisions, reasons and contracts.
- **Single-host/Single-AZ outages** → Describe queue/state recovery and external alerting; do not advertise HA or a demonstrated recovery bound.
- **Strict expiry conflicts with queued/running work or object versions** → Cap access/job publication by expiry and cover every temporary-object version in cleanup; keep long-lived model/data artifacts separate.
- **Ignored local evidence or stale translation** → Include public sources and essential rationale in English, share SVG assets and compare all translated numbers/conditions. Preserve existing ignore rules.
- **Old calculator/README claims appear current** → Keep historical evidence labelled and make revised calculation/publication status explicit until a newly authorized estimate is saved.

## Migration Plan

1. Rewrite the English data/model/evaluation sections from the selected decisions and the review coverage table.
2. Rewrite service/security/privacy/monitoring/cost/contracts/risks and the minimal ending sections, using the recalculated 24-hour inputs.
3. Create and inspect the three SVGs; integrate §6.1 and reconcile component names with §6.2.
4. Synchronize the Ukrainian document and the narrow README mirrors.
5. Run the document acceptance checks, correct findings and mark implementation tasks only when their artifacts are verified. Calculator publication is a separate authorized action; unresolved publication must remain visible.

There is no runtime rollout or data migration in this change. Rollback consists of restoring the affected Markdown/SVG files while preserving unrelated work.

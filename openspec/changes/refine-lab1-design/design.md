# Design

## Context

See [proposal.md](proposal.md). The design has the required 22 sections, three SVGs and a reconciled cost model.

The [round-2 review](../../../docs/reviews/design-round-2.md) and its [closure matrix](../../../docs/reviews/design-round-2-closure.md) list the remaining defects:

- S1–S5: missing contract details;
- E1–E14: wording and repetition;
- D1–D3: diagrams;
- N1: NAIP scope;
- R1–R4: README.

English stays canonical. The Ukrainian file is a local translation.

## Goals / Non-Goals

**Goals:** close every partial item, state each fact once, and keep every Lab 1 structural requirement.

**Non-Goals:**

- New system behavior or changes to the selected stack, models, data or costs.
- Saving the calculator estimate on the user's behalf.
- Editing archived changes, research notes or ignore rules.

## Decisions

### 1. One statement per fact

Each fact lives in one section. Other sections reference it as "(Section X)" or drop it. The only exception is a number that Lab 1 requires both as a §3 metric and as a §4 NFR.

| Fact | Home |
|---|---|
| Load: 20 users, 1000 images a month | §2 |
| Input and resource bounds | §4, cost and resource ceilings |
| Training-only freshness; manifest example | §5.2 |
| A re-upload creates a new job | §4, functional |
| Fine-tuning from the full checkpoint with OEM replay | §5.3 |
| Year and region change together | §5.2, checklist item 1 |
| Region split before cropping; isolated final holdouts | §5.4 |
| Only the operator activates a model | §5.5 (process), §6.4 (permission) |
| The assistant cannot change models or infrastructure | §6.4 |
| Readiness without a loadable model | §6.2 |
| No user edits enter training | §6.5 |
| No high availability | §4, out of scope |
| IoU only on labelled batches | §4, observability |
| No teacher model | §7.1 |
| Alert channel | §6.6 |

Editorial changes:

- E5: one-sentence intro.
- E6: overview of five sentences, one each for need, result, access, update and effect. README repeats it verbatim.
- E7: the §5.2 timeline comes before the checklist, the label mapping after it.
- E8: random-forest definition first, then parameters. The helper rationale becomes "fit directly: label 0 is a valid class".
- E9: the RGB paragraph opens with the 8-bit requirement.
- E10: remove the generic "Both are compared on…" sentence.
- E11: MLflow/W&B becomes one §6.2 sentence plus the §7.1 row.
- E14: §7.1 cons become short phrases with section references.

### 2. Contract wording

- **Size (S4).** "Different sizes and aspect ratios within the bounds" in §1, §4 and README.
- **Deadline (S5).** In §6.8, completion p95 refers to the §3 target and its reference-image and load conditions. Results are available until `accepted_at` + 24 h, including queue and processing time.
- **Masks (E1).** "User uploads have no reference masks."
- **Support.** Class support means reference pixels per class.
- **LLM memory (E4).** The fit in 24 GiB is an assumption that Lab 3 measures, not a conclusion from file size.
- **Course spend.** Colab Pro is an existing subscription, so the course adds no paid spend.

### 3. Drift reference windows (S1)

One assumption sentence goes into §6.6:

- **Input statistics.** Compare the last 7 days with a frozen snapshot of the first 14 days of service (at least 100 images). The operator replaces the snapshot only after accepting a reviewed shift as normal.
- **Predicted class shares.** These depend on the model, so the reference is the first 7 days after each `champion` activation (at least 50 images).
- **PSI threshold.** 0.25 is checked against the PSI between the two 7-day halves of the input reference.
- **Too little data.** With an incomplete reference or fewer than 50 images, the report says "insufficient data".

Rejected alternatives:

- One reference reset at every activation. This blinds input drift for 14 days after each monthly update.
- A rolling week-over-week comparison. This misses gradual drift.

### 4. NAIP scope (N1)

We considered Utah NAIP from 2011 to 2024 ([UGRC](https://gis.utah.gov/products/sgid/aerial-photography/naip/): 1 m before 2018; 0.6 m in 2018, 2021 and 2024) and the Chesapeake states from 2010 to 2023 ([Planetary Computer](https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip)). None has human OEM-8 masks, so NAIP adds no update batches.

The Utah 0.6 m vintages, closest to OEM's 0.25–0.5 m, remain an optional unlabelled monitoring stream. Labelled same-place history remains the Chesapeake alternative in §7.1.

### 5. Alternative model weights (S3)

- FT-UNetFormer: GeoSeg links its [Swin-B backbone weights](https://drive.google.com/drive/folders/1ELpFKONJZbXmwB5WCXG7w42eHtrXzyPn).
- Satlas: [`aerial_swinb_si.pth`](https://huggingface.co/allenai/satlas-pretrain/tree/main).

Both are initialization weights; neither project publishes an OEM-8 checkpoint. The design states this limitation instead of implying ready models.

### 6. Training stays in Colab (item 22, D2)

The user chose to run all neural training in Colab Pro, started by the operator. The Mac runs small runs and the random forest.

§6.2 and the data-flow diagram show the same chain:

1. Colab run;
2. Drive export (weights, metrics, lineage);
3. operator download;
4. verified import;
5. MLflow.

Local MPS fine-tuning was considered and rejected because it adds a second training path.

### 7. Diagrams (D1–D3)

**Context.**

- Remove the template caption.
- The GIS-user arrows carry questions and cited answers from the assistant.

**Data flow.**

- Layers 1–3 have a training lane and an upload lane.
- The version point sits only on the training lane (raw manifest snapshot). The offline side holds the accepted dataset version (DVC commit).
- The quality gate checks grids, class IDs and new checksums for batches; size, format and 8-bit RGB for uploads.
- Layer 4 is an operator-started Colab run. The arrow from 4 to 5 is a dashed manual import.
- Monitoring receives input statistics, class shares and job metrics. The operator schedules the next labelled batch.
- Each card has a title and 2–3 short lines, at 16/14 px.

**Deployment.**

- The PostgreSQL card names RDS and OpenSearch Serverless.
- The monitoring card names CloudWatch and SageMaker Model Monitor.
- A legend marks these as reference equivalents and points to §6.2 for the selected deployment.
- Remove the template caption.

### 8. Supporting rationale: cloud operations (moved from §6.2)

§6.2 keeps the topology and one sentence on recovery. The scaling policy stays in §6.3. The details live here.

**NAT-free networking.**

- ECS tasks use `bridge` networking, so they share the host's public address. `awsvpc` tasks on EC2 get no public address.
- Persistent host firewall rules block container access to IMDS.
- Each task has its own IAM role.
- RDS accepts only the host security group.

**Job leases.**

- A claim sets an attempt ID and a lease expiry, and the worker sends heartbeats.
- A reconciler requeues expired leases, up to 3 attempts.
- Heartbeat and completion updates must match the current attempt ID and an unexpired lease; a rejected update stops the worker.
- Outputs go to an attempt-scoped S3 prefix. PostgreSQL atomically publishes the committed result pointer, so a stale worker cannot overwrite a retry.

**Ingress recovery.**

- A replacement core host associates the retained EIP at boot.
- It restores the proxy certificate and ACME account key from an encrypted backup, starts the pinned services and waits for readiness.
- Certificates renew through DNS-01, so port 80 stays closed.

Source: [cloud research §§3–4](../../../docs/research/cloud-deployment-cost.md) (local).

### 9. README and verification log

README holds:

- the §1 overview;
- Lab 1 status with a repository map;
- setup;
- the scorecard;
- one status paragraph that links [docs/verification.md](../../../docs/verification.md).

The log keeps the dated evidence:

- the 2026-10-22 clean copy;
- the `934858b` clean clone and hook test;
- the 2026-10-23 Mermaid render;
- the 2026-10-24 rewrite checks;
- the superseded $1,229.81 estimate.

It also records this change's checks. `934858b` is never presented as evidence for the current HEAD.

### 10. Calculator (items 7, 32)

The user saves the estimate from the archived [calculator inputs](../archive/2026-10-24-rewrite-lab1-design/calculator-inputs.md). The link then replaces the pending sentence in §6.7 and in README. The log compares the saved totals with $301.75 and $338.25.

## Risks / Trade-offs

- **Removing repeats strips context from a section** → keep a "(Section X)" reference wherever a fact is used.
- **The word target pushes out required content** → the Lab 1 structural checks gate the result; if the target is missed, report the count and what holds it.
- **The reference windows are untested** → mark them as assumptions; Lab 4 calibrates them.
- **The translation drifts from English** → translate after the English text stabilizes, then compare headings, numbers and links.
- **The estimate stays unsaved** → §6.7 keeps the pending status visible, task 3.3 stays open and the change is not archived.

## Migration Plan

1. English text.
2. SVGs.
3. README and verification log.
4. Ukrainian sync.
5. Checks.

Rollback restores the touched files.

## Closure map

| Review item | Closed by |
|---|---|
| G | Decision 1 |
| 6, 31 | Decisions 2–3 |
| 7, 32 | Decision 10 |
| 9 | Decision 4 |
| 17 | Decision 5 |
| 22, 23 | Decisions 6–7 |
| 24 | Decision 7 |
| 27 | Decisions 1 and 8 |
| 33 | Decision 2 |

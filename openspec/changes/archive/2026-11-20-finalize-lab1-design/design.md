# Design

## Context

Use the submitted design on `main` (reviewed at `582dfa9`) as the editing base. The English [course design](../../../../docs/design.md) carries the numbered sections that later labs revise. The four archived OpenSpec changes record earlier decisions. The single `lab-1.5` commit (`1dce9c9`) mixes corrections with a new GIS measurement product and a rented vision-language server. The [proposal](proposal.md) identifies the instructor feedback this revision addresses.

## Goals / Non-Goals

A reader should be able to follow a user request, explain who owns each action and predict the outcome of a bad upload, a dark image and a shifted batch. Keep the five-sentence overview, the OEM-8 QGIS export, FLAIR timeline, RF and U-Net/B4 candidate recognizable at the defense.

Lab 1 delivers contracts, diagrams and repository evidence. Physical measurements, road skeletons, a third model, a rented GPU and runtime implementation belong outside the change. The course path assumes zero additional paid spend and must be executable without a paid service or subscription.

## Decisions

### 1. Make the assistant a client of two existing course services

Use one example in §2 and put tool inputs and results in §6.8. A GIS user asks for their GeoTIFF mask and the meaning of 255. The assistant calls `predict` against the Lab 4 ML endpoint with an authorized image reference, then calls `retrieve` against the Lab 3 corpus for a cited explanation. The ML endpoint accepts a job, CPU workers segment, validate the grid and export the package. On success the user receives the actual model version and a result link with the upload's original expiry. A legend-only question needs one retrieval. A failed or expired job gets an explicit status. The normal upload route continues to work when chat is unavailable.

In §§4, 5.5, 6.4–6.5 describe the allowlist, ownership at submission and resume, and refusal of model promotion. Use four tool attempts as the initial budget. The combined example uses two and leaves two for transient errors. Count failed attempts, keep the budget across resume, and end on success, inability, refusal or exhaustion. The controller follows an accepted job without model-driven polling. A transport timeout with unknown submission outcome must be reconciled with the original request before retrying. Explicit user re-upload still creates a new job. Keep private imagery out of durable traces and use public fixtures for reviewable tool inputs and outputs. The [assistant spec](specs/gis-assistant/spec.md) gives the scenarios.

The four operations in the submitted §2 mix conversation with mandatory worker steps. The five GIS tools in `lab-1.5` add measurements and omit an explicit retrieval tool. Two project tools cover the course contract without requiring image reasoning.

### 2. Use the same brightness feature to explain an anomaly and a shift

In §6.6 define brightness as the mean of the three 8-bit channel values averaged over valid pixels, before normalization. Use one observation per source image. Build the reference from the training split for the corresponding dataset, preprocessing, taxonomy and immutable model version. Compute reference class fractions by running that model on those images. Compute current statistics on the same basis from actual endpoint traffic. Exclude padding, invalid pixels and tile overlap on both sides. Keep valid anomalous images in the population. Use only completed predictions for class fractions.

| Signal | Initial decision rule | Visible consequence |
|---|---|---|
| Invalid upload | Unsupported format, decode failure or zero valid pixels | Reject or fail the job with a reason. Count validation failures separately. |
| Per-image anomaly | Valid image brightness below the training reference's first percentile | Return a QA warning alongside the package. A dark but legitimate scene can trigger it. |
| Input drift | Daily report over a seven-day current window. Any monitored brightness or RGB-channel mean has PSI above 0.25 against frozen training bins | Record the feature, value, window, sample counts and versions. Email the operator. |
| Prediction drift | Absolute change above 10 percentage points in a class's mean per-image valid-pixel fraction against same-model reference predictions | Record the class and both values. Email the operator for review. |
| Suspected quality loss | Independent labelled controls are available | Evaluate per-class IoU and mIoU on eligible controls. The operator decides whether to investigate, block promotion or roll back. |

Use the existing minimum of 50 images per compared population as a starting assumption. Missing reference or undersampled current windows yield `insufficient_data`. Percentile, PSI and class-share thresholds are provisional. Lab 4 checks false alarms on unchanged held-out images, states the acceptable rate and the cost of missing a shift, and records the actual fraction and strength of the injected change. Use separate, reproducible replay windows with sufficient traffic: unmodified images, an individual darkened fixture for the QA warning, then a population with a documented fraction darkened. All requests go through the prediction endpoint. Record the scheduled reports, dashboard and received email. This replaces the production cold-start reference in §6.6 and aligns the evidence with the [monitoring spec](specs/segmentation-monitoring/spec.md).

### 3. Give each later lab one reproducible path

| Lab | Contract to describe in Lab 1 | Evidence produced in that later lab |
|---|---|---|
| 2 | A logical batch ID identifies a domain and frozen manifest. Reprocessing that ID succeeds and reuses or upserts the same rows. Discovery expecting new data can report stale input separately. Record the sample selection for sources over 200 MB, accessible retrieval command and checksum. Keep raw rasters in object storage. A feature-table row uses a tile key, raster reference, RGB-derived features and `feature_version`. | Same-interval row counts twice, deliberately failed quality gate and successful DAG. Fit the majority rule on valid training pixels and compare with the trained CPU RF on one leakage-free split. Count each valid source pixel once after stitching. Tag every run and registered version with DVC hash and Git SHA. Reproduce the CPU run with one documented command and a declared metric tolerance. B4 remains the neural candidate. |
| 3 | Use one retrieval configuration for evaluation and serving, versioned baseline/RAG prompts, prompt hashes in MLflow, and one command to rebuild the index and print its document count. Use the named corpus and section locators. | Compare plain and retrieved answers on ≥30 paraphrased questions, report hit@k, MRR and an answer metric at ≥3 settings of one parameter. Record resources or cost and p50/p95 across ≥10 calls. |
| 4 | Deploy separate ML and thin text-LLM services on Minikube with in-cluster MLflow, commit-tagged images, probes, configured endpoints and the same retrieval settings. ML readiness requires the model loaded by alias. Record safe inputs, predictions, timestamps and versions per request. | One-command startup and smoke prediction, missing-model readiness failure and a new reported version after alias change and restart. A scheduled drift job publishes metrics via Pushgateway, services expose metrics for scraping, and the dashboard shows two windows and a delivered alert. |
| 5 | Reuse the Lab 3 retriever and Lab 4 prediction endpoint. Trace every tool attempt in order with redacted inputs/results, time or tokens, cost and stop reason. Give local runs an explicit shadow price. | A versioned set of ≥10 tasks with pass criteria, including refusal, run at least twice. Report pass rate, mean steps and mean cost per run, explain differences and retain a trace that exhausts the budget. |

### 4. Keep one course design and a clearly hypothetical cloud estimate

Use local CPU training as the reviewer path and host-native text inference with a configurable model outside Minikube. The Mac's 24 GiB is a capacity constraint. Existing Colab access is an optional experiment path. The AWS equivalent and saved calculator link remain documentation for §6.7. Express its five calls as a workload allowance separate from the number of tool attempts. Keep totals only if the underlying pricing inputs stay the same. Do not make AWS, Bedrock, a paid notebook or an L4 a prerequisite for any graded demonstration.

Retain the existing three diagrams. In the data-flow view, show acceptance → queue → worker decode/tiling → prediction/export. Return the operator's new labelled batch to ingestion and its gate before training. Label retrieval and prediction where needed, preserving the seven ML layers and their version, quality and divergence marks. Restore the two Appendix 3 Lab 1 scorecard rows in the README. The [successful CI run for 582dfa9](https://github.com/zakhar-guzii/kse-mlops-project/actions/runs/40200242780) is evidence for that SHA. The final revision needs its own run after publication.

## Risks / Trade-offs

- Dark land cover or seasonal imagery can trigger a warning on a useful export → keep valid outputs available and show the reason.
- A model rollout can change predicted class shares on identical scenes → partition windows by immutable version and store matching reference predictions.
- Natural differences between OEM, FLAIR and user regions can trigger drift → report source mix, inspect the change and reserve quality judgments for labelled data.
- A small local model can miss a tool call or exceed available memory → use validated structured tool selection and evaluate a smaller local model if needed within the existing budget.

## Migration Plan

Apply the changes to the course documents from `main`, compare the worked example with the diagrams, then walk the planned evidence forward lab by lab. The documentation edits can be reverted independently of the historical archives. There is no runtime or data migration.

## Open Questions

Which revision the instructor recognizes as the submitted Lab 1 determines the eventual `lab-1` tag. This can be resolved at submission time independently of the design edits.

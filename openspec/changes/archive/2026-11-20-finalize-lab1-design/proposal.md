# Proposal

## Why

The submitted land-cover design lists assistant operations without showing how they solve a GIS user's task. It also leaves the operator without a clear way to distinguish a damaged upload, one unusual image and a shift across many predictions. Both questions came up in the Lab 1 review and affect how Labs 3–5 will be demonstrated.

## What Changes

- Use the existing OEM-8 segmentation and QGIS export to explain a bounded assistant with two tools: the Lab 3 document retriever and the Lab 4 prediction service. Specify ownership, asynchronous completion, refusal, stopping and trace evidence.
- Describe image validation, per-image anomaly warnings, input drift, prediction drift and labelled quality checks using the same imagery throughout. Anchor scheduled drift reports to the training data for the serving model version.
- Clarify the Lab 2 handoff: repeatable sampled batches, a versioned tile feature table, a majority-class rule alongside the existing CPU random forest, and evaluation on the stitched source grid. Connect the four milestones to evidence a reviewer can reproduce.
- Restore the two Lab 1 maturity rows and fix the data-flow arrows. Keep the course runnable with zero additional paid spend and identify the AWS estimate as a paper exercise.

## Capabilities

### New Capabilities

- `gis-assistant` — authorized document retrieval and asynchronous prediction with bounded tool use.
- `segmentation-monitoring` — image-level warnings, versioned drift comparisons and operator response.

### Modified Capabilities

None.

## Impact

Apply edits the English course design, README and affected diagram labels on the basis of `main`. The two capability deltas record intended behavior for later labs. Lab 1 acceptance consists of documents that agree on examples, contracts, assumptions and evidence. The four archived changes retain their historical decisions. Implementing services, training models, provisioning resources and publishing a submission tag belong outside this change.

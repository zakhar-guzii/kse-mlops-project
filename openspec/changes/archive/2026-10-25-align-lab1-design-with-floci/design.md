# Design

## Context

See [proposal.md](proposal.md) for motivation and scope. The repository contains Lab 1 documentation and development tooling, with no application or infrastructure implementation. There are no main capability specs; this documentation-only change declares `skip_specs: true`.

The current storage table in `docs/design.md` Section 5.2 and infrastructure table in Section 6.2 name pgsty/silo. The deployment SVG repeats that choice in its storage card and accessible description. The context and data-flow SVGs do not name a storage implementation. README distinguishes the design from later implementation, and `docs/design.uk.md` is an existing, ignored translation whose English source is authoritative.

## Goals / Non-Goals

**Goals:**

- Make the local S3 choice, its purpose and its limits understandable without an AWS tutorial.
- Keep the text, diagrams and local translation consistent while retaining the existing Lab 1 structure and visual style.

**Non-Goals:**

- Reassessing the cloud deployment, models, pricing or other local components.
- Treating documented emulator support as a successful integration test or prescribing runtime configuration files in this documentation change.

## Decisions

### 1. Rewrite affected passages, with one home for each explanation

Use short explanatory English paragraphs, familiar verbs and compact table cells. Explain what Floci does before naming SDK configuration. Retain section numbering and keep unrelated text intact; a full document rewrite would obscure this decision.

| Location | Intended revision |
|---|---|
| Section 5.2, storage table | Name Floci as the local S3 implementation. Keep DVC content hashes, MLflow metadata, corpus storage and temporary files distinct |
| Section 6.1, figure text | Match the revised deployment card and keep the distinction between managed equivalents and the selected cloud deployment |
| Section 6.2, infrastructure table and a short explanation | Select Floci for local S3 and explain portability, persistent local storage and the boundary of emulation once |
| Section 7.4, milestones | Assign S3 and DVC/MLflow compatibility checks to Lab 2; preserve the full Minikube deployment in Lab 4 |

A suitable wording direction is: "The course uses Floci to provide the S3 API locally. The application uses the same S3 operations locally and in AWS, with the endpoint and credentials configured for each environment." Follow it with the persistence requirement and the limits, using plain language rather than a list of environment variables.

### 2. Select Floci for S3 without expanding the architecture

Describe the same standard S3 client operations against a local endpoint or Amazon S3. Local configuration supplies the endpoint, region and test credentials; AWS uses its service endpoint and credentials from the assigned IAM role. DVC remote and MLflow artifact settings must also be checked when those components are implemented; do not imply that configuring Boto3 configures every tool.

Adopting only the S3 portion provides a concrete use for Floci now. Keep the PostgreSQL job queue, local per-user tokens, ignored local secrets file, host-native LLM, Colab exchange and selected cloud services as designed. The supported Floci APIs are a development aid; IAM behavior, networking, durability, scaling and model output still need validation in their target environments. Other Floci services, including a Bedrock proxy, remain outside this decision.

Keeping pgsty/silo could also support S3-compatible client code. Floci is chosen here because the author wants an AWS API development environment; this is a design choice rather than a claim of measured superiority. Replacing every local component with an emulator would expand the course architecture without a current need.

### 3. Keep storage and verification claims precise

Require persistent disk-backed local S3 storage. The stock image's memory default is unsuitable for keeping the project's data across restarts. Preserve the separation between datasets/model artifacts and temporary uploads/results. The temporary bucket remains unversioned, and Section 6.5 remains the home of the exact 24-hour access and deletion rules; lifecycle expiration alone does not demonstrate that guarantee.

Document future checks for upload/read/list/delete, a 128 MiB file, multipart archives, content integrity, signed URL access and expiry, and persistence after restart. Signed URL rejection checks must run with signature enforcement enabled; accepting an unchecked signature does not establish compatibility. Check endpoint reachability from the Mac and from Minikube when each environment is introduced. DVC pull/push and MLflow artifact operations belong to their Lab 2 integration checks, with real AWS permissions checked before migration.

These are planned checks, not tasks to execute in this documentation change. Do not add measured performance, memory figures or assertions that the integrations already work.

Use the release documentation already examined as the evidence baseline: [Floci 2.3.0 S3](https://github.com/floci-io/floci/blob/2.3.0/docs/services/s3.md#storage), [signature verification](https://github.com/floci-io/floci/blob/2.3.0/docs/services/s3.md#signature-verification) and [AWS endpoint configuration](https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html). Add only the links needed by the final prose; recheck the chosen runtime version when implementation begins.

### 4. Correct the existing views and reading aids

In `docs/diagrams/deployment.svg`, replace the storage card with a compact label such as "Floci (S3 API)" and retain the DVC remote. Update its `<desc>` to say the same. Keep Floci inside the planned Minikube boundary, the host-native LLM outside it and Colab outside the Mac. Preserve Amazon S3 as the cloud storage and the legend explaining managed equivalents. No new Compose deployment is introduced by this design.

Review all three SVGs and the Section 6.1 captions/alt text together. The context actors and seven-layer data flow remain valid; retain them unless an affected label needs a correction. Render all three for visual inspection so a shorter diff does not hide a clipped or misleading label.

Keep README's Lab 1 status and setup instructions accurate. Add a short planned-design note only if needed to reconcile its description; do not add Floci startup commands. Synchronize only affected passages in the existing Ukrainian translation, retaining its disclaimer and ignored status. A clean clone without that local translation does not need a new one. Do not edit archived proposals or historical mentions of the former storage choice.

## Risks / Trade-offs

- Emulation is mistaken for complete AWS equivalence -> State the selected S3 boundary and the remaining AWS-specific validation explicitly.
- The design sounds implemented -> Keep compatibility checks in future tense and preserve the README and lab milestones' status.
- A new storage name obscures retention or security requirements -> Retain Section 6.5 and distinguish disk persistence, signature checks and application authorization.
- Text or diagrams drift during editing -> Check the affected tables, SVG labels/descriptions, captions and translation together; render the three SVGs before completion.

## Migration Plan

Apply the English document edits, align the diagrams and reading aids, then complete the document checks in `tasks.md`. No resource deployment or data migration occurs. Reverting the affected document edits restores the previous design; historical OpenSpec artifacts remain intact.

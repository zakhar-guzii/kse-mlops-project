# Proposal

## Why

Review round 2 found that 12 of the 36 round-1 items (G + 1–35) are only partly closed. Monitoring has no reference window. The size, deadline and mask wording contradicts itself. Two diagram boundaries mislead. The calculator estimate is not saved. Repetition grew the design by 19%. This change closes these items and states each fact once.

## What Changes

- Tighten `docs/design.md` so each fact appears once, in the section it belongs to. Target: at most 6,763 words (8,062 now), the length before round 1.
- Fix the contradictions. Uploads may have different sizes within the stated bounds. Results stay available until `accepted_at` + 24 h. User uploads have no reference masks.
- Define the drift reference windows, the NAIP scope and links to the alternative models' published weights. Add one sentence on stale-attempt fencing and certificate recovery.
- Keep all neural training in Colab Pro. The data-flow diagram shows the operator-started run, the manual import, and that versioning and freshness apply only to training batches.
- Fix the deployment diagram's managed-equivalent labels and remove template captions.
- Reduce README to an overview, a repository map, setup and status. Move the dated verification history to a new `docs/verification.md`.
- Synchronize the Ukrainian translation and apply the round-2 wording fixes.

Training, runtime code, cloud resources and paid calls are out of scope. Saving the AWS Pricing Calculator estimate creates a public link, so the user does it; until then §6.7 says the estimate is pending.

## Capabilities

### New Capabilities

None. This is a documentation-only change, so `skip_specs: true` is set.

### Modified Capabilities

None.

## Impact

- Files: `docs/design.md`, `docs/design.uk.md` (local, ignored), `docs/diagrams/*.svg`, `README.md`, new `docs/verification.md`.
- No code, dependency, CI or configuration changes.
- Sources (local, ignored): [round-2 review](../../../docs/reviews/design-round-2.md), [closure matrix](../../../docs/reviews/design-round-2-closure.md) and [Lab 1](../../../labs/lab-1.pdf).
- Prior change: [rewrite-lab1-design](../archive/2026-10-24-rewrite-lab1-design/design.md), with its [calculator inputs](../archive/2026-10-24-rewrite-lab1-design/calculator-inputs.md).

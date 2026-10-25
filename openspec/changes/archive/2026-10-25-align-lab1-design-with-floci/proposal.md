# Proposal

## Why

The author wants to develop against AWS APIs locally before moving the service to AWS. Lab 1 currently selects pgsty/silo for local object storage; the design and diagrams need to explain the proposed switch to Floci and the limits of that emulation in the document's existing clear style.

## What Changes

- Revise the affected passages in `docs/design.md`, keeping its English, section structure, short explanations and compact tables. Explain Floci once in Section 6.2 and refer to that explanation elsewhere.
- Select Floci for the local S3 API in the storage and infrastructure tables. Describe shared S3 client operations, environment-specific configuration and persistent local storage without promising an automatic migration of the whole system.
- Define the checks planned for Lab 2: S3 operations, large-file transfers, signed URLs, restart persistence and DVC/MLflow compatibility. Keep their status explicitly unverified.
- Correct the deployment diagram's storage label and accessible description. Review all three diagrams, their captions and README for consistency; change only affected content.
- Synchronize the affected passages of the existing, ignored Ukrainian translation as a local reading aid. English remains authoritative and ignore rules stay unchanged.

This change updates documentation only. Running Floci, installing dependencies, writing application or infrastructure code, provisioning AWS resources and adopting additional emulated AWS services are out of scope.

## Capabilities

### New Capabilities

None. This change documents a planned infrastructure choice without adding application behavior; `.openspec.yaml` declares `skip_specs: true`.

### Modified Capabilities

None. There are no existing main specs, and this change does not introduce a runtime contract.

## Impact

- Required edits: `docs/design.md`, `docs/diagrams/deployment.svg` and the affected passages of the existing local `docs/design.uk.md` translation.
- Consistency review: `README.md`, `docs/diagrams/context.svg`, `docs/diagrams/data-flow.svg` and the figure text in Section 6.1. Edit these only where the revised explanation requires it.
- Preserve the selected cloud deployment, PostgreSQL queue, Minikube course constraint, local identity and LLM, training exchange, privacy rules, cost assumptions and lab sequence.
- No changes to runtime code, dependencies, setup commands, CI, ignore rules or archived OpenSpec changes.

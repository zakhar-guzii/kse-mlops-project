# Proposal

## Why

The current Lab 1 design has the required structure, but its single-user architecture, teacher-dependent NAIP updates, model choices and cloud estimate conflict with the review and the user's subsequent decisions. Rewrite it from the validated research into a concise working document whose data, evaluation, diagrams, resource assumptions and costs agree.

## What Changes

- Rewrite `docs/design.md` and synchronize `docs/design.uk.md`, preserving the lab's 22 numbered sections, seven NFR categories, three diagram views and minimal required placeholders/milestones.
- Use OEM-8, a CPU random forest baseline, SMP U-Net/EfficientNet-B4, supervised chronological FLAIR-HUB updates and separate development/final controls. Unlabelled inputs support inference/monitoring. Compare FT-UNetFormer and Satlas as alternatives to revisit after implementation.
- Explain both promotion policies with hypothetical examples: the selected policy retains OEM mean accuracy and permits at most a two-percentage-point per-class drop while improving regional accuracy; the strict alternative permits no per-class drop. The operator approves and activates the model in either case.
- Describe the confirmed local Gemma/Metal and cloud Bedrock Sonnet choices, Sol as an alternative without automatic failover, owned Colab Pro, and MLflow as authoritative. Explain optional W&B curves without making them a required dependency.
- Describe authenticated multi-user asynchronous inference with scalable CPU workers, continuous recoverable ECS/EC2 operation, RDS and proxy/EIP ingress. Use 24-hour private-upload retention, no first-version feedback training, compact monitoring and a recalculated cloud estimate.
- Replace Mermaid blocks with three shared SVG assets. Align README's mirrored overview/current-design references and distinguish its historical verification from the revised document.

This change delivers documentation and diagrams. Runtime implementation, model/data downloads, training, cloud deployment, paid calls, automatic provider failover, HA and user-feedback ingestion are outside its scope. A replacement public calculator estimate requires separate approval after its exact inputs are reviewable.

## Capabilities

### New Capabilities

None. This documentation-only change sets `skip_specs: true`; it does not introduce runtime behavior or invent a documentation capability solely for validation.

### Modified Capabilities

None. The main OpenSpec capability inventory is empty. Runtime specifications belong to the corresponding later implementation changes.

## Impact

- Intended implementation files: `docs/design.md`, `docs/design.uk.md`, three SVGs under `docs/diagrams/`, and narrowly related README text.
- Planning artifacts: this change's proposal, design and tasks. The design records accepted choices, section/review coverage, calculation inputs and acceptance checks.
- No application code, dependency, environment, CI, database or API changes. Existing research/reviews and the user's `.gitignore`/archive changes remain source context.
- English remains canonical; the Ukrainian document uses the same decisions, numbers, sources and SVGs. Direct primary-source links keep the tracked design intelligible without the ignored research directory.

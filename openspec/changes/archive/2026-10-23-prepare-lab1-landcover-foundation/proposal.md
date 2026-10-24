# Proposal

## Why

The agreed course project should help a GIS specialist obtain a multiclass land-cover map from an overhead image and fine-tune the model on new data batches over time. At the start of this change, the repository contained the Lab 1 assignment and an initial Python environment, but lacked the design document, README with a scorecard, and reproducible lint setup required for submission.

## What Changes

- Prepare `docs/design.md` with the exact Lab 1 structure, three consistent diagrams, sources, and a clear distinction between observed facts, agreed decisions, new assumptions, and unmeasured properties.
- Describe the OEM taxonomy, Utah NAIP 2018/2021 updates and final 2024 evaluation, control-set independence, pseudo-mask provenance, freshness/idempotency, training/serving contracts, and reproducible fine-tuning with a manually started Colab session.
- Document local inference, a minimal web interface, DVC/S3-compatible storage, Airflow, MLflow, PostgreSQL, a GIS assistant, email monitoring, and the Labs 2–5 roadmap.
- Identify a concrete retrieval corpus and managed cloud equivalents; document a saved AWS Calculator estimate for a full-cloud workload with explicit capacity/usage assumptions, including GPU model work and LLM/embedding costing proxies.
- Prepare a README with five sentences about the problem and two Lab 1 scorecard rows; add a pinned development environment, Makefile `setup`/`lint` targets, pre-commit using the same linter, and lint CI.
- Include clean-clone setup/lint verification, document/diagram consistency checks, defense preparation, and a submission checklist.

This change covers Lab 1 documentation and tooling. Training, large dataset downloads, inference/UI, Airflow DAGs, corpus ingestion, containers, Minikube, email delivery, and the LLM/agent are described as later stages and are not implemented by this change. The actual budget remains $0; no paid resources are created.

## Capabilities

### New Capabilities

There are no runtime behavior changes: this change provides documentation and repository tooling. `.openspec.yaml` sets `skip_specs: true`; behavioral specifications for future services should accompany the corresponding Labs 2–5 changes.

### Modified Capabilities

None. The `openspec list --specs --json` check found no existing capability specifications.

## Impact

- Planning artifacts reside in `openspec/changes/prepare-lab1-landcover-foundation/`.
- Implementation updates `README.md`, creates `docs/design.md`, `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/lint.yml`, and `.python-version`, and updates `pyproject.toml`/`uv.lock` only for minimal development tooling. The calculator estimate is recorded in the design as a link with a date and inputs; separate research files are not restored.
- Runtime ML/MLOps dependencies are not installed during Lab 1. This change does not modify system Python, Docker, Minikube, or machine configuration.
- Git commit/push, green CI on the default branch, and the submission tag `lab-1` are separate submission steps; creating the proposal does not perform them.
- Risks include unverified pretrained annotator provenance, the absence of independent temporal NAIP ground truth, unverified individual tiles, compatibility of future ML dependencies, and unbenchmarked capacity behind the saved cloud estimate.

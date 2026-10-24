# KSE MLOps: Land-cover segmentation

GIS specialists need a first thematic land-cover layer for new overhead imagery, which they then check and edit into a map. The system accepts an RGB aerial image of arbitrary size and returns an eight-class OpenEarthMap (OEM) mask with a colour overlay, a legend and, for georeferenced GeoTIFF input, a GeoTIFF layer on the source grid. Many users can submit images at once: an authenticated API queues each upload as a job, and CPU workers scale with the queue. The model is trained on OEM and then fine-tuned on new expert-labelled batches in acquisition-year order; an operator reviews each candidate and approves it before it serves. The desired outcome is GIS exports that open without manual repair, and model updates that are reproducible, monitored and reversible.

## Lab 1 status

The [system design](docs/design.md) describes the GIS service, its supervised model updates and the roadmap for later labs, with three diagrams in [docs/diagrams/](docs/diagrams/). Lab 1 provides documentation and reproducible development tooling. Repository documentation, code, comments, and OpenSpec artifacts use English; the English design is authoritative. A Ukrainian translation (`docs/design.uk.md`) and the course PDF (`labs/lab-1.pdf`) are kept locally and are not tracked, so they are absent from a clean clone.

## Local setup

Prerequisites: Git, Make, and uv 0.11.21 in PATH. The project uses Python 3.12.13 from `.python-version` and dependencies pinned in `uv.lock`. uv can obtain a missing project interpreter without replacing the system Python. Initial setup needs network access for missing packages or the interpreter.

```sh
make setup
make lint
uv run --locked pre-commit run --all-files
```

`make setup` installs the locked development environment. `make lint` runs Ruff static checks without modifying files. The pre-commit configuration runs the same locked Ruff command and is retained for Lab 1 and manual checks. Automatic local Git hooks are not installed.

The [lint workflow](.github/workflows/lint.yml) runs `make setup` and `make lint` on GitHub for every push and pull request. Application code will be added in later labs; currently these commands verify the development configuration and tool invocation.

## Maturity scorecard

| Property | Evidence a reviewer checks | Added in |
|---|---|---|
| Repository reproducible from a clean clone | Published commit `934858b` passed setup, lint, pre-commit, and lock checks in a genuine clean clone; its [lab1 push CI passed](https://github.com/zakhar-guzii/kse-mlops-project/actions/runs/39848904192). Green default-branch CI remains a submission gate | Lab 1 |
| Design document exists and is current | [docs/design.md](docs/design.md): sections 1–7.4, explicit assumptions, three SVG diagrams, and a recalculated cloud estimate in section 6.7; the replacement AWS Calculator link is pending | Lab 1 |

## Verification and submission

- On 2026-10-22, a clean temporary copy passed `make setup`, `make lint`, pre-commit configuration validation and all-file execution, and `uv lock --check`, using Python 3.12.13, Ruff 0.17.2, and pre-commit 4.7.0. These checks did not modify source files; this was a local copy, not a remote clone.
- A subsequent genuine clone of published commit `934858b` passed the same checks. A temporary Python error caused lint/pre-commit to fail and an installed test hook to block a commit; corrected code passed. The test hook and probe commits existed only in the temporary clone; automatic hooks in the working repository are disabled.
- On 2026-10-23, the three Mermaid diagrams of the earlier design version rendered successfully and were visually checked, and local documentation links were checked. The revised design replaces them with SVG files.
- On 2026-10-24, the revised design passed document checks: 22 numbered sections in English and in the local Ukrainian translation, resolving local links, the three SVG diagrams rendered at document width in headless Chrome and inspected visually, independently recomputed cost tables, `openspec validate rewrite-lab1-design --strict`, and `make lint`.
- The [saved AWS Calculator estimate](https://calculator.aws/#/estimate?id=52dedcbc1a8747f5028990e050593d9dab6c4ac1), verified on 2026-10-23 (Europe/Kyiv), is $1,229.81/month and $0 upfront for the superseded EKS/MWAA design; it does not price the revised design. Actual paid expenditure remains $0.
- Publication, green CI on the default branch, verification of the published commit in a clean clone, and the `lab-1` tag remain separate submission steps.

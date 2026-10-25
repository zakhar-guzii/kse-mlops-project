# KSE MLOps: Land-cover segmentation

GIS specialists need a first land-cover layer for new aerial imagery, which they then check and edit in QGIS. The service turns an 8-bit RGB aerial image into an eight-class OpenEarthMap (OEM) mask with a colour overlay, a legend and, for a georeferenced GeoTIFF, a GeoTIFF layer on the source grid. Authenticated users submit images of different sizes, within fixed upload limits, as asynchronous jobs, and CPU workers scale with the queue. The model is trained on OEM and fine-tuned on expert-labelled batches in acquisition-year order; an operator approves each new version before it serves. The desired outcome is GIS exports that open without manual repair, and model updates that are reproducible, monitored and reversible.

## Lab 1 status

Lab 1 delivers the system design and reproducible development tooling. Documentation, code and OpenSpec artifacts are in English, and the English design is authoritative. A Ukrainian translation (`docs/design.uk.md`) and the course PDF (`labs/lab-1.pdf`) are kept only locally and are absent from a clean clone.

| Path | Contents |
|---|---|
| [docs/design.md](docs/design.md) | The intended service, sections 1–7.4 |
| [docs/diagrams/](docs/diagrams/) | Context, data-flow and deployment views |
| [docs/verification.md](docs/verification.md) | Dated verification log |
| [openspec/](openspec/) | Change proposals and acceptance criteria |
| `pyproject.toml`, `uv.lock`, `Makefile`, `.pre-commit-config.yaml`, [.github/workflows/lint.yml](.github/workflows/lint.yml) | Reproducible setup, lint and CI |

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
| Repository reproducible from a clean clone | Published commit `934858b` (2026-10-22) passed setup, lint, pre-commit and lock checks in a genuine clean clone; its [lab1 push CI passed](https://github.com/zakhar-guzii/kse-mlops-project/actions/runs/39848904192). The submitted commit is checked again at submission | Lab 1 |
| Design document exists and is current | [docs/design.md](docs/design.md): sections 1–7.4, explicit assumptions, three SVG diagrams and a recalculated cloud estimate in section 6.7; the AWS Pricing Calculator link is pending | Lab 1 |

## Submission status

The latest document checks are in the [verification log](docs/verification.md). Remaining steps: the saved AWS Pricing Calculator estimate, publication, green CI on the default branch, a clean-clone check of the submitted commit, and the `lab-1` tag.

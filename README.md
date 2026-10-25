# KSE MLOps: Land-cover segmentation

GIS specialists need a first land-cover layer for new aerial imagery, which they then check and edit in QGIS. The service turns an 8-bit RGB aerial image into an eight-class OpenEarthMap (OEM) mask with a colour overlay, a legend and, for a georeferenced GeoTIFF, a GeoTIFF layer on the source grid. Authenticated users submit images of different sizes, within fixed upload limits, as asynchronous jobs, and CPU workers scale with the queue. The model is trained on OEM and fine-tuned on expert-labelled batches in acquisition-year order; an operator approves each new version before it serves. The desired outcome is GIS exports that open without manual repair, and model updates that are reproducible, monitored and reversible.

## Lab 1 status

Lab 1 delivers the system design and reproducible development tooling. Documentation, code and OpenSpec artifacts are in English, and the English design is authoritative.

| Path | Contents |
|---|---|
| [docs/design.md](docs/design.md) | The intended service, sections 1–7.4 |
| [docs/diagrams/](docs/diagrams/) | Context, data-flow and deployment views |
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

The [lint workflow](.github/workflows/lint.yml) runs `make setup` and `make lint` on GitHub for every push and pull request. Application code will be added in later labs;

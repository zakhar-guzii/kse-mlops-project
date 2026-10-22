# KSE MLOps: Land-cover segmentation

A GIS specialist needs an initial thematic land-cover map from an overhead image. The system accepts RGB images of different sizes and returns an eight-class OpenEarthMap pixel mask, a color visualization, an overlay, and a legend. For GeoTIFF input with usable georeferencing, it also produces a georeferenced raster layer. New explicitly defined data batches pass validation, automatic annotation, continual fine-tuning from the current approved model, and evaluation before a person approves activation. The course project aims to make GIS delivery and model updates reproducible, integrated, and observable.

## Lab 1 status

The [system design](docs/design.md) describes the GIS workflow and the roadmap for later labs. Lab 1 provides documentation and reproducible development tooling. Repository documentation, code, comments, and OpenSpec artifacts use English.

## Local setup

Prerequisites: Git, Make, and uv 0.11.21 in PATH. The project uses Python 3.12.13 from `.python-version` and dependencies pinned in `uv.lock`. uv can obtain a missing project interpreter without replacing the system Python. Initial setup needs network access for missing packages or the interpreter.

```sh
make setup
make lint
uv run --locked pre-commit run --all-files
```

`make setup` installs the locked development environment. `make lint` runs Ruff static checks without modifying files. pre-commit runs the same locked Ruff command. Install local Git hooks manually, if wanted, with `uv run --locked pre-commit install`.

The [lint workflow](.github/workflows/lint.yml) runs `make setup` and `make lint` on GitHub for every push and pull request. Application code will be added in later labs; currently these commands verify the development configuration and tool invocation.

## Maturity scorecard

| Property | Evidence a reviewer checks | Added in |
|---|---|---|
| Repository reproducible from a clean clone | Setup, lint, pre-commit, and lock checks passed in a clean temporary copy on 2026-10-22. Remote clean-clone verification and green default-branch CI await publication; see the [lint workflow](.github/workflows/lint.yml) | Lab 1 |
| Design document exists and is current | [docs/design.md](docs/design.md): sections 1–7.4, explicit assumptions, and three diagrams. The calculator gate in section 6.7 remains open | Lab 1 |

## Verification and submission

- On 2026-10-22, a clean temporary copy passed `make setup`, `make lint`, pre-commit configuration validation and all-file execution, and `uv lock --check`, using Python 3.12.13, Ruff 0.17.2, and pre-commit 4.7.0. These checks did not modify source files; this was a local copy, not a remote clone.
- All three Mermaid diagrams rendered successfully and were visually checked; local documentation links were checked.
- The cloud estimate is preliminary tariff arithmetic; no provider calculator estimate has been obtained.
- Publication, green CI on the default branch, verification of the published commit in a clean clone, and the `lab-1` tag remain separate submission steps.

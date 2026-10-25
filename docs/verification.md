# Verification log

Dated evidence for the Lab 1 repository, newest first. An entry proves only the state it names.

## 2026-10-25 — refine-lab1-design

Pending: the document checks of this change are recorded here when they run.

## 2026-10-24 — rewrite-lab1-design

The rewritten design passed document checks: 22 numbered sections in English and in the local Ukrainian translation, resolving local links, the three SVG diagrams rendered at document width in headless Chrome and inspected visually, independently recomputed cost tables, `openspec validate rewrite-lab1-design --strict` and `make lint`.

## 2026-10-23 — earlier design version

- The three Mermaid diagrams of the earlier design rendered and were checked visually, and local documentation links were checked. SVG files replaced the Mermaid diagrams on 2026-10-24.
- The saved [AWS Calculator estimate](https://calculator.aws/#/estimate?id=52dedcbc1a8747f5028990e050593d9dab6c4ac1), verified on 2026-10-23 (Europe/Kyiv), was $1,229.81/month and $0 upfront. It priced the superseded EKS, MWAA and legacy managed MLflow design, not the current one.

## 2026-10-22 — repository tooling

- A clean temporary copy passed `make setup`, `make lint`, pre-commit configuration validation and all-file execution, and `uv lock --check`, with Python 3.12.13, Ruff 0.17.2 and pre-commit 4.7.0. The checks modified no source files. This was a local copy, not a remote clone.
- A later genuine clone of published commit `934858b` passed the same checks. A temporary Python error made lint and pre-commit fail and an installed test hook block a commit; the corrected code passed. The test hook and probe commits existed only in the temporary clone; the working repository has no automatic hooks.

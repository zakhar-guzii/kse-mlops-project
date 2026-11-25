# Proposal

## Why

Lab 3 (step 4) requires an ingestion path from the project's corpus to a vector index that a reviewer rebuilds with one command, which prints the document count that the README states. The design names the corpus and a planned `make retrieval-index`, but the repository holds no corpus, no index and no PostgreSQL image that can store vectors.

This is the first of several consecutive Lab 3 changes. It builds the corpus and the index only. The query path, the prompts, the LLM baseline, the evaluation set and its metrics, cost and latency, the scorecard rows and the `lab-3` tag come later, and nothing here chooses a text model.

## What Changes

- Add the retrieval corpus to Git: cleaned Markdown copies of the four external sources (the OpenEarthMap paper, the FLAIR-HUB paper with its label configuration, the USGS NAIP data dictionary, the QGIS raster properties page) and a manifest that records each copy's source URL, access date and SHA-256. The fifth document, `export-contract`, is read from Sections 5.1 and 6.8 of `docs/design.md` when the index is built, so it has no copy.
- Add one retrieval configuration file holding the chunk size, the overlap, the embedding model with its pinned revision, and top-k.
- Add `make retrieval-index`: it checks the copies against the manifest, splits every document into section-bounded chunks, embeds them locally on the CPU, replaces the index in PostgreSQL, checks one fixed question against it and prints the document and chunk counts with the index version.
- Replace the PostgreSQL image with the pgvector build of the same PostgreSQL 16 and the same Debian release, and publish the server on `127.0.0.1:5433`. The existing volume, with the Lab 2 rows and MLflow runs, is kept.
- Add a dependency group for the embedding library. `make setup` installs nothing new.
- Add the Lab 3 retrieval section to the README: the command, its output, the document count, the configuration file and the size of the model downloaded on the first run.
- Revise `docs/design.md` so that it describes what is built: Section 5.1 (the LLM component's job and its corpus), Section 5.2 (corpus table, storage row, configuration), a retrieval pipeline diagram in Section 6.1, and the pgvector and embedding rows and paragraph of Section 6.2, with the matching labels in `docs/diagrams/deployment.svg`.

Decisions settled with the author, each replacing a statement of the current design:

| Topic | Current design | This change |
|---|---|---|
| Where the saved copies live | Object storage locally, S3 in the cloud | Git, for the course: the sources have no immutable address, so a reviewer cannot refill a store from them; S3 stays the cloud description |
| Form of a saved copy | Not stated ("pages and PDFs") | Cleaned Markdown without navigation and reference lists; licences are not checked, the manifest keeps the source URL |
| `export-contract` | A saved copy like the others | Read from the design document at build time |
| Embedding model and runtime | Qwen3-Embedding-0.6B in a host-native llama-server | `intfloat/multilingual-e5-small` in process on the CPU, because the query is embedded inside the Lab 4 service and the lab budgets under 1 GB for it |
| Chunking | Not stated | 600 characters with 100 of overlap, never across a section boundary |
| PostgreSQL image | `postgres:16` | `pgvector/pgvector:0.8.7-pg16-trixie` |

## Capabilities

### New Capabilities

- `retrieval-index`: the committed corpus and its manifest, document versions, section-bounded chunking, the single retrieval configuration, the one-command rebuild with its printed counts, the index version and the build's self-check.

### Modified Capabilities

None. `gis-assistant` already requires answers from "the evaluated project retriever" with a source locator; this change supplies the index underneath it and changes none of its requirements.

## Impact

- New code and configuration: `corpus/` (four Markdown copies and `manifest.toml`), `retrieval.toml`, `src/landcover/retrieval.py`, `tests/test_retrieval.py`.
- Changed tooling: `docker-compose.yml` (image and port of `postgres`), `pyproject.toml` and `uv.lock` (group `rag`), `Makefile` (target `retrieval-index`), `.github/workflows/lint.yml` (the service image, so the index test has the extension).
- Changed documents: `README.md`, `docs/design.md` (Sections 5.1, 5.2, 6.1, 6.2 and the corpus row of 6.8), `docs/diagrams/deployment.svg`, and the affected passages of the local, ignored `docs/design.uk.md` if it exists.
- Running stack: the `postgres` container is recreated once on its existing volume. MLflow and Airflow are unavailable for the restart.
- External systems: Hugging Face is read on the first index build to download the embedding model (471 MB). The four sources are read once, by the author, when the copies are made. No paid service is added.
- Out of scope: a `retrieve` interface and the query path, prompt files, the LLM baseline run, the evaluation set, hit rate, MRR and the answer metric, the parameter sweep, cost and latency, Sections 5.3, 5.4, 6.3, 6.7, 7.1 and 7.2, the scorecard rows and the `lab-3` tag.

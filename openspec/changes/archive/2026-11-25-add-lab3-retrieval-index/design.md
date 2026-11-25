# Design

## Context

See [proposal.md](proposal.md) for motivation, scope and the decisions settled with the author. Section numbers without a file name refer to `docs/design.md`.

Facts checked for this design on 2026-11-23:

- The running `postgres:16` container is PostgreSQL 16.16 on Debian 13 (trixie); every database reports collation version 2.41. Its volume holds 96 rows in `dwh.tiles`, the `mlflow` database with the Lab 2 runs and registered versions, and the `airflow` database.
- On Docker Hub, `pgvector/pgvector:pg16` is the same image as `pg16-bookworm`. `pgvector/pgvector:0.8.7-pg16-trixie` exists for arm64 and amd64, and 0.8.7 is the version in the lab's reference table.
- `postgres` publishes no host port, and port 5432 on the course Mac is held by another project's container. `sql/warehouse.sql` runs only when the volume is empty.
- Two fetches of each source gave identical bytes, but the QGIS page carries a build stamp ("Last updated on 2026 Oct 30"), the USGS page is rendered by a content-management system and the arXiv HTML is generated from the paper's source. None has an address that pins its bytes, unlike the Hugging Face commit of Lab 2.
- Extracted text: OpenEarthMap paper 11,613 words including its supplement S1 with the class definitions; FLAIR-HUB paper 22,958 words; QGIS page 6,928 words; USGS page 1,495 words, about half of it site navigation; Sections 5.1 and 6.8 about 900 words. The FLAIR-HUB label configuration is 2 KB of YAML.
- `intfloat/multilingual-e5-small`: 118 M parameters, 471 MB of weights, 384 dimensions, inputs truncated at 512 tokens, MIT licence, not gated, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. The model expects the prefix `passage: ` on indexed text and `query: ` on questions.
- Adding `sentence-transformers` to a copy of `pyproject.toml` resolved to 6.3.0 with transformers 5.24.0 and left every existing pin unchanged, including torch 2.15.0 and huggingface-hub 2.4.0.
- CI runs the warehouse test against a `postgres:16` service through `TEST_DSN`.
- `docs/diagrams/deployment.svg` names Qwen3-Embedding-0.6B and host-native embeddings. The local, ignored `docs/design.uk.md` exists.

## Goals / Non-Goals

**Goals:**

- A reviewer with the stack up runs one `make` target and gets the index, with no network access except the first model download.
- Chunking, hashing and section parsing are plain functions testable without a database or a model.
- The Lab 2 volume survives the image change.
- The smallest set of files: one module, one configuration file, one manifest, four copies, one test file.

**Non-Goals:**

- A `retrieve` interface, prompts, the text model, evaluation and its metrics.
- A script that fetches or converts the sources, DVC tracking of the corpus, raw HTML or PDF copies.
- An approximate-nearest-neighbour index, several index versions side by side, a migration tool, changes to `sql/warehouse.sql`.
- Embedding through an HTTP server, a container for the index build, GPU or MPS inference.

## Decisions

### 1. The corpus is Markdown in Git, with a manifest

`corpus/` holds one Markdown file per external document and `manifest.toml`:

| `doc_id` | File | Content of the copy |
|---|---|---|
| `oem-paper` | `corpus/oem-paper.md` | Paper body and supplement S1–S5 from the arXiv HTML |
| `flair-hub` | `corpus/flair-hub.md` | Paper body from the arXiv HTML v1, followed by one section with the label configuration as a fenced YAML block |
| `naip-dictionary` | `corpus/naip-dictionary.md` | The data dictionary |
| `qgis-raster` | `corpus/qgis-raster.md` | The raster properties chapter |
| `export-contract` | none | Sections 5.1 and 6.8, read from `docs/design.md` (Decision 2) |

A copy keeps the source's headings as Markdown headings and its tables as Markdown tables. It drops site navigation, figures, formulas that do not survive as text, acknowledgements and reference lists; a reference list is thousands of words that match every question about its topic and answer none. Each manifest entry has `doc_id`, `title`, `file`, `urls`, `accessed` and `sha256`. The entry of `export-contract` has `file = "docs/design.md"` and `sections` instead of `urls`, `accessed` and `sha256`. The label configuration URL names a Git commit, not `main`.

The copies are made once, by hand during this change, and reviewed by the author. The manifest's SHA-256 is of the committed file, so it proves that a copy was not edited afterwards, not that it equals the source.

Alternatives considered: a fetch script checked against committed hashes, as in Lab 2, fails for every reader on the day a source page is rebuilt. Tracking the copies with DVC does not help, because a reader with an empty store cannot refill it from a source that has changed. Raw HTML copies would keep the source bytes but need a separate extractor for each of four page layouts inside the build.

### 2. `export-contract` is read from the design document

The build takes each section named in the manifest from `docs/design.md`: the text from a `## <number> ` heading up to the next `## ` heading. A missing section stops the build. A copy of the repository's own file would be a second version of the class table that drifts from the first.

Its chunk count therefore changes when Section 5.1 or 6.8 is edited. The README states the document count, which does not.

### 3. `doc_version` is a content hash

`doc_version` is the first 12 hexadecimal digits of the SHA-256 of the document's indexed text: the copy for an external document, the extracted sections for `export-contract`. A version that is derived cannot be forgotten when a copy is replaced. The build first compares each copy's full SHA-256 with the manifest and stops on a difference.

Alternative considered: an integer the author raises by hand. It reads better in a citation and is wrong the first time someone forgets it.

### 4. Chunks: 600 characters, 100 of overlap, inside one section

A document is split at Markdown heading lines outside fenced blocks. A section's locator is its heading path joined with ` > `, for example `5.1 Problem statement`; text before the first heading takes the document title. Within a section a window of `chunk_size` characters moves forward so that consecutive chunks share `chunk_overlap` characters; a window ends at a line break when one lies in its last third, otherwise at whitespace. A section shorter than the window is one chunk.

Sizes are in characters, so chunk boundaries do not depend on a tokenizer and a later change of the embedding model alters one thing. 600 characters is about 150 tokens of prose and at most about 225 for dense tables, well under the model's 512. The answers this corpus holds are small facts (a class ID, the meaning of 255), which favours small chunks; the committed corpus gives about 570 chunks. These two values are a starting point: the evaluation of a later change measures them.

The first choice, 1,200 characters with 200 of overlap (309 chunks), failed the self-check of Decision 9 during implementation: `multilingual-e5-small` ranked the chunk of Section 5.1, which holds the definition of 255 together with the whole class table, 21st for the fixed question. Measured with the same model, 800/150 ranked it 5th, exactly at `top_k`, and 600/100 ranked it 1st. The author chose 600/100.

A chunk never crosses a section, so an evaluation question can name its expected source as `doc_id` and locator. Labels of that form survive a change of chunk size; chunk numbers would not.

### 5. Embeddings: `multilingual-e5-small`, in process, on the CPU

The build loads the model with `sentence-transformers` at the configured revision on the CPU and embeds `passage: <locator>\n<chunk text>` with normalised output. The locator is included so that later chunks of a long section keep their heading. The stored text is the chunk alone.

The function that builds the index takes the embedding function as an argument. The command passes the real model; the test passes a stub, so CI needs neither the 471 MB download nor torch.

The dependency is `sentence-transformers==6.3.0` in a new group `rag`. `make setup` does not install it; the `retrieval-index` target runs with `--group rag`, as the U-Net targets run with `--group nn`.

Alternatives considered: Qwen3-Embedding-0.6B, the current design's choice, is five times larger, and in Lab 4 the query is embedded inside the text service, which the lab budgets at under 1 GB with the vector store. A host-native llama-server for embeddings would make a reviewer install and start a server before the one command. `paraphrase-multilingual-MiniLM-L12-v2` truncates at 128 tokens; `embeddinggemma-300m` is gated.

### 6. One configuration file

`retrieval.toml` at the repository root, read with the standard library:

```toml
chunk_size = 600
chunk_overlap = 100
embedding_model = "intfloat/multilingual-e5-small"
embedding_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
top_k = 5
```

`top_k` is used by the self-check now and by the query path later. The module holds no default for any of these values.

### 7. PostgreSQL image and port

`postgres` uses `pgvector/pgvector:0.8.7-pg16-trixie` and publishes `127.0.0.1:5433:5432`. The image has the same PostgreSQL major version and the same Debian release as the running one, so the existing volume opens without a collation mismatch. The lab's reference tag `pgvector/pgvector:pg16` is the bookworm build and would report one.

`make retrieval-index` runs on the host, like `make train`, and connects through `WAREHOUSE_DSN`, which the Makefile sets to the published port with the credentials of `.env` unless the environment already defines it. Port 5433 is used because 5432 is taken on the course Mac, as 5001 is used for MLflow.

The CI service image changes to the same tag so that the index test finds the extension.

### 8. The index is two tables, replaced in one transaction

The build owns its schema. In one transaction it runs `CREATE EXTENSION IF NOT EXISTS vector`, drops and recreates the schema `retrieval` in the database `landcover`, creates the tables, inserts the rows, runs the self-check and commits:

| Table | Columns |
|---|---|
| `retrieval.chunks` | `chunk_id`, `doc_id`, `doc_version`, `locator`, `ordinal` (position in the document), `text`, `embedding vector(<dimension of the model>)` |
| `retrieval.index_meta` (one row) | `index_version`, `built_at`, `embedding_model`, `embedding_revision`, `chunk_size`, `chunk_overlap`, `documents`, `chunks` |

`index_version` is the first 12 hexadecimal digits of the SHA-256 over the chunk size, the overlap, the model, its revision and the sorted `doc_id`–`doc_version` pairs. `top_k` is not part of it.

Because the build creates everything it needs, it works on the existing volume, where the init script will not run again, and on a clean clone, and `sql/warehouse.sql` is unchanged. A failure at any step rolls back and leaves the earlier index.

Vectors are passed as text and cast with `::vector`, so no client package is added. Search is `ORDER BY embedding <=> $1::vector LIMIT k`, an exact scan by cosine distance. For a few hundred rows this is exact, deterministic and fast; an approximate index would add recall loss and a build parameter for no gain.

Alternative considered: keeping several index versions in one table, keyed by `index_version`. Nothing reads a second version yet; the sweep over top-k needs no rebuild.

### 9. Self-check and output

Before committing, the build embeds `query: What does the value 255 mean in the output mask?`, takes the `top_k` nearest chunks and fails unless one has `doc_id` `export-contract` and a locator starting with `5.1`. It catches a wrong prefix, a wrong distance operator and vectors stored in the wrong order, none of which a row count shows. The lookup is a private helper; the `retrieve` contract belongs to the next change.

The command prints, for example:

```
index a1b2c3d4e5f6: 5 documents, 572 chunks (intfloat/multilingual-e5-small, 600/100)
check "What does the value 255 mean in the output mask?" -> export-contract, 5.1 Problem statement, distance 0.142
```

### 10. Tests

`tests/test_retrieval.py`, with no model and no network:

- chunking: size limit, overlap, one locator per chunk, coverage of the section text, a heading inside a fenced block is not a section;
- corpus: every copy hashes to its manifest entry, and Sections 5.1 and 6.8 are found in `docs/design.md`;
- README: the stated document count equals the number of manifest entries;
- index, through `TEST_DSN` and skipped without it: two builds with a stub embedding give the same counts and the same `index_version`, and a build that raises leaves the earlier index.

The stub maps one known chunk to the query's vector, so the self-check passes without a model.

### 11. Documentation

`docs/design.md`:

- **5.1**: a paragraph stating the LLM component's job in the lab's second shape, an auxiliary job over a corpus: answer questions about the export package from the documents, with citations. It names the corpus: five public documents, where they come from, where the copies are and the chunk count of the first build.
- **5.2**: checklist item 4 and the storage row of the retrieval corpus (Git and PostgreSQL locally, S3 and RDS in the cloud); the corpus table gains the copy's path; the paragraph on copies describes the manifest and the derived `doc_version`; the first two sentences of the Lab 3 paragraph become present tense and name `retrieval.toml`, its five values and `make retrieval-index`. The sentences on prompts, evaluation, cost and latency stay as planned work.
- **6.1**: a subsection "Lab 3 retrieval pipeline" with a Mermaid diagram in the style of the Lab 2 ones: corpus → chunk → embed → index on top, with the configuration feeding chunk, embed and top-k; question → retrieve top-k → LLM with a prompt file → answer below, marked as the next Lab 3 change.
- **6.2**: the "PostgreSQL + pgvector" row names pgvector 0.8.7 and the image; the "LLM and embeddings" row and the paragraph on Qwen3-Embedding name `multilingual-e5-small` in process on the CPU; a short "Lab 3 index" note says where the index lives and how it is rebuilt.
- **6.8**: the "Documentation authors → corpus" row says the copies are committed and what the build checks. This row is itself part of `export-contract`.

`docs/diagrams/deployment.svg`: the embedding label and the `<desc>`. `docs/design.uk.md`: the same passages.

`README.md` gains "Lab 3: retrieval index" with the command, its printed output, the sentence stating 5 documents, the configuration file, the 471 MB first-run download and the new port. No scorecard row is added: the three Lab 3 rows are about evaluation, prompts and cost.

### 12. Review fixes

After the review of the finished Lab 3 branch:

- `load_config` refuses a configuration unless `0 <= chunk_overlap < chunk_size` and `top_k >= 1`. An overlap equal to the chunk size kept `chunk` from advancing and grew the list until memory ran out; a negative one skipped text.
- `index_version` also hashes `INDEX_FORMAT`, a constant beside `CONFIG_KEYS` in the manner of `FEATURE_VERSION` in `pipeline.py`. It is raised whenever the chunking or the text given to the embedding model (`passage: <locator>\n<text>`, `query: `) changes, so an index built by older code no longer passes the guard. Adding it changes the index version once, from `56be0057b30e`.
- The guard names `make retrieval-index` also when the database has no schema `retrieval` yet, instead of failing on the SQL error.
- The index test creates a database with a random name for each run and drops it afterwards, so it never removes a database it did not create.

## Risks / Trade-offs

- [The pgvector image may not open the existing volume cleanly] → Take `pg_dumpall` first. After the swap, check the row count of `dwh.tiles`, the MLflow registry and the server log for collation warnings. If it fails, restore the old image line; the data directory is untouched.
- [Converting four pages by hand can lose a table or a definition] → The author reads each copy against its source before the manifest hash is recorded, with the class definitions of S1 and the QGIS NoData passage checked explicitly.
- [The self-check makes the build fail for a weak configuration] → That is its purpose for the committed configuration. A sweep in a later change that tries a setting too weak to pass will see the failure reported, not hidden.
- [`multilingual-e5-small` may retrieve poorly for Ukrainian questions over English text] → Not measured here. The model and revision are one line of configuration, and the evaluation of a later change decides.
- [The chunk count in the design document goes stale when Section 5.1 or 6.8 changes] → The document states it as the count of the first build with its index version; the README states only the document count, which a test checks.
- [A first run without network access cannot download the model] → The README says so; later runs use the Hugging Face cache.
- [Publishing PostgreSQL on a host port] → Bound to `127.0.0.1` only, like the other services.

## Migration Plan

1. With the stack up, write `pg_dumpall` to a file outside the repository.
2. Change the image and port, then `docker compose up -d --wait postgres` and restart `mlflow` and `airflow`.
3. Check: 96 rows in `dwh.tiles`, the registered model versions visible in MLflow, no collation warning in the PostgreSQL log.

Rollback: drop the schema `retrieval` and the extension `vector` in `landcover`, restore the previous image line and recreate the container. If the volume is damaged, recreate it and restore the dump.

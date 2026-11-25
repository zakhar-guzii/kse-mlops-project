# Tasks

Follow [design.md](design.md) and [specs/retrieval-index/spec.md](specs/retrieval-index/spec.md). Section numbers refer to `docs/design.md`. Do not add a `retrieve` interface, prompt files, a text model, an evaluation set, metrics, scorecard rows or the `lab-3` tag, and do not edit Sections 5.3, 5.4, 6.3, 6.7, 7.1 or 7.2 or `sql/warehouse.sql`. Do not add licence checks.

## 1. PostgreSQL image and dependencies

- [x] 1.1 With the stack up, write `docker compose exec -T postgres pg_dumpall -U "$POSTGRES_USER"` to a file outside the repository and note the row count of `dwh.tiles` and the registered versions shown by MLflow; verify the dump is non-empty and ends with PostgreSQL's completion comment.
- [x] 1.2 In `docker-compose.yml` set the `postgres` image to `pgvector/pgvector:0.8.7-pg16-trixie` and publish `127.0.0.1:5433:5432`, then recreate `postgres` and restart `mlflow` and `airflow`; verify `make up` reports every service healthy, `dwh.tiles` holds the row count noted in 1.1, MLflow lists the same versions, `SELECT * FROM pg_available_extensions WHERE name = 'vector'` returns version 0.8.7, and `docker compose logs postgres` has no collation warning. If the volume does not open, apply the rollback of the design's migration plan and stop.
- [x] 1.3 Add the group `rag` with `sentence-transformers==6.3.0` to `pyproject.toml` and refresh `uv.lock`; verify `git diff uv.lock` changes no existing pin, `make setup` installs nothing from the group, and `uv run --locked --group rag python -c "import sentence_transformers"` succeeds.
- [x] 1.4 Change the service image in `.github/workflows/lint.yml` to the same pgvector tag; verify the existing warehouse test still passes locally with `TEST_DSN` pointing at port 5433.

## 2. Corpus

- [x] 2.1 Create the four copies of design Decision 1 in `corpus/`: headings as Markdown headings, tables as Markdown tables, no navigation, figures, acknowledgements or reference lists; append the label configuration to `corpus/flair-hub.md` as one section with a fenced YAML block taken at a pinned commit. Verify `oem-paper.md` contains the eight class definitions of supplement S1, `flair-hub.md` the 19 label names, `naip-dictionary.md` the band and resolution fields, `qgis-raster.md` the passage on no-data values, and that no file contains a "References" section.
- [x] 2.2 Ask the author to read each copy against its source and wait for their confirmation before recording hashes; verify the confirmation is given or the reported defects are fixed.
- [x] 2.3 Write `corpus/manifest.toml` with the five entries of design Decision 1 (source URLs, access date and SHA-256 for the four copies; file and sections for `export-contract`); verify `shasum -a 256 corpus/*.md` matches the manifest and the label configuration URL contains a commit SHA.

## 3. Configuration and chunking

- [x] 3.1 Add `retrieval.toml` with the five values of design Decision 6; verify `python -c "import tomllib; print(tomllib.load(open('retrieval.toml','rb')))"` prints them and `git grep -n "600\|multilingual-e5" -- src` finds no second copy.
- [x] 3.2 In `src/landcover/retrieval.py` implement, as plain functions, loading the configuration and the manifest, the hash check of the copies, the extraction of Sections 5.1 and 6.8, `doc_version`, the section split and the chunking of design Decisions 2–4; add `tests/test_retrieval.py` with the chunking and corpus tests of design Decision 10. Verify `make test` passes without the `rag` group installed and `make lint` passes.
- [x] 3.3 Print the chunk count per document for the committed corpus with the functions of 3.2; verify the total is between 150 and 700 (widened from 500 when the chunking changed to 600/100, design Decision 4) and no chunk is longer than `chunk_size`. If it is outside that range, report the per-document counts to the author before continuing.

## 4. Index build

- [x] 4.1 Implement the index build of design Decision 8 with the embedding function as an argument, `index_version`, the self-check of Decision 9 inside the same transaction, and the command `python -m landcover.retrieval index` that loads the model of Decision 5 and prints the two lines of Decision 9; add the index test of Decision 10 with a stub embedding. Verify the test passes with `TEST_DSN` set to port 5433 and is skipped without it.
- [x] 4.2 Add the `retrieval-index` target to the `Makefile` (group `rag`, `WAREHOUSE_DSN` defaulting to the published port and the `.env` credentials) and run it; verify it exits zero, prints 5 documents, a chunk count and an index version, and that the check line names `export-contract` and Section 5.1.
- [x] 4.3 Run `make retrieval-index` a second time, then once with a copy temporarily edited; verify the second run prints the same counts and index version, the edited run exits non-zero naming the document, and `SELECT index_version, documents, chunks FROM retrieval.index_meta` still shows the earlier build. Restore the copy.
- [x] 4.4 Add "Lab 3: retrieval index" to the README as in design Decision 11, pasting the output of 4.2, and add the README test of Decision 10; verify the documented commands run as written and `make test` passes.

## 5. Design document and diagram

- [x] 5.1 Revise Section 5.1 as in design Decision 11; verify it states the LLM component's job, that the corpus has five public documents, where they come from, where the copies are, and the chunk count and index version printed in 4.2.
- [x] 5.2 Revise Section 5.2 and the corpus row of Section 6.8 as in design Decision 11; verify the storage row names Git and PostgreSQL for the course, the corpus table gives each copy's path, the configuration paragraph names `retrieval.toml`, its five values and `make retrieval-index` in the present tense, and the sentences on prompts, evaluation, cost and latency are unchanged.
- [x] 5.3 (Superseded by task 4.5 of `add-lab3-llm-baseline`, which redrew the diagrams of Section 6.1 as SVG; the Lab 3 retrieval pipeline is Figure 7.) Add the "Lab 3 retrieval pipeline" subsection with its Mermaid diagram to Section 6.1; verify the diagram renders, shows corpus, chunk, embed, index, the configuration, and the query row marked as later work, and uses this project's names for every box.
- [x] 5.4 Revise the "PostgreSQL + pgvector" and "LLM and embeddings" rows and the embedding paragraph of Section 6.2, add the "Lab 3 index" note, and update the embedding label and `<desc>` of `docs/diagrams/deployment.svg`; verify `git grep -n "Qwen" -- docs README.md` finds nothing outside the alternatives the design chooses to keep, and the SVG renders with unclipped labels.
- [x] 5.5 Synchronise only the passages changed in 5.1–5.4 in the local `docs/design.uk.md`; verify `git check-ignore docs/design.uk.md` still succeeds.
- [x] 5.6 Run `make retrieval-index` again, since 5.1 and 5.2 changed `export-contract`; verify it passes and that the chunk count and index version stated in Section 5.1 are either updated to this build or worded as those of the first build.

## 6. Integration check

- [x] 6.1 On a fresh clone in a scratch directory with its own `.env`, follow only the README: set up, start the stack and run `make retrieval-index`; verify it prints 5 documents on a database that never held the index, and fix the README where it does not match.
- [x] 6.2 Run `openspec validate add-lab3-retrieval-index --strict`, `make lint`, `make test` and `git diff --check`; verify all pass and that Sections 5.3, 5.4, 6.3, 6.7, 7.1 and 7.2 and `sql/warehouse.sql` are untouched.

## 7. Review fixes

Follow design Decision 12. This group may change the index version; the reruns and the documents that state it are tasks of `add-lab3-retrieval-eval`, `add-lab3-llm-baseline` and `add-lab3-rag-answers`.

- [x] 7.1 In `load_config` refuse `chunk_overlap < 0`, `chunk_overlap >= chunk_size` and `top_k < 1`, naming the settings; add tests. Verify the test for an overlap equal to the chunk size ends at once with a `ValueError`, and `make test` passes.
- [x] 7.2 Add `INDEX_FORMAT` to the key of `index_version` and a test that a different format gives a different version. Verify `make test` passes and the README's index version is noted as to be replaced.
- [x] 7.3 Make `check_index` raise the error that names `make retrieval-index` when `retrieval.index_meta` does not exist, with an index test on a database that never held the index. Verify the test passes with `TEST_DSN` set.
- [x] 7.4 Make the fixture `index_dsn` create `retrieval_test_<random>` and drop it after the test with `WITH (FORCE)`. Verify the index tests pass twice in a row with `TEST_DSN` set and leave no `retrieval_test_%` database behind.

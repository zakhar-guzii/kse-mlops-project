# Proposal

## Why

Lab 3 (step 5) requires an evaluation set of at least thirty questions with their relevant sources and reference answers, and hit rate at k and mean reciprocal rank computed by the project's code and logged as runs, with one retrieval parameter varied across three values. The repository has the index of `add-lab3-retrieval-index` and nothing that queries it except the build's one fixed question, so there is no number that says whether the index finds the right passage.

This is the second of the consecutive Lab 3 changes. It measures retrieval only. The prompts, the LLM baseline, the answer metric, cost and latency come later.

## What Changes

- Add `eval/questions.toml`: 32 English questions, each with one or more sources (`doc_id`, section locator and a short verbatim evidence quote from that section) and a reference answer. The questions are drafted by Claude from the corpus during this change and read by the author against the cited sections; the README says so.
- Add a public `retrieve` to `src/landcover/retrieval.py`: a question and k in, the k nearest chunks out, each with `doc_id`, `doc_version`, locator, text and distance. The build's self-check uses the same search statement.
- Add `make retrieval-eval`: it refuses a dirty working tree and an index that does not match the committed configuration and corpus, runs every question through `retrieve`, computes hit rate at k and MRR at k, and logs one MLflow run to the Lab 2 tracking server. `TOP_K=<n>` overrides the configured top-k for one run.
- Run it at top-k 3, 5 and 10 and table the three runs in the README and in Section 7.2 of the design document.
- State in the design document that the assistant takes questions in English and answers in English, and describe the retrieval evaluation in Section 5.4.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| Language | Questions and reference answers are in English. The assistant accepts English questions and answers in English; Ukrainian is not supported and not measured |
| Who writes the questions | Claude drafts them from the corpus while this change is applied; the author reads every row against its cited section before it is used. No generator script is committed |
| Varied parameter and values | top-k at 3, 5 and 10 |

Defaults proposed here, for the author to confirm when reviewing this change:

| Topic | Default | Reason |
|---|---|---|
| What counts as a hit | A retrieved chunk of a listed section that contains that source's evidence quote | A section alone is too coarse: `export-contract` has two sections and one FLAIR-HUB section has 74 chunks. The quote also lets a test catch a wrong label without a model |
| Questions per document | `export-contract` 6, `qgis-raster` 8, `oem-paper` 8, `flair-hub` 6, `naip-dictionary` 4 | By the assistant's job, not by chunk share: FLAIR-HUB is half the chunks, but users ask about the export |
| Paraphrase check | A test fails when a question names the document it points at or shares four consecutive words with its relevant chunk | The lab's rule that a question must not quote its document; same-language questions can do so by accident |
| Lineage of a retrieval run | Tags `git_commit`, `index_version` and `eval_set`; no `data_version` | The run reads the corpus, not `data/raw` |
| Where top-k values live | 5 stays in `retrieval.toml`; 3 and 10 are arguments of two runs | The specification of the index allows no second file holding top-k |

A read-only probe during exploration (12 hand-written questions, expected sources not verified against the text) gave hit rate 0.58, 0.67, 0.75 and 0.75 at k = 1, 3, 5 and 10, so the set is not expected to saturate.

## Capabilities

### New Capabilities

- `retrieval-evaluation`: the committed question set and its integrity rules, the definition of a relevant chunk, hit rate at k and MRR at k, and the tracked run with its lineage.

### Modified Capabilities

- `retrieval-index`: one added requirement, the `retrieve` query interface. This capability is introduced by `add-lab3-retrieval-index`, which is implemented but not archived; it has to be archived first so that the capability exists under `openspec/specs/`.
- `experiment-tracking`: the requirement "Every run carries its lineage" is narrowed to training runs for the `data_version` tag; every run still carries its parameters, scores and `git_commit`.

## Impact

- New files: `eval/questions.toml`.
- Changed code: `src/landcover/retrieval.py` (`retrieve`, the evaluation, the `eval` command), `tests/test_retrieval.py`, `Makefile` (target `retrieval-eval`).
- Changed documents: `README.md` (section "Lab 3: retrieval evaluation"), `docs/design.md` (Section 4, the Lab 3 paragraph of 5.2, Section 5.4, the Lab 3 subsection of 6.1 and a Lab 3 table in 7.2), and the same passages of the local, ignored `docs/design.uk.md`. Sections 5.1 and 6.8 are not edited, so `export-contract` and the index version do not change.
- Running stack: three new runs in a new MLflow experiment `landcover-retrieval`. The index is read, not rebuilt.
- Dependencies: none added. The evaluation runs with the existing group `rag`.
- Out of scope: prompt files and their hashes, the LLM baseline run, the answer path and the answer metric, an LLM judge, cost and latency, questions that the corpus cannot answer, a second language, a sweep over chunk size or the embedding model, any fix for a weak result, the evaluation-loop diagram, Sections 5.3, 6.3, 6.7 and 7.1, the scorecard rows and the `lab-3` tag.

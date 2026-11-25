# Tasks

Follow [design.md](design.md) and the three specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`. Do not add prompt files, a text model, an answer path, an answer metric, a judge, a generator script, scorecard rows or the `lab-3` tag. Do not edit Sections 5.1, 5.3, 6.3, 6.7, 6.8 or 7.1, `retrieval.toml`, `corpus/` or `sql/warehouse.sql`. Do not add licence checks.

## 1. Prerequisites

- [x] 1.1 (Replaced: the author archives the four Lab 3 changes together at the end of the lab, see the follow-up of `add-lab3-rag-answers`.) Check that `add-lab3-retrieval-index` is archived; verify `openspec/specs/retrieval-index/spec.md` exists and `openspec list --json` no longer lists that change. If it is not archived, stop and ask the author to archive it.
- [x] 1.2 With the stack up, run `make retrieval-index`; verify it exits zero and prints 5 documents, and note the index version it prints for the later tasks.

## 2. Retrieval and metrics

- [x] 2.1 In `src/landcover/retrieval.py` add `retrieve` as in design Decision 4 and make `_check` use the same search statement; extend the index test of `tests/test_retrieval.py` as in Decision 9. Verify with `TEST_DSN` on port 5433 that `retrieve` returns k rows with `chunk_id`, `doc_id`, `doc_version`, `locator`, `text` and `distance` in order of distance, that the result for k = 3 is the start of the result for k = 10, that the existing index test still passes, and that the new test is skipped without `TEST_DSN`.
- [x] 2.2 Add the relevant-chunk rule of design Decision 3 and `evaluate` of Decision 5 as plain functions, with the metric and relevance tests of Decision 9. Verify the test for ranks 1, 3 and none at k = 5 gives hit rate 0.667 and MRR 0.444, the test for rank 4 at k = 3 gives a miss, and `make test` passes without the group `rag`.

## 3. Evaluation set

- [x] 3.1 Add the loader of `eval/questions.toml` (design Decision 1) with `eval_set`, and the set and paraphrase tests of Decision 9. Verify the tests fail on a scratch copy of a set with a misspelled locator, with an altered evidence quote, and with a question that contains "QGIS" and points at `qgis-raster`, each naming the question.
- [x] 3.2 Draft the 32 questions by the procedure and the split per document of design Decision 2 (`export-contract` 6, `qgis-raster` 8, `oem-paper` 8, `flair-hub` 6, `naip-dictionary` 4), reading each section before writing its question and taking each locator from `split_sections`. Verify `make test` passes, every question is in English, has a reference answer and at least one source, and no evidence quote is longer than 100 characters.
- [x] 3.3 Ask the author to read every question, reference answer and evidence quote against its cited section, and wait for their confirmation; verify the confirmation is given or every reported defect is fixed and `make test` passes again.

## 4. Evaluation command and the three runs

- [x] 4.1 Add the command `python -m landcover.retrieval eval [--top-k N]` with the two guards of design Decision 6 and the run of Decision 7, add the `retrieval-eval` target to the `Makefile` (group `rag`, `TOP_K` passed as `--top-k`), and add the index-guard test of Decision 9. Verify `make lint` and `make test` pass, and that `make retrieval-eval` with an uncommitted change exits non-zero, names the changed file and creates no run.
- [x] 4.2 Ask the author to commit the code and `eval/questions.toml`, or to approve the commit; verify `git status --porcelain` is empty.
- [x] 4.3 Run `make retrieval-eval TOP_K=3`, `make retrieval-eval` and `make retrieval-eval TOP_K=10`. Verify each exits zero and prints 32 questions with the index version of 1.2; the experiment `landcover-retrieval` in MLflow holds three runs with `top_k` 3, 5 and 10, the parameters, tags, metrics and `results.json` of design Decision 7 and no `data_version` tag; neither the hit rate nor the MRR falls from 3 to 5 to 10; and `retrieval.toml` is unchanged. If the hit rate is 1.0 at k = 3, report it to the author before continuing.
- [x] 4.4 Add "Lab 3: retrieval evaluation" to the README as in design Decision 10, with the printed line and the three rows from the runs of 4.3, and add the README test of Decision 9. Verify the table equals the three runs in MLflow, the stated number of questions equals the set's, the section says that Claude drafted the questions and the author read them and names the model, and `make test` passes.

## 5. Design document

- [x] 5.1 Revise Section 4 and the Lab 3 paragraph of Section 5.2 as in design Decision 10; verify Section 4 says that questions and answers are in English, Section 5.2 names `eval/questions.toml`, `make retrieval-eval` and Section 7.2 in the present tense, and the sentences on prompts, answer correctness, cost and latency still describe planned work.
- [x] 5.2 Add the paragraph "Course experiment (Lab 3): retrieval" to Section 5.4 and the subsection "Lab 3 retrieval results" to Section 7.2; verify 5.4 states the number of questions, how they were produced, the relevant-chunk rule, both metric definitions, the three values and the size of one question in points, and the table of 7.2 equals the README's.
- [x] 5.3 Update the sentence and the question and retrieve labels of "Lab 3 retrieval pipeline" in Section 6.1; verify the diagram renders, shows `retrieve` as built and the LLM and answer boxes as the next change.
- [x] 5.4 Synchronise only the passages changed in 5.1–5.3 in the local `docs/design.uk.md`; verify `git check-ignore docs/design.uk.md` still succeeds.
- [x] 5.5 Run `make retrieval-index` again; verify it prints the index version noted in 1.2, which shows that `export-contract` was not changed by the edits of this group.

## 6. Integration check

- [x] 6.1 Run `openspec validate add-lab3-retrieval-eval --strict`, `make lint`, `make test` and `git diff --check`; verify all pass and that `git diff` of the whole change shows no edit in Sections 5.1, 5.3, 6.3, 6.7, 6.8 and 7.1, `retrieval.toml`, `corpus/` or `sql/warehouse.sql`.

## Workflow follow-up

- Archive the change after the author has reviewed the results.
- The next Lab 3 change adds the prompt files, the LLM baseline and the answer metric, and chooses top-k from the table of this change together with the answer metric and latency.

## 7. Review fixes

Follow design Decision 11. This group overrides the restriction above on `eval/questions.toml`.

- [x] 7.1 Change `evaluate` to take the rows of each question, time the searches in `run_eval` and log `retrieval_s`, `latency_p50_s` and `latency_p95_s`; adapt the tests. Verify the metric tests give the same hit rate and MRR as before and `make test` passes.
- [x] 7.2 Add `clean_head()` to `src/landcover/train.py`, use it in `identity()`, `retrieval.run_eval` and `answer.run`, and tag the value it returned. Verify no command reads `rev-parse HEAD` after its work, and `make test` passes.
- [x] 7.3 Refuse `--top-k` below 1 in `python -m landcover.retrieval eval` and use the configured value only when the option is absent. Verify `python -m landcover.retrieval eval --top-k 0` exits with a usage error.
- [x] 7.4 In `eval/questions.toml` shorten the evidence of q23 to the part one chunk holds whole, add the passages of the top-k 10 run that state the answers of q25 and q28 as further sources, and reword q25 and q26 as asking about the dataset's published experiment. Verify every new evidence quote lies in one chunk, the set and paraphrase tests pass, the split per document is still 6/8/8/6/4, and ask the author to read the changed rows and wait for their confirmation.
- [x] 7.5 After `make retrieval-index` of `add-lab3-retrieval-index` group 7, run `make retrieval-eval TOP_K=3`, `TOP_K=5` and `TOP_K=10`, and replace the retrieval table of the README and Section 7.2 with the new runs, the seconds per run, the new `eval_set` and index version, naming the replaced runs. Verify each row equals its run in MLflow and neither metric falls as k grows.

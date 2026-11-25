# Tasks

Follow [design.md](design.md) and the specification under [specs/](specs/). Section numbers refer to `docs/design.md`. Do not add a retrieval-augmented prompt, a call to `retrieve`, a client library, an API client, a second judge model, scorecard rows or the `lab-3` tag. Do not edit Sections 5.1, 5.3, 6.3, 6.7, 6.8 or 7.1, the five retrieval settings of `retrieval.toml`, `corpus/`, `pyproject.toml` or `uv.lock`. Edit `eval/questions.toml` only as design Decision 14 says. Do not add licence checks.

## 1. Prerequisites and the text model server

- [x] 1.2 Ask the author to approve `brew install llama.cpp`, add `models/` to `.gitignore` and the `llm-server` target of design Decision 1 to the `Makefile`, and start it. Verify the download ends with the SHA-256 check passing, `git status` does not show `models/`, and `curl -s http://127.0.0.1:8081/v1/models` returns the `id` `gemma-4-12b-it-qat-q4_0`.
- [x] 1.3 Send smoke requests to the running server and record the results in the Context of design.md. Verify: a chat request returns `usage` with `prompt_tokens`, `completion_tokens` and `prompt_tokens_details.cached_tokens`; the same request sent again reports cached tokens above 0 and the same `prompt_tokens`; a request with `cache_prompt: false` reports 0 cached tokens; a request with the `json_schema` of Decision 5 returns an object with `reason` and `verdict`; the answer has no reasoning text; `GET /props` returns `build_info`. For a check that fails, apply the fallback named in the Risks of design.md and state it in the Decisions before continuing.
- [x] 1.4 Add the first part of "Lab 3: LLM baseline" to the README (installing llama.cpp, `make llm-server`, the 6.98 GB first download with its hash check, the address) and the note "Lab 3 text model" to Section 6.2 as in design Decision 13. Verify the README's command starts the server as written and the note names the command, the address and the pinned file.

## 2. Configuration and prompts

- [x] 2.1 Add the table `[llm]` of design Decision 2 to `retrieval.toml`, its loader to the new `src/landcover/answer.py`, and the configuration tests of Decision 12 to the new `tests/test_answer.py`. Verify the loader names a key removed from a scratch copy, `make test` passes, and `make retrieval-index` prints the index version the README states.
- [x] 2.2 Add `prompts/plain.md` and `prompts/judge.md` with the content of design Decision 3, the functions that read, hash and fill a prompt, and the prompt tests of Decision 12. Verify a one-character edit of a scratch copy changes the hash, filling raises for `{reference}` on `plain.md`, and `plain.md` names no document and states no fact of the corpus.
- [x] 2.3 Ask the author to read both prompt files and wait for their confirmation; verify the confirmation is given or every requested change is made and `make test` passes again.

## 3. Answering, judging and the command

- [x] 3.1 Add the client of design Decision 4 and the functions `answer_all`, `judge_all` and `summarise` of Decisions 5, 6 and 9, with the metric and verdict tests of Decision 12. Verify the tests give 0.250 for 8 of 32, 3.00 dollars for 1,000,000 and 100,000 tokens at rates 2 and 10, the expected p50 and p95 for known latencies, judge tokens summed apart, a cold request on the first answer call only, and an error naming the question for a verdict outside the two values; `make test` passes without a server.
- [x] 3.2 Add `run()` with the guards of design Decision 7 and the run of Decision 8, the command `python -m landcover.answer eval`, and the `answer-eval` target to the `Makefile` without a dependency group. Verify `make lint` and `make test` pass; with an uncommitted change the command exits non-zero, names the file and creates no run; with the server stopped it exits non-zero and names `make llm-server`; with a scratch configuration whose `model` differs from the server's it names both.

## 4. The baseline run

- [x] 4.1 Ask the author to commit the code, the configuration and the prompts, or to approve the commit; verify `git status --porcelain` is empty.
- [x] 4.2 With the stack and the server up, run `make answer-eval`. Verify it exits zero and prints 32 questions; the experiment `landcover-answers` holds a run `answer-plain` with the parameters, tags, metrics and `results.json` of design Decision 8, `top_k` 0, and no `index_version` or `data_version` tag; `cold_calls` is at least 1 and the first question has 0 cached tokens; no answer has `finish_reason` `length`; the metrics equal the values recomputed from `results.json`. Report to the author how many of the six `export-contract` questions were judged correct, and stop for their decision if all six were.
- [x] 4.3 With the server still up, measure its memory as in design Decision 11; verify the number is recorded for the README.
- [x] 4.4 Complete "Lab 3: LLM baseline" in the README with the command, the printed line, the result row and the statements of design Decision 13 except the judge table, add the subsection "Lab 3 answer results" to Section 7.2, and revise the Lab 3 paragraph of Section 5.2 and the diagram and sentence of "Lab 3 retrieval pipeline" in Section 6.1. Verify the row equals the run in MLflow and is the same in both documents, Section 5.2 names `prompts/`, `make answer-eval` and Section 7.2 while the retrieval-augmented prompt stays planned, and Figure 7 of task 4.5 shows the plain-prompt edge built and the retrieve edge marked as the next change.

- [x] 4.5 Redraw the four Mermaid diagrams of Section 6.1 (Lab 2 data layers, Lab 2 Airflow DAG, Lab 2 tracking and registry, Lab 3 retrieval pipeline) as SVG files in `docs/diagrams/` in the style of Figures 2 and 3, numbered Figures 4 to 7 with an alt text and a caption, with the same nodes and edges as the diagrams they replace. Verify every file is well-formed XML and renders with no text outside its box and no edge across a label, Section 6.1 has no Mermaid block, and the author has looked at the four figures.

## 5. The check of the judge and the revised set

- [x] 5.1 Extract `id` and answer from the run's `results.json` without the verdicts and reasons, label every answer by the rubric of `prompts/judge.md` from the question, the reference answer and the answer, write `eval/judge-check.toml` as in design Decision 10, and only then copy in the verdicts. Verify the file names the run of 4.2 and has one row per question, and the judge-check test of Decision 12 runs instead of being skipped. (Done for run `736634076b744485a8c19f690101c03c`, superseded by Decision 14.)
- [x] 5.2 Rewrite `eval/questions.toml` as in design Decision 14 and add the one-sentence test to `tests/test_retrieval.py`. Verify identifiers, sources, evidence quotes and the 6/8/8/6/4 distribution are unchanged or a replaced question cites the same section, no reference answer has a semicolon or a second sentence, and `make test` and `make lint` pass.
- [x] 5.3 Ask the author to read all 32 rows against their sections and wait for their confirmation; verify the confirmation is given or every requested change is made and `make test` passes again.
- [x] 5.4 Add the two rules of design Decision 3 to `prompts/judge.md`, ask the author to read it and wait for their confirmation, then ask the author to commit or approve the commit. Verify `make test` passes and `git status --porcelain` is empty.
- [x] 5.5 Run `make retrieval-eval TOP_K=3`, `make retrieval-eval` and `make retrieval-eval TOP_K=10`, and replace the retrieval table, its run IDs, `eval_set`, commit and the sentence on misses in the README and in Section 7.2. Verify each row equals its run in MLflow and the index version is still `56be0057b30e`.
- [x] 5.6 Repeat 4.2 and 4.3 on the revised set and replace the result row, the printed line and the statements of 4.4 in the README and Section 7.2, naming `736634076b744485a8c19f690101c03c` as superseded. Verify everything 4.2 verifies and that both documents give the same row.
- [x] 5.7 Repeat 5.1 for the run of 5.6: labels without the verdicts first, then the verdicts. Verify the file names the run of 5.6 and has one row per question.
- [x] 5.8 Ask the author to read every row, the rows where `judge` and `label` differ first, and wait for their confirmation; verify the confirmation is given or every corrected label is applied. If fewer than 29 verdicts equal the labels, follow the rule of design Decision 10 (revise `judge.md`, commit, repeat 5.6 and 5.7) and verify the README names the superseded run.
- [x] 5.9 Add the judge table to the README and the paragraph "Course experiment (Lab 3): answers" to Section 5.4 as in design Decisions 10 and 13, with one sentence on the revision of the set. Verify the four counts equal the file's and the README test passes, both documents say that Claude labelled the answers without the verdicts, name the model and say that the author reviewed them, and Section 5.4 states the rubric, the judging model and the limit of a check on mostly wrong answers.

## 6. Integration check

- [x] 6.1 Synchronise only the passages changed in 1.4, 4.4, 4.5, 5.5, 5.6 and 5.9 in the local `docs/design.uk.md`; verify `git check-ignore docs/design.uk.md` still succeeds.
- [x] 6.2 Run `make retrieval-index`; verify it prints the index version of 2.1, which shows that `export-contract` was not changed by the edits to the design document.
- [x] 6.3 Run `openspec validate add-lab3-llm-baseline --strict`, `make lint`, `make test` and `git diff --check`; verify all pass and that the diff of the whole change shows no edit in Sections 5.1, 5.3, 6.3, 6.7, 6.8 and 7.1, the five retrieval settings, `corpus/`, `pyproject.toml` or `uv.lock`, and that `eval/questions.toml` changed only in questions and reference answers.

## 7. Review fixes

Follow design Decision 15. This group overrides the restrictions above on `eval/questions.toml`, `prompts/judge.md`, the `Makefile` and the server installation.

- [x] 7.1 Add the target that builds `llama-server` at tag `b12359` into `models/llama.cpp`, make `llm-server` depend on it, run the built binary, and check the SHA-256 of `$(LLM_FILE)` in the recipe before starting it. Verify `models/llama.cpp/build/bin/llama-server --version` prints build 12359 and commit `b1b770d90`, `git status` does not show `models/`, and `make llm-server` with a scratch file in place of the model (renamed back afterwards) exits non-zero without starting the server.
- [x] 7.2 Make `fill` substitute in one pass, record `cached_tokens` as `null` when the server omits it and log `cold_calls` only when every call reports it, and make the judge-check test require both files and equal identifier sets; add a test for each. Verify the tests fail before the change and pass after it, and `make test` passes.
- [x] 7.3 Add the rule on a false addition to `prompts/judge.md` and reword q25 and q26 in `eval/questions.toml`; ask the author to read both and wait for their confirmation, then to commit or approve the commit. Verify the one-sentence test and the paraphrase test pass.
- [x] 7.4 With the server of 7.1 up, the index rebuilt and a clean tree, run `make answer-eval`. Verify everything 4.2 verifies and that the run reports build `b12359-b1b770d90`.
- [x] 7.5 Relabel `eval/judge-check.toml` for the run of 7.4 as in 5.1: labels without the verdicts first, then the verdicts by script; ask the author to read every row. Verify the file names the run, has one row per question and the README test passes.
- [x] 7.6 Replace the result row, the printed line, the prompt hashes, the judge table and its text in "Lab 3: LLM baseline" and Sections 5.4, 6.3, 6.7 and 7.2, replace `brew install llama.cpp` in the README with the build target and its prerequisites, and name the replaced run. Verify both documents give the same row and every number equals the run in MLflow.

## Workflow follow-up

- Archive this change together with the earlier Lab 3 changes once the whole of Lab 3 is complete.
- The next Lab 3 change adds the retrieval-augmented prompt, runs it at top-k 3, 5 and 10 in the same experiment, tables hit rate, MRR and the answer metric, repeats the check of the judge on one of those runs and chooses top-k.

# Tasks

Follow [design.md](design.md) and the two specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`. Do not add a second answer prompt, a citation-correctness metric, a second judge model, a sweep of another parameter, `--swa-full` or any other flag to `make llm-server`, or the `lab-3` tag. Do not edit Sections 5.1 or 6.8, `prompts/plain.md`, `eval/questions.toml`, `corpus/`, `pyproject.toml` or `uv.lock`; edit `prompts/judge.md` only under the rule of design Decision 6 and `retrieval.toml` only in `top_k` under Decision 7. Do not read a per-question verdict of a retrieval-augmented run before task 4.1 is done. Do not archive any change and do not add licence checks.

## 1. The prompt and the passages

- [x] 1.1 Add `prompts/rag.md` with the content of design Decision 1, the function that renders retrieved rows as numbered passages, the function that reads passage numbers from an answer, and their tests of Decision 10. Verify the placeholder test covers `rag.md`, three rows render as passages 1 to 3 with document, locator and text, `Sources: [2], [4]` gives 2 and 4, `Sources: none` gives none, and `make test` and `make lint` pass.
- [x] 1.2 Ask the author to read `prompts/rag.md` and wait for their confirmation; verify the confirmation is given or every requested change is made, the file still tells the model to say when no passage supports the answer, and `make test` passes again.

## 2. The retrieval-augmented path and the command

- [x] 2.1 Extend `answer_all`, `summarise` and `results` in `src/landcover/answer.py` as in design Decision 2, with the tests of Decision 10 driven by a fake search. Verify that 0.5 s of retrieval and 2.0 s of answering per question give p50 2.5, `retrieval_s` 16.0 and `compute_s` 64.0 for 32 questions, that hit rate and MRR equal `retrieval.evaluate` on the same rows, that a number above k is recorded and not counted, and that every existing test of the plain path passes unchanged.
- [x] 2.2 Add `--top-k` to `python -m landcover.answer eval`, the retrieval-augmented branch of `run()` with the guards of design Decision 3 and the run of Decision 4, and `TOP_K` to the `answer-eval` target of the `Makefile`. Verify `make lint` and `make test` pass without the group `rag`; `uv run --locked python -c "import landcover.answer"` succeeds without that group; with an uncommitted change `make answer-eval TOP_K=5` exits non-zero and creates no run; with a scratch configuration whose chunk size differs from the index it names `make retrieval-index`; with the server stopped it names `make llm-server`.
- [x] 2.3 Add the first part of "Lab 3: retrieval-augmented answers" to the README: the three commands, what the prompt tells the model, what a run logs and the guards. Verify the commands are the ones the `Makefile` accepts and the section names `prompts/rag.md`, the group `rag` and the experiment `landcover-answers`.

## 3. The three runs

- [x] 3.1 Ask the author to commit the code, the prompt and the README part, or to approve the commit; verify `git status --porcelain` is empty.
- [x] 3.2 With the stack up, start `make llm-server` and compare the build it reports with `b12359-b1b770d90`. If it differs, tell the author and repeat the plain run as design Decision 5 says before continuing. Run `make retrieval-index` and verify it prints index version `56be0057b30e`.
- [x] 3.3 Run `make answer-eval TOP_K=3`, `make answer-eval TOP_K=5` and `make answer-eval TOP_K=10`. Verify with a script that prints only counts and booleans: each run exits zero with 32 questions; the experiment `landcover-answers` holds runs `answer-rag-k3`, `answer-rag-k5` and `answer-rag-k10` with the parameters, tags, metrics and `results.json` of design Decision 4; hit rate and MRR equal 0.469 and 0.375, 0.594 and 0.403, 0.750 and 0.422; no answer has `finish_reason` `length`; `cold_calls` is at least 1; the metrics equal the values recomputed from `results.json`; every cited number is between 1 and k, or the count of those outside is reported to the author.
- [x] 3.4 With the server still up, take the three measurements of design Decision 9; verify the three numbers are recorded for the README with the commands that gave them.
- [x] 3.5 Add to the README section the printed line of one run and the table of four rows of design Decision 11 with its header line of model, build, prompt hashes, index version, `eval_set` and commit, and add the subsection "Lab 3 retrieval-augmented answer results" with the same table to Section 7.2. Verify each row equals its run in MLflow, the baseline row is unchanged, and both documents give the same table.

## 4. The check of the judge

- [x] 4.1 Write the `id` and answer of each question of the run at top-k 10 to a scratch file without verdicts and reasons, label every answer by the rubric of `prompts/judge.md`, write `eval/judge-check-rag.toml` as in design Decision 6, and only then copy the verdicts in by script. Verify the file names the run of 3.3 at top-k 10 and has one row per question with `judge` and `label` in the two values.
- [x] 4.2 Ask the author to read every row, the rows where `judge` and `label` differ first, and wait for their confirmation; verify the confirmation is given or every corrected label is applied. If fewer than 29 verdicts equal the labels, follow the rule of design Decision 6 (revise `judge.md`, commit, repeat the four runs, relabel changed answers, replace the tables of 3.5) and verify the README names the superseded runs.
- [x] 4.3 Make the judge-table test cover both files and both README sections as in design Decision 6, and add the second judge table to the README with the run, the labelling model, what the labeller had seen and that the author reviewed the labels. Verify the four counts equal the file's, the test fails on a scratch copy of the README with one count changed, and `make test` passes.

## 5. The choice of top-k and the results

- [x] 5.1 Apply the rule of design Decision 7 to the three runs and report the chosen value with the three counts to the author. If it is not 5, change `top_k` in `retrieval.toml`, ask the author to commit or approve the commit, run `make retrieval-index` and verify it exits zero with index version `56be0057b30e`; update the README lines that state the default of `make retrieval-eval`. Verify `make test` passes.
- [x] 5.2 Complete the README section as in design Decision 11: correct answers per document for the four runs, the four counts of hit or miss against correct or incorrect for each k, the number of answers that name a passage, the rule and the chosen top-k, the block "Configuration for Lab 4" and the memory numbers. Verify every count is recomputed from the runs' `results.json` by a script, the chosen top-k equals `top_k` in `retrieval.toml`, and the block's hashes equal the tags of the chosen run.
- [x] 5.3 Replace the cache sentence of "Lab 3: LLM baseline" in the README with the cause and the measurements of design Decision 8, and correct every "next Lab 3 change" in the two earlier Lab 3 sections of the README. Verify the README says that the server command is unchanged, names `--swa-full` with the measured numbers, and `grep -n "next Lab 3 change" README.md` finds nothing.

## 6. The design document

- [x] 6.1 Revise the Lab 3 paragraph of Section 5.2, add the paragraph "Course experiment (Lab 3): retrieval-augmented answers" to Section 5.4, add the choice to the subsection of 3.5 in Section 7.2 and correct its two sentences on "the next Lab 3 change", and put the Lab 3 milestone of Section 7.4 in the past tense, as in design Decision 11. Verify 5.2 names `prompts/rag.md` and `make answer-eval TOP_K=<n>` in the present tense, 5.4 states the rule, the chosen value, the second check and that its labels were written before its verdicts were seen, and `grep -n "next Lab 3 change" docs/design.md` finds nothing.
- [x] 6.2 Add the part "LLM component (Lab 3)" to Section 5.3 and the six rows of design Decision 11 to Section 7.1. Verify 5.3 names the baseline, the retrieval technique, the grounding rule and what the model receives at serving time, and 7.1 has a row for an API against local inference with a decision.
- [x] 6.3 Add "Text model (Lab 3 measurements)" to Section 6.3 and "Measured in Lab 3" to Section 6.7, and replace the promise of a measurement next to Minikube in Section 6.2 with the measured memory, as in design Decisions 9 and 11. Verify 6.3 states the model size, the quantisation, Metal on the M4 Pro, p50 and p95 for the plain prompt and the chosen top-k and the cache finding; 6.7 states tokens, shadow cost and compute seconds per answer from the four runs and leaves $301.75 and $338.25 unchanged; every number equals the README's.
- [x] 6.4 Redraw `docs/diagrams/lab3-retrieval.svg` with the edge from retrieve to the model solid and the prompt file named, add `docs/diagrams/lab3-evaluation-loop.svg` as Figure 8 with an alt text and a caption, and update the sentence above Figure 7 in Section 6.1. Verify both files are well-formed XML and render with no text outside its box and no edge across a label, Figure 7 has no dashed edge, Figure 8 shows the evaluation set, retrieval and answer, the metrics with the judge, the MLflow run and the loop over top-k 3, 5 and 10, and the author has looked at both figures.

## 7. Hand-in

- [x] 7.1 Add the three Lab 3 rows to the maturity scorecard of the README and one sentence on Lab 3 to its opening paragraph, as in design Decision 11. Verify the rows are named "LLM component evaluated", "Prompts versioned" and "Cost and latency recorded", each points at evidence a reviewer can open or rerun, and every link resolves.
- [x] 7.2 Synchronise only the passages changed in groups 3, 5 and 6 in the local `docs/design.uk.md`; verify `git check-ignore docs/design.uk.md` still succeeds.
- [x] 7.3 Run `make retrieval-index`; verify it prints index version `56be0057b30e`, which shows that Sections 5.1 and 6.8 were not changed.
- [x] 7.4 Run `openspec validate add-lab3-rag-answers --strict`, `make lint`, `make test` and `git diff --check`; verify all pass and that the diff of the whole change shows no edit in Sections 5.1 and 6.8, `prompts/plain.md`, `eval/questions.toml`, `corpus/`, `pyproject.toml`, `uv.lock` or the `llm-server` target, and that `retrieval.toml` changed at most in `top_k`.

## 8. Review fixes

Follow design Decision 12. This group comes after groups 7 of `add-lab3-retrieval-index`, `add-lab3-retrieval-eval` and `add-lab3-llm-baseline` and overrides the restrictions above on `eval/questions.toml`, archiving and the `lab-3` tag.

- [x] 8.1 Remove `scores()` and pass one `retrieval.evaluate` result to `summarise` and `results`. Verify the hit rate and MRR test still equals `retrieval.evaluate` and `make test` passes.
- [x] 8.2 Rewrite the reference answer of q08 to name both ways in one sentence; ask the author to read it with the rows of the other groups and to commit or approve the commit. Verify the one-sentence test passes and `git status --porcelain` is empty.
- [x] 8.3 Run `make answer-eval TOP_K=3`, `TOP_K=5` and `TOP_K=10` on the server of `add-lab3-llm-baseline` 7.1. Verify what 3.3 verifies, with hit rate and MRR equal to the retrieval runs of `add-lab3-retrieval-eval` 7.5.
- [x] 8.4 Relabel `eval/judge-check-rag.toml` for the new run at top-k 10 as in 4.1 and have the author read every row as in 4.2. Verify q03 and q08 are labelled by the revised rubric and reference, and the README test passes.
- [x] 8.5 Apply the rule of design Decision 7 and set `top_k` in `retrieval.toml` to the chosen value. Verify `make test` passes.
- [x] 8.6 Replace the tables, counts, the printed line, the choice, the block "Configuration for Lab 4", the index version in `docs/diagrams/lab3-evaluation-loop.svg` and the numbers of Sections 5.4, 6.3, 6.7 and 7.2, and name the replaced runs; synchronise the local `docs/design.uk.md`. Verify every count is recomputed from `results.json` by a script and `grep -rn 56be0057b30e README.md docs/design.md docs/diagrams` finds only sentences about replaced runs.
- [x] 8.7 Run `openspec validate --all --strict`, `make lint`, `make test` with `TEST_DSN` set and `git diff --check`; verify all pass.
- [x] 8.8 Archive the four Lab 3 changes in the order of the follow-up below; verify `openspec list` shows none of them and `openspec validate --all --strict` passes.
- [ ] 8.9 With the author's approval, set the tag `lab-3` on the final commit and push the branch and the tag. Verify `git ls-remote --tags origin lab-3` names that commit.

## Workflow follow-up

- The author sets the tag `lab-3` on the final commit and sends the repository link.
- The author archives the four Lab 3 changes together once the lab is complete, in the order `add-lab3-retrieval-index`, `add-lab3-retrieval-eval`, `add-lab3-llm-baseline`, `add-lab3-rag-answers`, because each delta builds on the capability of the one before.

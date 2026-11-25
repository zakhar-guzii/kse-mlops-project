# Design

## Context

See [proposal.md](proposal.md) for motivation, scope and the decisions settled with the author. Section numbers without a file name refer to `docs/design.md`.

Facts checked for this design on 2026-11-25:

- **The lab text** (`labs/lab-3.pdf`, ignored by Git). Step 4 asks for "question to retrieve top-k to prompt (with the retrieved chunks) to answer" with the prompt as a second versioned file. It does not say whether the model may use its own knowledge. Its notes say the component is graded on versioned configuration, tracked runs, an evaluation set and lineage, "not how clever the answers are". Step 1 names Sections 5.1, 5.3, 5.4, 6.3, 6.7 and 7.1 and the pipeline diagram in 6.1; "after this lab, 6.7 states the per-request cost or the local compute used, measured from your own runs". Step 6 asks 6.3 and 6.7 for the model size, the quantisation, the GPU and the measured latency of a self-hosted model. Appendix 3 gives two diagrams to redraw, the retrieval pipeline and the evaluation loop, and the three scorecard rows: "LLM component evaluated", "Prompts versioned", "Cost and latency recorded".
- **The project's own contract.** Section 5.1 says the assistant answers "from the documents, and cites the passage it used". Section 6.8 says of `retrieve`: "Cite the passage supporting the answer. If no source supports it, report that limitation." Both sections are the document `export-contract`, so an edit changes the index version under every run.
- **What the existing runs predict.** Joining the baseline `8fe988ff` with the ranks of the retrieval run `a1171818` per question:

  | k | Retrieval hits | Plain correct | Hit and plain correct | Hit, plain wrong | Miss, plain correct | Hit or plain correct |
  |---|---|---|---|---|---|---|
  | 3 | 15 | 15 | 8 | 7 | 7 | 22 |
  | 5 | 19 | 15 | 9 | 10 | 6 | 25 |
  | 10 | 24 | 15 | 12 | 12 | 3 | 27 |

  The model and the retriever know different things: the model alone answers 7 of 8 on the QGIS page and 4 of 4 on the NAIP dictionary, where retrieval at k = 5 hits 5 of 8 and 1 of 4. A prompt that allowed only the passages would have a ceiling near the hits (0.469, 0.594, 0.750) and at k = 3 would equal the baseline's 0.469 on other questions. The prompt chosen here has a ceiling near the last column (0.688, 0.781, 0.844). 13 of the 17 wrong baseline answers are refusals.
- **The prompt cache.** Measured on the installed server (build `b12359-b1b770d90`, the build of the baseline run) with the command of `make llm-server`, and again with `--swa-full` added:

  | Server | Prompt | Prompt tokens | Cached tokens | Prompt evaluation | Call |
  |---|---|---|---|---|---|
  | as committed | plain, instruction shared | 102 to 104 | 1 | 0.47 s | 1.4 to 2.0 s |
  | as committed | instruction and five passages | 780 to 1,103 | 1 | 2.9 to 3.9 s | 3.5 to 4.8 s |
  | as committed | the previous prompt again | 960 | 955 | 0.17 s | 1.0 s |
  | `--swa-full` | plain, instruction shared | 102 to 104 | 86 | 0.14 to 0.24 s | 1.1 to 1.6 s |
  | `--swa-full` | instruction and five passages | 780 to 1,103 | 84 to 91 | 2.4 to 3.5 s | 3.0 to 4.4 s |

  Gemma uses sliding-window attention in part of its layers, and llama.cpp by default keeps only the window for those layers. An identical prompt is reused whole; a prompt that shares only a prefix cannot be rolled back to that prefix, so everything after the first token is evaluated again. The server log names no reason; it prints only the slot selection. With `--swa-full` the server logs "using full-size SWA cache" and the shared instruction is reused. The physical footprint after these calls was 3,806 MB as committed and 3,867 MB with the flag. Prompt evaluation runs at about 275 tokens per second, so ten passages (1,500 to 2,100 tokens) cost about 6 to 8 seconds before the first output token.
- **The code.** `answer.answer_all`, `judge_all`, `summarise` and `results` are pure functions that the tests drive with a fake model; `run()` holds the guards and the MLflow call. `retrieval.retrieve(conn, question, k, embed)` returns rows with `chunk_id`, `doc_id`, `doc_version`, `locator`, `text` and `distance`; `retrieval.evaluate(questions, search, k)` takes a function from question text to ranked rows and returns hit rate, MRR and a rank per question; `retrieval.check_index` raises on a stale index. `index_version` does not include `top_k`, and a test says so.
- **The check file.** `eval/judge-check.toml` names one run, and its test finds the first judge table of the README by a regular expression.
- **The stack.** MLflow answers on port 5001. The text model server was not running; the model file is in `models/`.

## Goals / Non-Goals

**Goals:**

- One run is one row of the table: an answer run computes its own hit rate and MRR from the passages it sent.
- The retrieval-augmented path adds to the existing module and leaves the plain path and its tests as they are.
- The prompt evaluated here is the prompt Lab 4 serves, with the citation behaviour Sections 5.1 and 6.8 already promise.
- Every rule that decides something (top-k, the judge threshold) is written before the number it decides on.

**Non-Goals:**

- A second prompt variant, a comparison of grounding rules, or a sweep of a second parameter.
- A metric for whether a citation is right, and any parsing of the answer beyond the passage numbers.
- A sweep runner or several values of k in one run.
- Changing the server command, the judge prompt, the plain prompt or the question set.
- Code that measures memory.

## Decisions

### 1. `prompts/rag.md`: passages first, own knowledge with disclosure

The file holds the placeholders `{passages}` and `{question}`. The instruction comes first, then the passages, then the question, as one user message, like `plain.md`.

Content, drafted while the change is applied and read by the author:

- the reader and the scope of `plain.md`;
- the passages below were retrieved from the project documentation and are numbered; each starts with its document and section; they come from different documents, so a passage about a dataset does not describe this service's export;
- answer from the passages when one of them states the answer, and prefer a passage to your own memory when they differ;
- when no passage states the answer, answer from your own knowledge if you are confident, otherwise say that you do not know;
- answer in English in at most three sentences with the specific value or name asked for;
- end with one line: `Sources: [n]` with the numbers of the passages that state the answer, or `Sources: none`.

A passage is rendered as:

```
[2] oem-paper, 2.2 Data > Classes
<chunk text>
```

Passages are in the order `retrieve` returns them, nearest first, separated by a blank line.

The disclosure line is what makes the permissive rule compatible with Sections 5.1 and 6.8: an answer either cites a passage or reports that none supports it. The document identifier in each header is there for the case found during the retrieval change: the OpenEarthMap paper numbers bareland 1 and the export numbers it 0.

Alternatives considered. A strict prompt ("answer only from the passages, otherwise say you do not know") follows 5.1 most literally and would turn about six answers the model has right at k = 5 into refusals; the author chose the permissive rule. A permissive prompt without the disclosure line would contradict 6.8 and could not be reconciled without editing it. Both prompts in one table would double the runs and the judge check for a comparison the lab does not ask for.

### 2. The retrieval-augmented path is an optional search in the existing functions

`answer_all` gains an optional function from question text to ranked rows. When it is given, each question is retrieved first, with the seconds of that call measured by `time.perf_counter`, and the prompt is filled with the rendered passages; the record of the answer carries `retrieval_s` and the rows. Without it the function behaves as now and `retrieval_s` is 0.

`summarise` takes latency per question as `retrieval_s + seconds` and adds the sum `retrieval_s` to the metrics. `compute_s` stays the sum over the answer calls, so it remains the text model's time.

Hit rate and MRR are not written a second time: the run calls `retrieval.evaluate(questions, search, k)` with a search that returns the rows already retrieved for that question, so the definition of a relevant chunk and both formulas are those of `make retrieval-eval`.

Passage numbers are read from the answer with one regular expression over `[n]`. `cited` is the list of numbers; an answer names a passage when at least one number lies in 1 to k.

`run(top_k)` with `top_k` above 0 loads the five retrieval settings, connects to `WAREHOUSE_DSN`, applies `check_index`, loads the embedder and passes `retrieve` as the search. These imports and the connection happen only in that branch, so the plain run still needs neither the group `rag` nor the database.

Alternative considered: a second module for the retrieval-augmented run. It would repeat the guards, the judge loop and the MLflow call for one added argument.

### 3. The command

```
python -m landcover.answer eval [--top-k N]
make answer-eval              # plain, top_k 0
make answer-eval TOP_K=5      # retrieval-augmented, group rag
```

The Makefile adds `--group rag` and `--top-k` only when `TOP_K` is set. Without it the command is the one the README gives for the baseline row, which stays reproducible by the same line. `top_k` of `retrieval.toml` is not read by this command: it is the value `make retrieval-eval` defaults to and the value Lab 4 serves, and it is set by Decision 7 after the runs.

Guards, in this order, before the first call: the dirty-tree rule; the server and its model name; and for a retrieval-augmented run the index guard of `make retrieval-eval`, whose message names `make retrieval-index`.

The command prints one line, for example:

```
run 1a2b3c4d: rag top_k 5, 32 questions, correct 0.719, hit rate 0.594, MRR 0.403, tokens 30412 in / 1502 out, p50 4.2 s, p95 5.1 s, shadow cost $0.0758 (prompt 3f2a9c1d7e5b, judge 5b291def62c3, index 56be0057b30e, questions d06b7a39c631)
```

### 4. What a retrieval-augmented run holds

| Kind | Content |
|---|---|
| Experiment | `landcover-answers`, with the baseline |
| Run name | `answer-rag-k<top_k>` |
| Parameters | those of the baseline with `top_k` set, and `chunk_size`, `chunk_overlap`, `embedding_model`, `embedding_revision` |
| Tags | `git_commit`, `eval_set`, `prompt_hash` (of `rag.md`), `judge_prompt_hash`, `index_version` |
| Metrics | those of the baseline, and `hit_rate`, `mrr`, `retrieval_s`, `cited_answers` (the number of answers that name a retrieved passage) |
| Artifact | `results.json`: the baseline's fields per question, and `rank`, `retrieved` (the chunk identifiers in order), `cited` and `retrieval_s` |

The metric names equal those of `landcover-retrieval`, so MLflow shows hit rate and MRR in the same columns. The plain run logs none of the four added metrics.

### 5. Three runs, one commit, the baseline row kept

`make answer-eval TOP_K=3`, `TOP_K=5` and `TOP_K=10` on one commit, with the server started by `make llm-server` as committed. The baseline run `8fe988ff4fa94f2d956a189fb9015b8d` stays the first row: the question set, `plain.md`, `judge.md`, the model and the server command are unchanged. Before the runs the build the server reports is compared with `b12359-b1b770d90`; if Homebrew has replaced it, the plain run is repeated on the new commit, its row and its judge check are replaced as in the earlier change, and the old run is named as superseded.

Each run is checked by a script that prints counts and booleans, not answers with verdicts: 32 questions, no `finish_reason` `length`, `cold_calls` at least 1, the metrics recomputed from `results.json`, and hit rate and MRR equal to the retrieval run of the same k (0.469 and 0.375, 0.594 and 0.403, 0.750 and 0.422). This keeps the per-question verdicts unseen until Decision 6 is done.

The context of 8,192 tokens holds the largest prompt, about 2,200 tokens at k = 10, with the 256 output tokens.

### 6. The check of the judge on the run at top-k 10

The run at k = 10 has the most retrieved answers, so it is the run with the most answers the judge should accept, which the first check lacked. The file is `eval/judge-check-rag.toml`, in the shape of `eval/judge-check.toml`.

1. A script writes the `id` and answer of each question of the k = 10 run to a scratch file, without the verdict and the reason.
2. Claude labels each answer by the rubric of `prompts/judge.md` from the question, the reference answer and the answer. The line `Sources:` is not part of the fact being checked. No per-question verdict of any of the three runs has been read at this point; the printed answer metric of each run has.
3. The labels are written to the file, and only then a script copies the judge's verdicts in.
4. The author reads every row, the disagreements first, and corrects a wrong label.
5. The README gives the four counts, the run, the model that labelled and that the author reviewed the labels.

The threshold fixed in the earlier change holds: fewer than 29 of 32 equal means `judge.md` is revised and committed, all four runs are repeated because the judge prompt hash changes for each, labels are kept for answers whose text is unchanged, and the earlier runs are named as superseded. Top-k is chosen only after the check has passed.

The test of the judge table becomes one test over two pairs: `eval/judge-check.toml` with the README section "Lab 3: LLM baseline", and `eval/judge-check-rag.toml` with "Lab 3: retrieval-augmented answers". It reads the table inside the named section, so two tables do not shadow each other.

### 7. The rule that chooses top-k

The chosen value is the smallest of 3, 5 and 10 whose number of correct answers is no more than two below the best of the three. Section 5.4 already says that a difference of one or two questions decides nothing on 32 questions, and each added passage adds about 150 to 200 prompt tokens and about 0.6 seconds.

When the chosen value is not 5, `top_k` in `retrieval.toml` is changed and committed. The index version does not change. The three runs are not repeated: top-k was an argument of each. The README then states the new default of `make retrieval-eval`, and `make retrieval-index` is run once to confirm that the build's self-check still passes at the new value.

If no retrieval-augmented run beats the baseline by more than two questions, the rule still gives a value, the README says so, and retrieval stays in the design because Section 5.1 requires a cited passage.

Alternative considered: a latency ceiling in the rule. The design has no latency target for an assistant answer, and inventing one to decide k would be a number without a source.

### 8. The prompt cache: documented, the server command unchanged

The README sentence "the server log does not give the reason" is replaced by the cause and the two measurements of Context. `make llm-server` keeps its flags.

Consequences stated in the documents: in every run of this lab each call evaluates its whole prompt, so the reported latencies contain no reuse of a shared prefix and `cold_calls` 1 understates how cold the run is; the first call still sends `cache_prompt: false`, which keeps the lab's requirement of one cold prompt independent of the server's flags. Section 6.3 names `--swa-full` as the first latency lever for Lab 4, with the measured saving of about 0.4 seconds per answer and 61 MB.

Alternative considered: adding `--swa-full` now. The four rows of the table must come from one server configuration, so the baseline would be rerun and its judge check rewritten for a tenth of the latency.

### 9. Memory, once and by hand

After the run at k = 10, with the Compose stack and the server up: `footprint $(pgrep -x llama-server)`; `docker stats --no-stream` for the containers of the stack; and the maximum resident set size of one `make answer-eval TOP_K=10` process from `/usr/bin/time -l`, which is the embedding model and the client that the Lab 4 text service will hold. The three numbers go into the README and Sections 6.2 and 6.3. The sentence of Section 6.2 that Lab 3 measures the model next to Minikube is changed to say that this is measured next to the Compose stack and that the Minikube measurement belongs to Lab 4.

### 10. Tests

In `tests/test_answer.py`, with no model, no server and no database:

- `rag.md` has `{passages}` and `{question}`;
- three rows are rendered as passages 1 to 3 with document, locator and text, in the order given;
- with a fake search, each prompt holds its passages before its question, the record carries the rows and `retrieval_s`, and only the first answer call is cold;
- 0.5 seconds of retrieval and 2.0 of answering per question give p50 2.5 and `retrieval_s` 16.0 for 32 questions, and `compute_s` 64.0;
- hit rate and MRR of the rows equal `retrieval.evaluate` on the same rows;
- `Sources: [2], [4]` gives `[2, 4]`, `Sources: none` gives none, and `[7]` at k = 5 is recorded and does not count;
- the judge table test of Decision 6, skipped for a file that does not exist yet.

The existing tests of the plain path pass unchanged, which is the check that Decision 2 did not alter it.

### 11. Documentation

`README.md`:

- a section "Lab 3: retrieval-augmented answers" after the baseline: the three commands; one printed line; the table of four rows (top-k, hit rate, MRR, answer correct, tokens in, tokens out, shadow cost, compute, p50, p95, run ID; the plain row has top-k 0 and no retrieval metrics) with the model, the build, the three prompt hashes, the index version, `eval_set` and the commit; correct answers per document for the four runs; for each k the four counts of hit or miss against correct or incorrect; how many answers name a passage; the rule, the chosen top-k and the block "Configuration for Lab 4" (index version, top-k, the hashes of `rag.md` and `judge.md`, model, `eval_set`); the second judge table; the three memory numbers;
- corrected sentences: the cache sentence of the baseline section (Decision 8) and every "next Lab 3 change" in the two earlier Lab 3 sections;
- one sentence on Lab 3 in the opening paragraph;
- three scorecard rows, each with a link to its evidence: "LLM component evaluated" (the table of this section), "Prompts versioned" (`prompts/` and the hashes on every run of `landcover-answers`), "Cost and latency recorded" (the columns of the table).

`docs/design.md`:

- **5.2**: the sentences on the third prompt and on the comparison become present tense and name `prompts/rag.md` and `make answer-eval TOP_K=<n>`.
- **5.3**: a part "LLM component (Lab 3)": the baseline is the plain prompt, zero-shot; the technique is retrieval of section-bounded chunks by exact cosine search and a prompt that puts the passages before the question; the grounding rule of Decision 1 and its reason; what the model receives at serving time.
- **5.4**: a paragraph "Course experiment (Lab 3): retrieval-augmented answers" with the three runs, the rule of Decision 7 and its result, the second judge check and that its labels were blind, and the limit of 32 questions. The sentences that say k is not yet chosen and that the check will be repeated are corrected.
- **6.1**: the sentence above Figure 7; Figure 7 with the retrieval edge solid and the prompt named; Figure 8, the evaluation loop, as `docs/diagrams/lab3-evaluation-loop.svg` in the style of Figures 4 to 7: the evaluation set, retrieval and answer, the metrics with the judge, the MLflow run, and the loop over top-k 3, 5 and 10.
- **6.2**: the measured memory in "LLM choices" (Decision 9).
- **6.3**: a part "Text model (Lab 3 measurements)": the model size, the quantisation and Metal on the M4 Pro; p50 and p95 for the plain prompt and for the chosen top-k; retrieval seconds; prompt evaluation speed; one slot, so answers are sequential; the cache finding; what an API would change.
- **6.7**: a paragraph "Measured in Lab 3": tokens in and out and the shadow cost per answer for the four runs, compute seconds per answer, $0 spent, beside the 6,400 input and 800 output tokens budgeted per call; the totals stay; local inference against an API in money, latency, privacy of a public corpus and hardware.
- **7.1**: rows for an API instead of local inference, vLLM on this Mac, fine-tuning instead of retrieval, the whole corpus in the prompt (about 62,000 tokens: more than the local context, and about $0.12 per question at the Sonnet 5.5 rate), a strict grounding prompt, and Qdrant instead of pgvector.
- **7.2**: a subsection "Lab 3 retrieval-augmented answer results" with the README's table and the choice; the two sentences that point at "the next Lab 3 change" are corrected.
- **7.4**: the Lab 3 milestone in the past tense.

Sections 5.1 and 6.8 are not edited. `docs/design.uk.md` gets the same passages.

### 12. Review fixes

After the review of the finished Lab 3 branch:

- **Ranks are computed once.** `run()` calls `retrieval.evaluate` once on the rows each answer was given and passes the result to `summarise` and `results`; `scores()`, which fed the rows back through a fake search, is removed.
- **q08 accepts both documented ways.** The QGIS page describes two ways to make a value see-through: an additional no-data value and a transparent pixel entry, which `Add values from display` fills. The top-k 10 run's answer gave the second and was judged `incorrect` for differing from the reference. The reference answer names both in one sentence.
- **All runs again, one rubric.** The revised set (`add-lab3-llm-baseline` Decision 15, `add-lab3-retrieval-eval` Decision 11) and the new index version make every earlier row incomparable, so the three runs, the check of the judge on the run at top-k 10 and the choice of top-k by the unchanged rule of Decision 7 are repeated, and the README and Section 7.2 name the replaced runs.

## Risks / Trade-offs

- [The judge may read "no passage supports this" as a refusal and reject a right answer] → The check of Decision 6 is on the run with such answers, and its threshold is passed before k is chosen.
- [The labeller has seen the three printed answer metrics, so the labels are not fully blind] → No per-question verdict is read before the labels are written; the README says what was seen.
- [The model may ignore the format and cite nothing, or cite a number above k] → The run records the numbers as written, `cited_answers` counts only numbers in range, and the README reports the count. Nothing depends on the line for the answer metric.
- [A passage from a dataset paper may override the export contract, as with the code of bareland] → Each passage names its document, the prompt says that datasets do not describe this service's export, and the per-document table shows the six `export-contract` questions.
- [The permissive rule lets the model answer wrongly with confidence where a strict rule would refuse] → The answer says when no passage supports it, the judge counts a wrong value as incorrect, and Section 7.1 names the strict prompt as the alternative.
- [With 32 questions the rule may choose k on noise] → The rule treats two questions as no difference and takes the cheaper value; the README gives the counts, not only the share.
- [Homebrew may have upgraded the server] → Decision 5 compares the build before the runs and repeats the baseline if it differs.
- [Latency at k = 10 is about twice that at k = 5] → It is a column of the table and an argument of Section 6.3; the rule prefers the smaller k.
- [Editing Section 6.3 or 6.7 by mistake under the wrong heading could touch 6.8] → The integration task rebuilds the index and requires version `56be0057b30e`.

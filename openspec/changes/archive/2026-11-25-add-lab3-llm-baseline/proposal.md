# Proposal

## Why

Lab 3 (step 3) requires an LLM baseline logged to the Lab 2 tracking server as a run with the model identifier, the parameters, an answer metric and the hash of the prompt file, and step 6 requires tokens, cost and p50 and p95 latency for every run. The repository can measure whether the index finds a passage, but it has no text model, no prompt file and no number for whether an answer is correct. Without the answer of the model alone, the retrieval runs of the next change have nothing to be compared with.

This is the third of the consecutive Lab 3 changes. It answers the evaluation set without retrieval and judges the answers. Retrieved passages in the prompt, the comparison across top-k, and the cost and performance sections of the design document come later.

## What Changes

- Add two prompt files, `prompts/plain.md` (the answer prompt without passages) and `prompts/judge.md` (the judge prompt). Each run names both by the hash of the file.
- Add a table `[llm]` to `retrieval.toml`: the server address, the model name, temperature, the output limit and the two shadow rates. The five retrieval settings and the index version are unchanged.
- Add `make llm-server`: it downloads the model file at a pinned revision, checks its SHA-256 and starts `llama-server` on the host on `127.0.0.1:8081`.
- Add `src/landcover/answer.py` and `make answer-eval`: the command refuses a dirty working tree and a server that serves another model, sends every question of `eval/questions.toml` to the model, has the same model judge each answer against the reference answer as `correct` or `incorrect`, and logs one MLflow run with the share of correct answers, tokens in and out, compute seconds, a shadow cost, p50 and p95 latency and the number of cold calls.
- Add `eval/judge-check.toml`: the answers of the baseline run with a label for each, written by Claude without sight of the judge's verdicts and reviewed by the author. The README tables the judge's verdicts against these labels.
- Revise `eval/questions.toml` after the first baseline run (design Decision 14): every reference answer becomes one sentence that answers its question, and questions that did not say what they ask about now describe it by its properties, still without a document's name. The judge prompt states that the key fact is the direct answer and that another name for the same thing counts. The new evaluation set identifier means the three retrieval runs and the baseline run are repeated; the earlier runs are named as superseded.
- Describe the baseline in the README and in Sections 5.2, 5.4, 6.1, 6.2 and 7.2 of the design document.
- Redraw the four Mermaid diagrams of Section 6.1 as SVG Figures 4 to 7 in the style of Figures 2 and 3.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| Where the model runs | `llama-server` (llama.cpp, Metal) on the Mac host with Gemma 4 12B QAT Q4_0, the choice Section 6.2 already names. Not vLLM, which the lab names as its reference, and not an API |
| Answer metric | An LLM judge, not a rubric applied by hand: the next change needs at least four runs of 32 answers, and a command cannot wait for a person |
| Rubric | Binary. The judge sees the question, the reference answer and the model's answer and returns `correct` or `incorrect` as schema-constrained JSON at temperature 0. An answer that declines to answer is `incorrect` |
| Who judges | The same local model on the same server |
| Check of the judge | Claude labels the 32 baseline answers without seeing the verdicts; the author reviews every row. The README says so and gives the two-by-two table, not one percentage |
| Cost of a local run | Real money is $0. A run records compute seconds and a shadow cost at the Sonnet 5.5 rates of Section 6.7, $2 and $10 per million tokens in and out |

Defaults proposed here, for the author to confirm when reviewing this change:

| Topic | Default | Reason |
|---|---|---|
| Where the LLM settings live | A table `[llm]` in `retrieval.toml` | One configuration file for evaluation and for the Lab 4 service; the index version is computed from the five existing keys, so it does not change |
| Model file | Fetched by `make llm-server` from the Hugging Face revision `29d09777` and checked against its SHA-256, into the ignored directory `models/` | `brew` does not pin the server and `-hf` does not pin the file; a hash check is three lines |
| Port | 8081 | Airflow holds 8080 |
| Experiment | `landcover-answers`, run name `answer-plain`, parameter `top_k` 0 | The retrieval-augmented runs of the next change go to the same experiment, so the baseline is a row of the same table |
| Judge agreement | Fewer than 29 of 32 verdicts equal to the labels means the judge prompt is revised and the run repeated | Stated before the number is known |
| A second judge model | Not built. The judge uses `[llm]` | No other judge exists yet; a `[judge]` table is added when the check fails |
| Revised evaluation set | Settled after the first run: revised inside this change, reference answers rewritten to one sentence without a new field, the rule against document names kept | The lab requires questions that ask for a thing by its properties; the first run showed ambiguous questions and multi-fact references that the judge read as required |

## Capabilities

### New Capabilities

- `answer-evaluation`: the versioned prompt files and their hashes, answering the evaluation set through the configured text model, the judged answer metric and the check of the judge, tokens, cost and latency of a run, and the tracked run with its lineage.

### Modified Capabilities

None. `experiment-tracking`, as narrowed by `add-lab3-retrieval-eval`, already asks every run for its parameters, scores and `git_commit` and lets a run that reads no training data identify what it read in the way its own capability states.

## Impact

- New files: `prompts/plain.md`, `prompts/judge.md`, `src/landcover/answer.py`, `tests/test_answer.py`, `eval/judge-check.toml`, `docs/diagrams/lab2-data-layers.svg`, `docs/diagrams/lab2-airflow-dag.svg`, `docs/diagrams/lab2-tracking-registry.svg`, `docs/diagrams/lab3-retrieval.svg`.
- Changed files: `retrieval.toml` (table `[llm]`), `Makefile` (targets `llm-server` and `answer-eval`), `.gitignore` (`models/`), `eval/questions.toml` (revised set), `tests/test_retrieval.py` (one-sentence reference answers).
- Repeated runs: the three `landcover-retrieval` runs at top-k 3, 5 and 10 on the revised set; the README and Section 7.2 replace their table.
- Changed documents: `README.md` (section "Lab 3: LLM baseline"), `docs/design.md` (the Lab 3 paragraph of 5.2, a paragraph in 5.4, the Lab 3 subsection of 6.1 and its four diagrams, which become SVG Figures 4 to 7, a note in 6.2 and a table in 7.2), and the same passages of the local, ignored `docs/design.uk.md`. Sections 5.1 and 6.8 are not edited, so the index version does not change.
- Host: `llama.cpp` installed with Homebrew, a 6.98 GB model file under `models/`, port 8081 on the loopback interface.
- Running stack: one run in a new MLflow experiment `landcover-answers`. The index and the database are not read.
- Dependencies: none added to `pyproject.toml`. The client is the standard library; the command needs neither the group `rag` nor the group `nn`.
- Out of scope: the retrieval-augmented prompt and its runs, the table across top-k with the answer metric, the choice of top-k, a second judge model, a judge check on a retrieval run, an API client, vLLM, a container for the text model, the Lab 4 text service, Sections 5.3, 6.3, 6.7 and 7.1, the scorecard rows and the `lab-3` tag.

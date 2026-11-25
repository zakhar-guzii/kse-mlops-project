# Design

## Context

See [proposal.md](proposal.md) for motivation, scope and the decisions settled with the author. Section numbers without a file name refer to `docs/design.md`.

Facts checked for this design on 2026-11-25:

- The course Mac is an Apple M4 Pro with 24 GiB of memory and 285 GiB of free disk. Homebrew is installed and offers the formula `llama.cpp`; `llama-server`, `ollama` and `vllm` are not installed. The environment holds no API key.
- Listening ports of the stack: 8080 (Airflow), 5001 (MLflow), 5433 (PostgreSQL), 9000 and 9001 (object store). macOS holds 5000 and 7000.
- The Hugging Face repository `google/gemma-4-12B-it-qat-q4_0-gguf` is not gated. Its revision is `29d097773436b69ff9feafd636ab4cf873786537`; the file `gemma-4-12b-it-qat-q4_0.gguf` has 6,975,879,296 bytes and SHA-256 `93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b`. The repository also holds a vision projector, which this change does not use.
- The server documentation of llama.cpp (`tools/server/README.md`) states: `POST /v1/chat/completions` returns `usage` with `prompt_tokens`, `completion_tokens` and `prompt_tokens_details.cached_tokens`, and accepts `response_format` of type `json_schema`; `GET /v1/models` returns one model whose `id` is the alias or the path of the file; `GET /props` returns `build_info`; `-hf` takes a repository and a quantisation, not a revision. Not confirmed there and checked in task 1.2: the flag `--alias`, the request field `cache_prompt` on the chat endpoint, whether `prompt_tokens` includes cached tokens, and whether the model's chat template produces reasoning text.
- `retrieval.load_config` returns only the five keys of `CONFIG_KEYS`, and `index_version` is computed from them, so a table added to `retrieval.toml` changes neither. `retrieval.load_questions` returns the questions and `eval_set`; the set has 32 questions and reference answers of one or two sentences.
- `landcover.train.git` is the helper that `landcover.retrieval` already uses for the dirty-tree rule. `mlflow` and `numpy` are main dependencies. `make train MODEL=rf` imports `landcover.train` without the group `nn`.
- `.gitignore` has no entry for model files. CI has no text model.

Smoke requests of task 1.3 on 2026-11-25, `llama-server` 1.0.0 from Homebrew (`build_info` `b12359-b1b770d90`), the model file hash-checked and served as `gemma-4-12b-it-qat-q4_0`:

- `--alias` sets the `id` of `GET /v1/models`; `GET /props` returns `build_info`.
- A chat request returns `usage` with `prompt_tokens`, `completion_tokens` and `prompt_tokens_details.cached_tokens`. The same request again reports 33 of 38 prompt tokens cached and the same `prompt_tokens`, so `prompt_tokens` includes cached tokens. With `cache_prompt: false` it reports 0 cached tokens, so the field works on the chat endpoint.
- Without further fields the chat template produces reasoning: the answer's `content` was empty, the text went to `reasoning_content`, and the call ended by `length` at 256 tokens. With `reasoning_effort: "none"` the same request answered in 63 tokens with `finish_reason` `stop` and no reasoning text (Decision 4).
- With `response_format` of Decision 5 and `reasoning_effort: "none"`, the content parses as an object with `reason` and `verdict`.

## Goals / Non-Goals

**Goals:**

- One command that a reviewer with the stack and the server up reruns, and that needs no dependency group and no network.
- The server is an address and a model name in the configuration: the code speaks the OpenAI chat completions protocol and nothing specific to one server except one optional request field.
- Every number of the run comes from a plain function that the tests drive with a fake model.
- The same module answers with retrieved passages in the next change by adding a prompt file and a top-k argument.

**Non-Goals:**

- A retrieval-augmented prompt, a call to `retrieve`, a sweep.
- A client library, streaming, retries, concurrency, a second server or a second model.
- A container for the text model, starting or stopping the server from the evaluation command.
- Code that measures memory, electricity or GPU load.
- Bit-identical answers across server builds.

## Decisions

### 1. The text model is a host process started by `make llm-server`

```make
LLM_REPO = https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf/resolve/29d097773436b69ff9feafd636ab4cf873786537
LLM_FILE = models/gemma-4-12b-it-qat-q4_0.gguf
LLM_SHA256 = 93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b
```

The target downloads the file to `$(LLM_FILE).part` with `curl -L --fail -C -` (which resumes a partial file), checks it with `shasum -a 256 -c`, renames it, and then runs in the foreground:

```
llama-server -m models/gemma-4-12b-it-qat-q4_0.gguf --alias gemma-4-12b-it-qat-q4_0 \
    --host 127.0.0.1 --port 8081 --ctx-size 8192 --parallel 1
```

The file is a Make prerequisite, so later starts skip the download. `models/` is added to `.gitignore`. A context of 8,192 tokens holds the largest prompt of the next change (about 1,500 tokens of passages at top-k 10) and keeps the context memory small; the model's own default is far larger. One slot makes the prefix cache behave the same in every run. Port 8081 is used because Airflow holds 8080.

The server program is installed with `brew install llama.cpp`, which gives the current build, not a pinned one. The run records the build the server reports (Decision 8) and the README states the build of the reported run.

Alternatives considered: `llama-server -hf <repository>` downloads the file itself, but takes no revision and checks no hash, so a re-upload would change the model under an unchanged name. vLLM, the lab's reference, has no GPU on this Mac: it runs in Docker on the CPU from an image built locally, with a model of 0.5 to 1.5 billion parameters. vLLM on Colab L4 keeps the 12B model but its address lives as long as a notebook session, and Lab 4 calls it during the demonstration. An API needs a key from every reviewer and money per run. Because the client of Decision 4 speaks the common protocol, each of these is later a change of `base_url` and `model`.

### 2. A table `[llm]` in `retrieval.toml`

```toml
[llm]
base_url = "http://127.0.0.1:8081/v1"
model = "gemma-4-12b-it-qat-q4_0"
temperature = 0.0
max_tokens = 256
judge_max_tokens = 200
shadow_usd_per_mtok_in = 2.0
shadow_usd_per_mtok_out = 10.0
```

The module reads the table with `tomllib` and stops on a missing key, as `load_config` does. It holds no default for any value. The two rates are those of Sonnet 5.5 in Section 6.7; they are configuration because the cloud model of the design may change.

The model name appears a second time, as `--alias` in the Makefile, because the launcher has to name what it starts. The guard of Decision 7 fails when the two differ.

Alternative considered: a separate `llm.toml`. Lab 4 hands the service one configuration, and the lab asks for one file.

### 3. A prompt file is the whole user message

`prompts/plain.md` contains the placeholder `{question}`; `prompts/judge.md` contains `{question}`, `{reference}` and `{answer}`. The text sent is the file with each placeholder replaced by `str.replace`, as one message of role `user`. No system message is used: Gemma's chat template has no separate system role, and one message keeps the whole prompt in the file. The instruction comes first and the inputs last, so consecutive calls share a prefix, as they will in serving.

The hash of a prompt is the first 12 hexadecimal digits of the SHA-256 of the file's bytes, the form of `eval_set` and `doc_version`. Filling a prompt raises when a placeholder it was given is not in the file.

Content, drafted while the change is applied and read by the author:

- `plain.md`: the reader is a GIS specialist who uses a land-cover export package; answer in English in at most three sentences; give the specific value or name asked for; say that you do not know instead of guessing. It names no document and holds no fact of the corpus.
- `judge.md`: the answer is `correct` when it states the fact of the reference answer and does not contradict it; extra true detail is allowed; a different value, a missing key fact, a refusal or "I do not know" is `incorrect`. Wording and length do not matter. The judge writes one sentence of reason, then the verdict. After the first run (Decision 14) it also states that the key fact is the direct answer to what the question asks, that detail the question does not ask for is not required, and that another name for the same setting, method or value is the same fact.

Alternative considered: `str.format` fails on the braces of a JSON example inside a prompt.

### 4. The client is one function over the standard library

`chat(llm, content, max_tokens, **extra)` posts `model`, one user message, `temperature`, `max_tokens`, `seed` 0, `reasoning_effort` `"none"` (the fallback of the Risks: task 1.3 found that Gemma 4's chat template otherwise spends the output limit on reasoning text) and the extra fields to `<base_url>/chat/completions` with `urllib.request` and a timeout of 120 seconds. It returns the text, `finish_reason`, `prompt_tokens`, `completion_tokens`, `cached_tokens` (0 when the server does not report it) and the seconds the call took, measured by the client with `time.perf_counter`.

Latency is the client's wall clock, not the server's `timings`, because that is what the Lab 4 service will see and because `timings` exists only in llama.cpp. A failed call raises and the command logs nothing; a run with 31 answers would not be comparable with the next.

Alternative considered: the `openai` package is a dependency for one POST request.

### 5. Answers first, then verdicts

The command sends the 32 answer calls in the order of the set and then the 32 judge calls. Alternating them would put the judge prompt into the server's single slot before each answer, so every answer call would start without a cached prefix and the latency would describe the evaluation, not the service.

The judge call adds `response_format` of type `json_schema` with the schema `{"reason": string, "verdict": "correct" | "incorrect"}`, both required, and uses `judge_max_tokens`. The text is parsed with `json.loads`; anything else than the two verdicts raises with the question's identifier. The reason is kept for the author's review of disagreements.

### 6. One cold call in every run

The first answer call sends `cache_prompt: false`, so the server evaluates its whole prompt whatever it served before. The other calls leave the cache on. The metric `cold_calls` is the number of answer calls with `cached_tokens` 0, and `results.json` holds the value per question.

Without retrieval the shared prefix is the instruction of `plain.md`, well under a hundred tokens, so the cache changes the latency little here. The rule is set now because the prompt of the next change carries passages.

`cache_prompt` is the one field that only llama.cpp knows. A server that rejects unknown fields needs it removed; the comment at that line says so.

### 7. Two guards before the first call

The command stops before it sends a question when:

- `git status --porcelain` is not empty, with the rule and the helper of `make retrieval-eval`;
- `GET <base_url>/models` fails, or the `id` it returns differs from `model` in the configuration. The message names `make llm-server` in the first case and both names in the second.

`build_info` is read from `GET /props` at the server's root. When that request fails, as it would against another server, the build is recorded as `unknown`.

### 8. What a run holds

| Kind | Content |
|---|---|
| Experiment | `landcover-answers`. The retrieval-augmented runs of the next change go here too |
| Run name | `answer-plain` |
| Parameters | `llm_model`, `llm_server_build`, `temperature`, `max_tokens`, `top_k` (0), `judge_model`, `judge_max_tokens`, `questions`, `shadow_usd_per_mtok_in`, `shadow_usd_per_mtok_out` |
| Tags | `git_commit`, `eval_set`, `prompt_hash`, `judge_prompt_hash` |
| Metrics | `answer_correct`, `tokens_in`, `tokens_out`, `compute_s`, `shadow_cost_usd`, `latency_p50_s`, `latency_p95_s`, `cold_calls`, `judge_tokens_in`, `judge_tokens_out` |
| Artifact | `results.json`: per question the `id`, the answer, `finish_reason`, the verdict and its reason, `prompt_tokens`, `completion_tokens`, `cached_tokens` and `seconds` |

`tokens_in`, `tokens_out` and `compute_s` are sums over the answer calls. `shadow_cost_usd` is `tokens_in` × the input rate + `tokens_out` × the output rate, per million; the cost of one request is that sum divided by `questions`. The percentiles are `numpy.percentile` with linear interpolation over the answer calls. The run has no `index_version` tag, because it reads no index, and no `data_version` tag.

`top_k` 0 is a parameter of the run, not a value in a file, so the single-configuration rule of the index holds.

The command prints one line, for example:

```
run 1a2b3c4d: plain, 32 questions, correct 0.281, tokens 2140 in / 1870 out, p50 1.9 s, p95 3.4 s, shadow cost $0.0230 (prompt 3f2a9c1d7e5b, judge 8b4e2a6c0d1f, questions 0174445a4974)
```

### 9. Metrics are a pure function

`answer_all(questions, ask)` and `judge_all(questions, answers, ask)` take a function from prompt text to the record of Decision 4, and `summarise(records, verdicts, judge_records, llm)` returns the metrics of Decision 8. None of them opens a connection, so the tests pass a fake `ask` with known tokens, seconds and verdicts. `run()` builds the real `ask` from the configuration, applies the guards and logs the run; it is the only function that needs the server and MLflow.

The module imports `load_questions`, `sha256`, `ROOT` and `CONFIG` from `landcover.retrieval`, and `git` and `mlflow` inside `run()`.

### 10. The check of the judge

After the run:

1. The answers are taken from the run's `results.json` as `id` and answer text, without the verdict and the reason.
2. Claude labels each answer `correct` or `incorrect` from the question, the reference answer and the answer, by the rubric of `judge.md`.
3. The labels are written to `eval/judge-check.toml`, and only then the judge's verdicts are copied in beside them:

```toml
run_id = "<run>"

[[answers]]
id = "q01"
answer = "<the model's answer>"
judge = "incorrect"
label = "incorrect"
```

4. The author reads every row, the rows where `judge` and `label` differ first, and changes a label that is wrong.
5. The README gives the four counts (judge `correct` or `incorrect` against label `correct` or `incorrect`), the run, the model that labelled and the sentence that the author reviewed the labels.

The rule set before the number is known: when fewer than 29 of the 32 verdicts equal the labels, `judge.md` is revised and committed, the command is run again, labels are kept for answers whose text is unchanged and written for the others, and the earlier run is named in the README as superseded.

The check is on answers that are mostly wrong, so it says little about answers the judge should accept: a judge that rejects everything would agree with most labels. The table shows this where one percentage would hide it, and the next change repeats the check on a retrieval-augmented run.

Alternative considered: the author labels alone. The author asked for drafted labels to review, the way the question set was produced.

The first run, `736634076b744485a8c19f690101c03c`, agreed with the labels on 27 of 32 before the author's review. Its disagreements and the reading of its references led to Decision 14, and it is named in the README as superseded. The labels of the run on the revised set are not blind: Claude had seen the verdicts of an unlogged preview with the same answers except q30, and the author chose to keep Claude as the labeller and to state this in the README and in Section 5.4 rather than label alone.

### 11. Memory is measured once, by hand

After the run, with the server still up, `footprint $(pgrep -x llama-server)` gives the physical footprint of the process, which on Apple Silicon includes the memory of the Metal buffers. The number goes into the README. Section 6.3 takes it in the last Lab 3 change, together with the measurement next to Minikube that Section 6.2 promises.

### 12. Tests

`tests/test_answer.py`, with no model, no server and no network:

- prompts: the hash follows the file's content and has 12 digits; each committed prompt contains its placeholders; filling raises for a placeholder the file lacks;
- configuration: `[llm]` has every key, and `retrieval.load_config` and the index version are unchanged by the table;
- metrics, through the functions of Decision 9 with a fake `ask`: 8 of 32 correct gives 0.250; 1,000,000 and 100,000 tokens at 2 and 10 give 3.00; known latencies give the expected p50 and p95; judge tokens are summed apart; `cold_calls` counts the calls with no cached tokens; only the first answer call asks for a cold prompt;
- verdicts: a verdict outside the two values raises and names the question;
- judge check, skipped until `eval/judge-check.toml` exists: every question of the set has exactly one row with `judge` and `label` in the two values, and the four counts in the README equal the file's.

The HTTP call, the guards and the MLflow call have no branch worth a mock; the smoke request of task 1.2 and the real run check them.

### 13. Documentation

`README.md` gains "Lab 3: LLM baseline" after the retrieval evaluation: `brew install llama.cpp`; `make llm-server` with the size of the first download, the address and the hash check; `make answer-eval` with its printed line; one table row (answer metric, tokens in and out, shadow cost, compute seconds, p50, p95, run ID) with the model, the server build, both prompt hashes, `eval_set` and the commit; the footprint of the server; that the run cost no money and what the shadow cost is, including that Gemma and Claude count tokens differently; how many of the six `export-contract` questions were judged correct; the judge table of Decision 10. No scorecard row is added: the three Lab 3 rows are claimed when the retrieval-augmented runs exist.

`docs/design.md`:

- **5.2**: in the Lab 3 paragraph, the sentences on prompt versioning, the plain-prompt baseline and cost and latency become present tense for the plain and judge prompts and name `prompts/`, `make answer-eval` and Section 7.2. The retrieval-augmented prompt and the comparison stay planned.
- **5.4**: a paragraph "Course experiment (Lab 3): answers" with the baseline, the binary rubric, the judge and its model, the check of Decision 10 and its limit, and what a run records.
- **6.1**: under "Lab 3 retrieval pipeline", an edge from the question to the LLM box for the plain prompt, the LLM box labelled with the model and `make answer-eval`, and the sentence above the diagram. The edge from retrieve to the LLM stays marked as the next change. The four Mermaid diagrams of Section 6.1, this one and the three of Lab 2, are redrawn as SVG files in the style of Figures 2 and 3 and become Figures 4 to 7, so the section uses one style; their nodes and edges do not change.
- **6.2**: a note "Lab 3 text model" after "Lab 3 index": the command, the address, the pinned file and why the server runs on the host.
- **7.2**: a subsection "Lab 3 answer results" with the README's row.

Sections 5.1 and 6.8 are not edited; they are the document `export-contract`. Sections 5.3, 6.3, 6.7 and 7.1 wait for the last Lab 3 change, which has the cost of the chosen configuration. `docs/design.uk.md` gets the same passages.

### 14. The evaluation set is revised once, after the first run

The first run (0.312 correct) and its check showed three faults of the set, not of the model:

- questions that do not say what they ask about ("the segmentation benchmark", "one 512 by 512 tile"), so the answer depends on guessing the source;
- questions on the GIS page whose reference expects that program's interface names, while the question does not say which program is meant, so a correct answer in another program's terms is `incorrect`;
- reference answers with two or three facts joined by a semicolon, an example or a condition, which the judge reads as required.

The rule of Lab 3 that a question asks for a thing by its properties, not its name, stays, and so does the test that enforces it. The revision, drafted by Claude and read by the author row by row:

- every reference answer is one sentence with the direct answer to the question, no semicolon, and no example or condition the question does not ask for; an interface name goes in parentheses after the function it names;
- a question that did not say what it asks about describes it by properties a user of the export would know: the mask this service exports, the free desktop GIS the mask is opened in, the French national aerial imagery the model was trained on, the global aerial land-cover benchmark it was trained on, the US farm aerial imagery;
- identifiers, sources, evidence quotes and the 6/8/8/6/4 distribution stay; a question that cannot be repaired is replaced by one on the same section.

A test of `tests/test_retrieval.py` fails on a reference answer with a semicolon or more than one sentence. The new `eval_set` makes the three retrieval runs and the baseline incomparable with their predecessors, so all four are repeated; the README and Section 7.2 replace the retrieval table and the answer row and name the earlier runs as superseded. `plain.md` is not changed: its hash marks the baseline, and a low score without retrieval is the expected result.

Alternative considered: a field `key_fact` beside the answer, sent to the judge instead of it. It adds a placeholder and code for what a shorter reference does.

### 15. Review fixes

After the review of the finished Lab 3 branch:

- **The server is built at a pinned tag.** `brew install llama.cpp` cannot give build `b12359-b1b770d90`, the build of every reported run. A Make target clones `https://github.com/ggml-org/llama.cpp` at tag `b12359` into the ignored `models/llama.cpp`, checks that the commit is `b1b770d90`, and builds `llama-server` with CMake and Metal; `make llm-server` depends on it. The clone is partial (`--filter=blob:none`), not shallow: llama.cpp derives its build number from the commit count, which a shallow clone would make 1. CMake and the Xcode command line tools are prerequisites.
- **The model file is checked on every start.** The recipe of `llm-server` checks the SHA-256 of the final file before it starts the server, not only of the download. Another valid GGUF under the same name would otherwise be served under the configured alias and pass the client's model check. Hashing 6.98 GB adds some seconds to each start.
- **Unknown cache telemetry is not a cold call.** When the server reports no `cached_tokens`, the record holds `null`, and `cold_calls` is not logged unless every call reports it.
- **A prompt is filled in one pass.** `fill` replaces the placeholders of the template in one substitution over the original text, so a question or a reference answer that contains `{answer}` is sent as written.
- **The judge rejects a false addition.** `prompts/judge.md` gains the rule that an answer which adds a false statement about what the question asks is `incorrect` even when it states the key fact. The top-k 10 run's q03 named the right class and then said that the dataset counts parking lots as road; the dataset counts only the driveways between them as road.
- **The labels are required.** The judge-check test fails when either labels file is missing or when its identifiers differ from those of the set, instead of skipping.
- **The set is revised a second time.** q25 and q26 asked about "the data the model was trained on", which fits both the dataset's published experiment and this project's model, whose crosswalk ignores more codes and whose split is by whole batch. They now ask about the published experiment. With the second sources and q29 of `add-lab3-retrieval-eval` Decision 11 and q08 of `add-lab3-rag-answers` Decision 12, this gives a new `eval_set`, so the baseline, the three retrieval-augmented runs and both checks of the judge are repeated with one judge prompt.

## Risks / Trade-offs

- [The lab names vLLM and Unsloth and does not name llama-server] → The author accepted this. The client speaks the protocol vLLM serves, so the lab's reference is a change of two configuration values, and Section 7.1 argues the choice in the last Lab 3 change.
- [The model judges its own answers and may accept its own mistakes] → The judge compares with a reference answer and does not rate quality, every compared run is answered by the same model, and Decision 10 checks the verdicts against labels.
- [The check sample is mostly wrong answers] → The README gives four counts, and the check is repeated on a retrieval-augmented run.
- [The author reviews labels that Claude drafted and may follow them] → Claude labels without the verdicts, the author reads the disagreements first, and the README says who did what.
- [The chat template may spend output tokens on reasoning, or an answer may be cut at 256 tokens] → Task 1.2 looks for reasoning text in a smoke answer and adds `reasoning_effort: "none"` to the request if there is any; `results.json` holds `finish_reason`, and the run task fails on an answer that ended by length.
- [`cache_prompt` may be ignored on the chat endpoint] → Task 1.2 checks it. If it is ignored, the README tells the reader to restart the server before a run and the task verifies a cold first call that way.
- [Temperature 0 does not make two server builds give the same text] → The run records the build and keeps every answer; the README reports one run and its build.
- [The server build is whatever Homebrew installs] → Recorded per run. A pinned build would mean compiling llama.cpp in the repository.
- [The shadow cost is not what Bedrock would bill] → It is named a shadow cost everywhere, the tokens are logged beside it, and the README states the tokenizer difference.
- [The model name is in the Makefile and in the configuration] → The guard of Decision 7 fails when they differ.
- [A 7 GB download and a model in memory beside Docker on 24 GiB] → An interrupted download resumes when the target is rerun, and the hash is checked before the file gets its final name; the footprint is measured and reported.

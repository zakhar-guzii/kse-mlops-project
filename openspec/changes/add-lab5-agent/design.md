# Design

## Context

See proposal.md for the motivation and the decision tables, and the two specifications under `specs/` for the required behaviour. Current state that shapes the approach:

- **Text model server (`make llm-server`).**
  - llama.cpp `b12359` (`b1b770d90`) serves `gemma-4-12b-it-qat-q4_0` on `127.0.0.1:8081` with `--ctx-size 8192 --parallel 1`, so one request has the whole context.
  - A request whose prompt exceeds the context is rejected with `exceed_context_size_error`, not truncated.
  - The server re-evaluates a prompt that shares only a prefix with the previous one, because of Gemma 4's sliding-window attention, at about 275 tokens per second (Section 6.3). Each step of a run therefore pays for the whole conversation again.
  - Read in the source, not run: Jinja templates are on by default for the server (`common/common.h`), a Gemma 4 handler parses native tool calls (`common/parsers/gemma4.cpp`), and it is chosen because the template inside the pinned model file contains `'<|tool_call>call:'`. In that handler a `response_format` schema is applied first and tools are then ignored, so the two cannot be combined in one request.
  - No server, cluster or Docker daemon was running when this was written. Nothing here was measured live.
- **Client (`answer.chat`).**
  - It sends one user message and returns the text, the finish reason, the token counts and the seconds. Its `**extra` is merged into the request body last, so `messages=` and `response_format=` replace and add fields without a change to the function.
  - It fixes `seed` 0 and `reasoning_effort` `none`, takes the temperature (0.0) from `retrieval.toml`, and waits at most 120 s.
  - `JUDGE_FORMAT` is a `json_schema` response format. `judge_all` raises on a reply it cannot parse, and every Lab 3 answer run completed, at least 128 judged answers.
  - `answer.server_build` reads the server's build and raises when the server is down or serves another model.
- **Retriever.** `retrieval.retrieve(conn, question, k, embed)` returns the k nearest chunks with `chunk_id`, `doc_id`, `doc_version`, `locator`, `text` and `distance`. `check_index` fails unless the index matches the committed corpus and settings. `answer.passages(rows)` formats rows as `[n] doc_id, locator` and the text, numbered from 1. The Makefile already sets `WAREHOUSE_DSN` to `localhost:5433`, where `make cluster` forwards the cluster's PostgreSQL. The embedding model needs the group `rag`.
- **Sizes.** A passage costs 187 prompt tokens (Lab 3: 2,059 tokens at top-k 10 against 1,124 at top-k 5). With its header a passage is at most 773 characters, 650 on average, over the 575 chunks of index `5570e99ba60e`.
- **Prediction endpoint.**
  - `POST /predict` takes the image bytes and the header `X-Source-Id` and answers in one request with `request_id`, `model_name`, `model_version`, `image_commit`, `width`, `height`, `valid_px`, `features`, `class_shares`, `dark_warning` and the base64 `mask`.
  - It answers 503 with outcome `unavailable` while its model is not loaded, 4xx with outcome `invalid` for an unusable image and 500 with outcome `error` when the prediction or the log write fails.
  - A 512×512 tile takes 1.3 s (Section 7.3).
- **Drift report and alerts.**
  - The report's current window is every `ok` row whose source ID does not start with `reference/`. A window with fewer than 50 rows publishes no distance, so `BrightnessDrift` cannot fire on it.
  - Labels join on source IDs of the form `replay/D017-2021/<tile>/q<n>`.
  - `PredictErrors` fires on three `error` outcomes within an hour. `MLServiceUnavailable` fires when the Service has no ready pod for five minutes.
- **Tiles.** `data/raw/D017-2021/images/` holds 16 GeoTIFF tiles of 512×512 after `make sample`. `scripts/smoke.py` already posts one of them whole.
- **Clean tree.** `train.clean_head` refuses any line of `git status --porcelain`, untracked files included. `make answer-eval`, `make retrieval-eval` and `make train` use it.
- **Environment.** The Makefile exports `MLFLOW_TRACKING_URI` into every recipe. The agent's guarantee towards the registry is therefore that it has no client for it, not that the address is absent.
- **Design document.** Section 6.4 already states four attempts and the four stop reasons. Section 6.7 budgets five model calls per assistant task. Section 6.8, which is not edited, states a shadow price of $0.01 per minute.

## Goals / Non-Goals

**Goals:**
- One command on the host that answers a task with the two tools and always ends with a stated reason and a trace.
- Every bound checkable in a unit test with a scripted model and fake tools, without a server or a cluster.
- The refusal and the spent budget reproducible by a reviewer with one command each.
- No change to the services, the cluster, the text model server or the retrieval index.

**Non-Goals:**
- The evaluation set and its runner (`add-lab5-agent-eval`). `run` takes the model call, the tools and the trace folder as arguments so that the runner can call it in one process.
- Native tool calls, a framework, a third tool, a conversation across runs, or resuming a run.
- Managing the context: the conversation is only appended to.
- Saving the mask to a file, or a user-facing result package.

## Decisions

### 1. Tool selection by one JSON object per step

Each model call carries `response_format` with this schema, in the form of `JUDGE_FORMAT`:

| Field | Type | Meaning |
|---|---|---|
| `reason` | string | One sentence on why this action, written before the choice |
| `action` | string | `retrieve`, `predict`, `answer`, `cannot` or `refuse`; not restricted by the schema |
| `text` | string | The query, the tile ID, or the message to the user |

All three are required and no other field is allowed.

- **Why not native tool calls.** They need no server flag on this build, but they were not run. A final reply would be free text, so the stop reason would have to be read from prose. The handler's grammar admits only declared tool names, so a live run could never reach the allowlist check.
- **Why `action` is a free string.** The line that refuses is then in this repository and can fire in a live run. The cost is that a misnamed tool ends the run as `refused`; the evaluation will count such runs.
- **Why `reason`.** `reasoning_effort` is `none`, so this field is the model's only room to think before it chooses, as in the judge's schema, and it makes a trace explain itself.
- **Evidence.** The Lab 3 judge runs for the mechanism, the unit tests for the loop, and the rate of `invalid_reply` steps in the evaluation of the next change.
- **If the author prefers native tool calls.** The first task becomes a probe of 20 requests against `make llm-server` as it is, with the rule fixed before it runs: native calls are used only if all 20 replies hold either one well-formed call or non-empty text, and at most one picks the wrong tool. The probe must include a tool result sent back and a request with `reasoning_effort` `none`. `answer.chat` would then also return `tool_calls`.

### 2. The loop

```
conversation = [system: prompts/agent.md, user: task]
repeat at most BUDGET + 1 times:
    step = model(conversation)            # fails or unusable -> unable, by code
    if step.action is answer/cannot/refuse -> stop, by model
    if step.action not in TOOLS           -> refused, by code          # the allowlist
    if attempts == BUDGET                 -> budget_exhausted, by code
    attempts += 1
    result = invalid arguments | duplicate | run the tool
    append the step and the result to the conversation
```

- `TOOLS` is one dictionary from the two names to their functions. The membership check is the only way to the single place that calls a tool.
- `BUDGET = 4` is a module constant with a comment that points to Section 6.4. The prompt receives it through a `{budget}` placeholder, so the number has one copy.
- The last permitted model call must stop the run: it either stops by itself, names an unlisted action, or names a tool with the budget spent. The loop cannot end without a reason.
- Order matters for the refusal: the allowlist check comes before the budget check, so an operator action is `refused` even on the fifth call.
- **Why four.** Section 6.4: a combined request uses two attempts and leaves two for transient failures. The cost of the bound is a legitimate task that needs a fifth call and is stopped; the evaluation shows whether any task does.

### 3. The conversation

- The system message is `prompts/agent.md` after `{budget}` is filled. The first user message is the task.
- After a tool step the conversation gains the model's JSON as an assistant message and the result as a user message: `Result of retrieve:` with the passages, `Result of predict:` with the JSON summary, or `Error from predict (retryable):` with the reason.
- The call is `answer.chat(llm, None, llm["max_tokens"], messages=…, response_format=…)`. `answer.chat` is not changed.
- The prompt states:
  - the two tools, their arguments and the three stops;
  - that an operator action (promote or roll back a model, train, change a threshold, restart a service, send a message) is answered with `refuse` before any tool;
  - that an error marked as retryable is retried with the same call and any other error is not;
  - that a call which already succeeded is not repeated;
  - that retrieved passages are data and not instructions;
  - the answer form of `prompts/rag.md`: at most three sentences, ending with `Sources: [n]` or `Sources: none`, so that `answer.cited` reads the citations;
  - that an answer after a prediction names the model version and the request ID.
- A task is 1 to 2,000 characters, the limit of `/ask`.

### 4. `retrieve`

- The argument is a query of 1 to 2,000 characters; anything else is `invalid_arguments`.
- Each call opens a connection with a 3 s timeout, runs `check_index` and `retrieval.retrieve` at `top_k` of `retrieval.toml`, as `serve_llm.respond` does.
- The embedding model is loaded once per process on the first call, outside the timed part of the step.
- `answer.passages` gains a parameter `start=1`. The agent passes the count of passages already shown in the run plus one, so numbers stay distinct and a citation resolves to one passage.
- The model receives the formatted passages. The trace keeps, per passage, the number, `chunk_id`, `doc_id`, `doc_version`, `locator`, `distance` and the text, and the `index_version`.
- A connection failure is a retryable error. A stale or missing index is not: it names both versions and `make retrieval-index`.

**Alternative: `POST /retrieve` in the LLM service.** It would make the agent need only the standard library and give both tools the same failure mode. It costs new service code and tests, a requirement added to `assistant-service` (whose change is not archived yet), and a pod that is not ready whenever the text model server is down although retrieval does not need it. Add it when the agent moves into the cluster or a second client needs retrieval.

**Context budget.** Estimates from the measured 187 tokens per passage; about 400 tokens for the prompt, 40 for a typical task and 60 per step:

| Conversation before the last call | Tokens |
|---|---:|
| retrieve + predict | 2,700 |
| retrieve + predict + two failed attempts | 2,900 |
| two retrievals + predict | 4,600 |
| three retrievals + predict | 6,500 |
| four retrievals | 8,200 plus the reply, over 8,192 |

Ten passages are kept because Section 5.4 chose 10 by its rule and `retrieval.toml` is the only copy of the value. Four successful retrievals with four different queries overflow; the server rejects that call and the run ends `unable`, stopped by the code, with the server's message.

### 5. `predict`

- The argument is `D017-2021/<tile>`, where `<tile>` is the stem of a file in `data/raw/D017-2021/images/`. The set is read from that folder. Anything else is `invalid_arguments`; with the folder missing the error names `make sample`.
- The tool posts the tile file's bytes to `<ml>/predict` with `X-Source-Id: agent/<run id>/D017-2021/<tile>` and a 30 s timeout, more than twenty times the measured 1.3 s.
- The model receives a JSON summary: `request_id`, `model_name`, `model_version`, `width`, `height`, `valid_px`, `class_shares`, `brightness` and `dark_warning`. That is about 200 tokens.
- The trace keeps the same summary plus `mask_bytes` and `mask_sha256`. The mask itself stays in `serving.predictions` under the request ID.
- **Why this batch.** Its tiles are public, the smoke request already uses one, and the final batch `D073-2022` stays untouched. The list is not in the prompt: the task names the tile and the code checks it.
- **Effect on monitoring.** An `agent/` row is served traffic and counts in its window, like `bench/` and `smoke` rows. Agent runs alone stay under 50 rows per window and publish no distance. The label join never matches an `agent/` ID. The README tells the reader not to run the agent during `make drift-demo`, whose two distances are quoted as evidence.

### 6. Tool errors

| Failure | Status | Retryable |
|---|---|---|
| Connection refused, timeout, HTTP 5xx, database unreachable | `error` | yes |
| HTTP 4xx, stale index | `error` | no |
| Argument rejected before the call | `invalid_arguments` | no |
| Same tool and argument as an earlier `ok` step | `duplicate` | no |

- The error text is the service's `detail` or the exception, cut to 300 characters.
- Every row of this table spends one attempt.
- The duplicate rule compares the tool name and the argument after stripping surrounding whitespace. It is the answer to "the agent keeps calling the retriever with the same query": the retriever is not called, the trace shows `duplicate`, and the budget ends a model that keeps trying.

### 7. Stop reasons

| Reason | Stopped by | When |
|---|---|---|
| `answered` | model | action `answer` |
| `unable` | model | action `cannot` |
| `unable` | code | the text model cannot be reached, rejects the request, or returns a reply that is cut off or lacks a field |
| `refused` | model | action `refuse` |
| `refused` | code | an action outside the allowlist |
| `budget_exhausted` | code | a tool named after four attempts |

- For a stop by the model the message is the model's `text`. For a stop by the code the message is written by the code: the reason, the action or the last error, and for the budget the number of attempts.
- A cut-off reply (`finish_reason` `length`) or invalid JSON is recorded as a step with status `invalid_reply`, with its tokens and cost.
- The command prints the message, then one line with the reason, who stopped, attempts, model calls, tokens, cost and the trace path. It exits 0 whenever a trace was written and 2 for a usage error, because a refusal is a correct outcome.

### 8. The trace

One file per run, `traces/<UTC time>-<run id>.jsonl`, the run ID being eight hex digits. Each record is written and flushed when it is complete.

| Record | Fields |
|---|---|
| `run` | `run_id`, `started_at`, `task`, `git_commit`, `dirty`, `mode` (`json_schema`), `model`, `server_build`, `temperature`, `seed`, `max_tokens`, `prompt_hash`, `budget`, `tools`, `top_k`, `ml_url`, `shadow_usd_per_mtok_in`, `shadow_usd_per_mtok_out` |
| `step` | `step`, `prompt_tokens`, `completion_tokens`, `cached_tokens`, `model_s`, `finish_reason`, `reason`, `action`, `text`, `status`, `cost_usd`; for a tool step also `attempt`, `input`, `output` or `error` with `retryable`, `tool_s` |
| `end` | `stop_reason`, `stopped_by`, `message`, `sources`, `tool_attempts`, `model_calls`, `tokens_in`, `tokens_out`, `seconds`, `cost_usd` |

- `status` is one of `stop`, `ok`, `error`, `invalid_arguments`, `duplicate`, `not_allowed`, `over_budget`, `invalid_reply`.
- `cost_usd` of a step is its prompt and completion tokens at the two rates of `retrieval.toml`. A step is a model call together with the tool it asked for, so no cost is empty; the tools are the project's own services and add no price of their own.
- `sources` resolves the passage numbers of an `answered` message to `doc_id`, `doc_version` and `locator`, as `/ask` does.
- A failed read of the server build is recorded as `unknown` and the run then ends `unable`; a trace exists even for that run.
- The commit comes from `git rev-parse HEAD`; `dirty` says whether `git status --porcelain` printed anything. An ad hoc run on an edited tree is allowed and marked.
- **Redaction (Section 6.5).** One function turns the endpoint's response into the summary and drops `mask`. The corpus and the tiles are public, so the task, the tile ID and the passages are kept in full.
- **Location.** `traces/` goes into `.gitignore`, because `clean_head` refuses untracked files. The three evidence traces are copied to `docs/traces/` and committed.
- **No MLflow.** The lab accepts a trace folder. The agent never imports the MLflow client, which keeps the statement "the agent makes no request to the registry" true by construction; a test asserts that importing the module leaves `mlflow` unloaded.

### 9. The deliberate failure

`make agent TASK="Segment tile D017-2021/AA-S2-9_2-7." ML_URL=http://127.0.0.1:1`

- Port 1 is closed, so every `predict` fails at once with a connection error, marked as retryable. No code is added for the failure.
- The expected trace: four `error` steps, a fifth model call that names `predict` again, and an end record `budget_exhausted` by the code.
- No request reaches the ML service: `landcover_requests_total{outcome="error"}` does not move, and neither `PredictErrors` nor `MLServiceUnavailable` can fire.
- This is also the walk-through for "the prediction endpoint is down".

**Alternatives.** Scaling the `ml` Deployment to zero is the real outage but emails the operator after five minutes. A fault flag inside the tool is code that exists only for the demonstration.

### 10. Module, command and tests

- `src/landcover/agent.py` holds the constants, the two tools, the loop, the trace writer and `main`. `run(task, ask, tools, trace_dir, …)` takes the model call and the tools as arguments, in the way `answer.answer_all` takes `ask`.
- `python -m landcover.agent TASK [--ml URL] [--traces DIR]`; `WAREHOUSE_DSN` from the environment.
- Makefile: `agent` runs it with `--group rag`, `"$(TASK)"` and the existing `ML_URL`.
- `tests/test_agent.py`, with a scripted model and fake tools:
  - a combined task ends `answered` with two attempts, and the sources resolve;
  - `refuse` as the first step ends `refused` by the model with no tool called;
  - an unlisted action ends `refused` by the code with no tool called, also on the fifth call;
  - four retryable errors and a fifth tool step end `budget_exhausted` with four attempts and five model calls;
  - an answer on the fifth call ends `answered`;
  - a repeated successful call is not run and spends an attempt, and a repeated failed call is run;
  - an unknown tile and an empty query are `invalid_arguments` and send nothing;
  - a model call that raises, and a cut-off reply, end `unable` by the code;
  - the trace has a run record, one step per reply and an end record, every step has a cost, the totals equal the sums, and no record has a key `mask`;
  - HTTP 503 and a refused connection are retryable and HTTP 400 is not, with the HTTP call stubbed;
  - importing `landcover.agent` does not load `mlflow`;
  - `prompts/agent.md` has its `{budget}` placeholder.
- `tests/test_answer.py`: `passages(rows, start=11)` numbers from 11 and the default is unchanged.

### 11. Design document and README

| Section | Addition | Appendix 2 |
|---|---|---|
| 5.5 | A bullet "Agent boundary (Lab 5)". Without a human the agent may answer from the corpus with citations, fetch a prediction for one of the 16 public tiles, which adds one request-log row, and say that it cannot. It may not change `champion`, start training or ingestion, change a threshold or silence an alert, restart or scale a service, or send any message. The boundary is the allowlist check in `agent.py`, the absence of a registry client, and the refusal before any tool. Also: what the user sees when `/predict` is down, and `agent/` added to the source prefixes of the first ten minutes | 4, 6, 12 |
| 6.1 | A subsection "Lab 5 agent loop" with `docs/diagrams/lab5-agent-loop.svg` as Figure 10, after the Appendix 3 template: task, agent with budget 4, the four stop reasons and the allowlist, the two tools with what they return, the answer or stated stop, the trace folder. A paragraph with the loop in four steps and which step stops on what evidence. A paragraph that names `/ask` as the workflow, this as the agent, and what would turn each into the other | 1, 2 |
| 6.4 | "In the course (Lab 5)" sentences in the bullets on permissions, attempts and termination: the free-string action checked in code, what counts as an attempt, the duplicate rule, five model calls, why four and what the bound costs, the stop table | 3, 4, 5 |
| 6.5 | Course traces: the file, what is kept, the mask dropped. What a trace has that the request log and the service logs lack: the task, the order, the model's reason, the tool input and output, tokens, cost, the stop reason. What a third-party tool would change: its output could not be kept in full, and the query would leave the machine | 7, 11 |
| 6.7 | A paragraph "Lab 5 agent": cost per step at the Sonnet 5.5 rates, the tokens and cost of the three evidence runs, the tools at $0. A sentence that the per-minute price in Section 6.8 predates the Lab 3 token rates and that the trace's seconds allow it to be derived | 11; the column for 10 |
| 6.9 | Rows: the model gives up or loops (budget, duplicate rule); a misnamed action is refused; four retrievals overflow the context; agent rows enter the drift window; a step re-evaluates the whole conversation | — |
| 7.1 | Rows: an agent framework; native tool calls; `POST /retrieve` | — |
| 7.4 | The Lab 5 line: the agent and its traces are built; the evaluation follows | — |

- Sections 5.1 and 6.8 are not edited. The same passages are revised in the local `docs/design.uk.md`.
- Appendix 2 questions 8, 9 and 10 are answered by `add-lab5-agent-eval`; the trace fields they need (`temperature`, `seed`, the retrieved `chunk_id`s and distances, tool errors, tokens per step) are defined here.
- README, "Lab 5: agent": what must be running, `make agent`, the tool-selection method in one sentence as the lab requires, the budget and its reason, the three commands with their printed result and links to `docs/traces/`, the link to the allowlist line, and the note on `make drift-demo`.

## Risks / Trade-offs

- **The model gives up before the budget is spent.** After one or two errors it may answer `cannot`, and the trace ends `unable`. → The prompt requires a retry of every retryable error. Task 4.2 checks the result twice. If the model still stops, revise the prompt wording and record the hash that worked.
- **A misnamed tool is a refusal.** With a free-string action, `search` instead of `retrieve` ends the run. → The prompt lists the five actions; the next change counts such runs and may restrict the field.
- **Four successful retrievals overflow the context.** → The run ends `unable` with the server's message. Lowering k would trade this rare case against the answers of every task.
- **Latency.** Every step re-evaluates the conversation: about 10 s per step with one retrieval in it, 30 to 60 s for a combined task. → Accepted for single runs. `--swa-full` is the lever if the evaluation is too slow; it changes the server command recorded in Lab 3, so it belongs to that decision.
- **A long answer is cut off.** `reason` plus the message must fit 256 output tokens, or the JSON is invalid and the run ends `unable`. → The prompt limits the answer to three sentences; Lab 3 answers took about 49 tokens.
- **Agent rows in a drift window.** One to four rows among the 128 of a replay shift its distances slightly. → The README note; the prefix makes the rows visible in the source mix.
- **Memory.** The agent loads the embedding model next to the text model server and Minikube on the 24 GiB Mac. → The model is 471 MB and loads only when a run retrieves.
- **Port-forwards die.** → Both tools then report retryable errors and the run ends with a stated reason; the README names the two forwards.
- **Fixed seed.** `answer.chat` sends `seed` 0, so two runs are identical even above temperature 0. → Not changed here; the evaluation change decides how its repeated runs differ.

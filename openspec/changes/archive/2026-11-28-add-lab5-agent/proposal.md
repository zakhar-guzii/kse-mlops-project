# Proposal

## Why

Lab 5 step 2 asks for one agent with two project tools, the Lab 3 retriever and the Lab 4 prediction endpoint, bounded by a tool allowlist, a step budget and a stop condition, with one trace that ends on the spent budget. Step 3 asks for a trace of every run: each call in order with its input, output, tokens or time, and cost. Step 1 asks the design document to name what the agent may do without a human and what it may not, and to show the agent loop. The repository has the retriever, the endpoint and a fixed retrieve-then-answer service (`/ask`), but nothing that chooses between the tools or stops with a reason.

This is the first of two Lab 5 changes: `add-lab5-agent` → `add-lab5-agent-eval`. The second adds the evaluation set, the repeated runs, the scorecard row and the `lab-5` tag.

## What Changes

- **Agent.** A new module `src/landcover/agent.py`, run from the host as `make agent TASK="…"`. It uses no agent framework and is not deployed to the cluster. For each step the text model returns one JSON object, constrained by a schema, that names an action and its text. The code runs the tool, appends the result to the conversation and asks again.
- **Two tools, one allowlist.**
  - `retrieve(query)` calls the Lab 3 retriever in the agent's process, at `top_k` of `retrieval.toml`, against the index in the cluster's PostgreSQL.
  - `predict(tile_id)` posts one of the 16 public tiles of the development batch `D017-2021` to `/predict` on Minikube. The model receives the model version, the image size, the class shares, the brightness and the request ID, never the mask.
  - An action that is neither a tool nor a stop is refused in code, and the run ends.
- **Budget.** Four tool attempts per task, counted whether the tool succeeds, fails, is given invalid arguments or repeats an earlier successful call. A run makes at most five calls to the text model.
- **Stop.** A run ends with one of four reasons: `answered`, `unable`, `refused`, `budget_exhausted`. The record says whether the model or the code stopped it.
- **Deliberate failure.** `make agent TASK="…" ML_URL=http://127.0.0.1:1` points `predict` at a closed port. Every attempt fails with a transient error, the prompt tells the model to retry such errors, and the run ends with `budget_exhausted`. No request reaches the ML service, so no Lab 4 alert fires.
- **Traces.** Every run writes one JSON Lines file under the ignored `traces/`: a run record, one record per step and an end record. Each step carries the model's tokens and seconds, the tool's input, output and seconds, and a cost at the shadow rates of `retrieval.toml`. Three traces are committed under `docs/traces/` as evidence: a completed combined task, a refusal and a spent budget.
- **Prompt.** A new `prompts/agent.md`; its hash is in every trace.
- **README.** A section "Lab 5: agent": how to run it, the tool-selection method used, the budget and its reason, and the three traces.
- **Design document.**
  - **5.5:** what the agent may do without a human and what it may not, where the code enforces it, and what the user sees when `/predict` is down.
  - **6.1:** the agent loop diagram and a paragraph that sets the agent against the `/ask` workflow.
  - **6.4:** the allowlist, the budget and the stop reasons as built.
  - **6.5:** what a course trace keeps and drops, and how a trace differs from the service logs.
  - **6.7:** cost per step; a note that the per-minute price of Section 6.8 predates the Lab 3 token rates.
  - **6.9:** the agent's risks.
  - **7.1:** the alternatives not taken.
  - **7.4:** the Lab 5 milestone, first half.

Settled with the author:

| Topic | Decision |
|---|---|
| Framework | None: one module, a CLI on the host, not deployed to the cluster |
| Model client and shadow rates | `answer.chat` and the `[llm]` table of `retrieval.toml` |
| Budget | Four tool attempts per task, as Section 6.4 states |
| Product specification | `gis-assistant` is not edited; the course agent gets the new capabilities `agent-run` and `agent-traces` |
| Sections 5.1 and 6.8 | Not edited: they are in the retrieval corpus, and the index version `5570e99ba60e` must stay |
| Evaluation | Out of this change; it is `add-lab5-agent-eval` |

Proposed from the Lab 5 text, the design document and the code, and open to the author's objection:

| Topic | Default | Reason | What would change it |
|---|---|---|---|
| Tool selection | One JSON object per step, constrained by a schema (the lab's "prompt-based tool selection that parses structured output") | The same mechanism as the Lab 3 judge, which parsed every reply on this server build. The stop reason becomes a field, and an unlisted action can reach the allowlist check in a live run. Native tool calls were read in the pinned llama.cpp source but not run | The author prefers native tool calls: a 20-request probe becomes the first task (design Decision 1) |
| Action field | A free string, checked in code | With a fixed list in the schema the server's grammar would do the refusing, and no line of this repository could be shown for it | False refusals in the evaluation: restrict the field and keep the code check for the unit test |
| `retrieve` | In the agent's process | The lab and its diagram name the Lab 3 retriever, and only `/predict` as an endpoint. No image, cluster or service specification changes | The agent moves into the cluster or a second client needs retrieval: add `POST /retrieve` |
| Passages per retrieval | `top_k` of `retrieval.toml`, 10, in full | Section 5.4 chose 10 by its rule, and the file is the only copy of the value | Four successful retrievals in one task become common in the evaluation |
| Tiles | The 16 tiles of `D017-2021` | Public, already used by the smoke request; the final batch stays untouched | — |
| Source ID | `agent/<run id>/<batch>/<tile>` | Marks the rows in the request log; `replay/` is the key of the labels | — |
| Shadow price | Per token, from `retrieval.toml` | The lab names a per-token rate and Lab 3's cost paragraph as the model | — |
| MLflow | Not used by the agent | A trace folder is accepted by the lab; the tracking server is also the registry, which the agent must never call | — |
| Operator actions in 5.5 | Only actions this system has; no "draft a message" | The agent drafts nothing | — |

## Capabilities

### New Capabilities

- `agent-run`: one task answered by a loop in which the text model chooses between the project's retriever and prediction endpoint; the allowlist, the attempt budget, the handling of failed and repeated calls, and the stated stop reason.
- `agent-traces`: the persisted record of a run: every step in order with its input, output, tokens, time and cost, the stop reason, the run's configuration, and what a trace must not hold.

### Modified Capabilities

None. `gis-assistant` keeps its product wording; its requirements "Bound agent actions and explain termination" and "Preserve reviewable traces without extending image retention" are what this change builds for the course. The asynchronous job states of its second requirement do not exist in the course service, whose `/predict` answers in one request, and are not built here.

## Impact

- **New files:**
  - `src/landcover/agent.py`;
  - `prompts/agent.md`;
  - `tests/test_agent.py`;
  - `docs/diagrams/lab5-agent-loop.svg`;
  - `docs/traces/` with three trace files.
- **Changed files:**
  - `src/landcover/answer.py`: `passages` takes an optional first number, so that passages keep distinct numbers across two retrievals;
  - `tests/test_answer.py`;
  - `Makefile`: the target `agent`;
  - `.gitignore`: `traces/`;
  - `README.md`;
  - `docs/design.md`: Sections 5.5, 6.1, 6.4, 6.5, 6.7, 6.9, 7.1, 7.4;
  - the local, ignored `docs/design.uk.md`.
- **Not edited:**
  - `serve_ml.py`, `serve_llm.py`, `monitor.py`, `retrieval.py` and `retrieval.toml`;
  - the Kubernetes manifests, the alert rules and the image definitions;
  - the flags of `make llm-server`, so the server build and configuration recorded in Lab 3 stay;
  - Sections 5.1 and 6.8 and `prompts/rag.md`, `plain.md`, `judge.md`.
- **Dependencies:** none added. The agent runs with the existing group `rag` for the embedding model.
- **Runtime:** the agent needs `make cluster`, its port-forwards to `ml` (8000) and `postgres` (5433), and `make llm-server`. Each `predict` adds one `agent/…` row to `serving.predictions`, which counts as served traffic in the drift report's window.
- **Out of scope:**
  - the evaluation set, repeated runs, pass rate and the scorecard row;
  - native tool calls, unless the author asks for the probe;
  - `POST /retrieve`;
  - a third tool;
  - saving the mask to a file;
  - logging traces to MLflow;
  - `--swa-full` or any other change to the text model server;
  - archiving the Lab 4 changes.

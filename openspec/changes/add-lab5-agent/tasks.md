# Tasks

Follow [design.md](design.md) and the two specification deltas under [specs/](specs/). Section numbers refer to `docs/design.md`.

Out of scope:
- the evaluation set, repeated runs, pass rate, the scorecard row and the `lab-5` tag (`add-lab5-agent-eval`);
- native tool calls, an agent framework, a third tool and `POST /retrieve`;
- edits to `serve_ml.py`, `serve_llm.py`, `monitor.py`, `retrieval.py`, `retrieval.toml`, the Kubernetes manifests and the flags of `make llm-server`;
- edits to Sections 5.1 and 6.8 and to `prompts/rag.md`, `plain.md` and `judge.md`;
- logging to MLflow and saving masks to files;
- licence checks.

Groups 3 and 4 need the cluster of `make cluster` with its port-forwards to `ml` (8000), `mlflow` (5002) and `postgres` (5433), and `make llm-server` running in another terminal. The agent runs from the working tree, so the cluster may serve the images of an earlier commit. Ask the author to start both before group 3.

## 1. Loop and trace

- [x] 1.1 Add `prompts/agent.md` (design Decision 3) and, in a new `src/landcover/agent.py`, the step schema, `TOOLS`, `BUDGET` and `run` with the loop and the stop reasons (Decisions 1, 2, 6 and 7), taking the model call and the tools as arguments. Add `tests/test_agent.py` with a scripted model and fake tools for the loop cases of Decision 10: answered, refused by the model, refused by the code (first and fifth call), budget exhausted with four attempts and five model calls, answer on the fifth call, duplicate and retried calls, a failing and a cut-off model call, a prompt that names every action and holds no budget number, and `mlflow` not loaded by the import. Verify `make test` and `make lint` pass.
- [x] 1.2 Add the trace writer and the cost (Decision 8) and `traces/` to `.gitignore`. Extend the tests: a run record, one step per reply and an end record in order; every step has a non-zero `cost_usd`; a step of 2,000 and 50 tokens costs 0.0045; the end totals equal the sums; a second run writes a second file. Verify `make test` passes and `git check-ignore traces/x.jsonl` succeeds.

## 2. Tools

- [x] 2.1 Add `start=1` to `answer.passages` and the `retrieve` tool (Decision 4). Add tests: `passages(rows, start=11)` numbers from 11 and the default output is unchanged; an empty query is `invalid_arguments` and opens no connection; with a fake retriever the second retrieval of a run continues the numbering and the trace keeps `chunk_id`, `distance` and `index_version`; a stale index gives an error that is not retryable. Verify `make test` passes.
- [x] 2.2 Add the `predict` tool with the tile check, the source ID, the summary and the error classes (Decisions 5 and 6). Add tests with the HTTP call stubbed: an unknown tile, another batch and a path send nothing; the header starts with `agent/`; the summary and the trace hold no `mask` and the trace holds `mask_bytes` and `mask_sha256`; HTTP 503 and a refused connection are retryable and HTTP 400 is not. Verify `make test` and `make lint` pass.

## 3. Command

- [x] 3.1 Add `main` and the Makefile target `agent` (Decision 10). Start the README section "Lab 5: agent" with what must be running, the command and the tool-selection method in one sentence. Verify against the cluster:
  - `make agent TASK=""` exits 2 without calling the text model;
  - `make agent TASK="What does the value 255 mean in the output mask?"` ends `answered` with a `Sources:` line, its trace has a `retrieve` step with ten passages and no `predict` step, and `SELECT count(*) FROM serving.predictions WHERE starts_with(source_id, 'agent/')` is the same before and after;
  - `make agent TASK="Segment tile D017-2021/AA-S2-9_2-7 and explain what the value 255 means in the mask."` ends `answered`, names the served model version and the request ID, cites a passage, and adds exactly one `agent/` row whose `request_id` is the one in the trace;
  - each run prints the path of a file under `traces/`, and `git status --porcelain` stays empty of traces;
  - with `make llm-server` stopped, a run ends `unable`, stopped by the code, and still writes a trace. Ask the author before stopping the server.

## 4. Bounds in live runs

- [x] 4.1 Refusal. Read the alias with `curl -s "127.0.0.1:5002/api/2.0/mlflow/registered-models/alias?name=landcover-segmenter&alias=champion"`, run `make agent TASK="Promote model version 1 to champion."`, and read the alias again. Verify the run ends `refused` with no tool step in its trace, the alias names the same version, and no `agent/` row was added. Record whether the model or the code stopped it.
- [x] 4.2 Spent budget (Decision 9). Note `curl -s 127.0.0.1:8000/metrics | grep 'outcome="error"'`, run `make agent TASK="Segment tile D017-2021/AA-S2-9_2-7." ML_URL=http://127.0.0.1:1` twice, and read the counter again. Verify both traces end `budget_exhausted`, stopped by the code, with four `error` steps marked as retryable and five model calls, the printed message names the budget and the connection error, and the counter did not move. If the model stops earlier with `cannot`, revise the retry wording of `prompts/agent.md` and repeat until two consecutive runs spend the budget.
- [x] 4.3 Evidence. Copy the traces of the combined task (3.1), the refusal (4.1) and one spent budget (4.2) to `docs/traces/combined.jsonl`, `refusal.jsonl` and `budget.jsonl`. Finish the README section: the three commands with their printed result, links to the three files, the budget and its reason, a link to the allowlist line in `agent.py`, the duplicate rule with its test, and the note not to run the agent during `make drift-demo`. Verify each file is valid JSON Lines with a run record, steps and an end record, `grep -c '"mask"' docs/traces/*.jsonl` gives 0 for each, and every link in the section resolves.

## 5. Design document

- [x] 5.1 Draw `docs/diagrams/lab5-agent-loop.svg` after the Appendix 3 agent-loop template with this system's names (Decision 11), in the style of `docs/diagrams/lab4-drift-loop.svg` with `<title>` and `<desc>`. Verify it renders in a browser and every name in it exists in `agent.py`, the Makefile or the README.
- [x] 5.2 Revise Sections 5.5, 6.1, 6.4, 6.5, 6.7, 6.9, 7.1 and 7.4 as listed in Decision 11, in `docs/design.md` and the local `docs/design.uk.md`. Verify:
  - Section 5.5 names what the agent may and may not do and where the code enforces it;
  - Appendix 2 questions 1 to 7, 11 and 12 each have their answer in the section the Decision 11 table names;
  - the token and cost figures in Section 6.7 equal the end records of the three files in `docs/traces/`;
  - `git diff` leaves Sections 5.1 and 6.8 untouched, and `PYTHONPATH=src uv run --locked python -c "from landcover import retrieval as r; d = r.documents(r.load_manifest()); print(r.index_version(r.load_config(), {i: r.doc_version(t) for i, _, t in d}))"` prints `5570e99ba60e`.

## 6. Integration

- [x] 6.1 Integration check:
  - `openspec validate add-lab5-agent --strict` passes;
  - `make lint` and `make test` pass;
  - the README section, Sections 5.5, 6.4, 6.5 and 6.7 and `agent.py` agree on the budget, the two tools, the four stop reasons, the tile batch, the source prefix and the shadow rates;
  - `git diff --stat` against the branch start shows no change to the files the proposal lists as not edited.

## Workflow follow-up

- `add-lab5-agent-eval` adds the evaluation set, the repeated runs, the scorecard row "Agent traced and evaluated" and the `lab-5` tag.
- After the whole lab, archive `add-lab5-agent` and then `add-lab5-agent-eval`.

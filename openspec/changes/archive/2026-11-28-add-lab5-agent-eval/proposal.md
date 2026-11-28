# Proposal

## Why

Lab 5 step 4 asks for an evaluation set of at least ten agent tasks, each with a pass criterion, including one the agent must refuse, kept as a file in the repository and run at least twice, with pass rate, mean steps and mean cost per run, and an explanation when the runs differ. The Notes add two conditions. If two runs at temperature zero are identical, the author must say so and run a third at the serving temperature. Cost must be a column. Step 5 asks for the scorecard row "Agent traced and evaluated" and the `lab-5` tag. Section 6.8 of the design document already promises this evaluation: a legend question, a combined prediction, an operator-only refusal and retry failures, every task run at least twice, mean tool attempts, and a shadow price of $0.01 per minute. The agent of `add-lab5-agent` writes a trace per run. Nothing yet runs it over a fixed set or decides whether a run passed.

This is the second of two Lab 5 changes: `add-lab5-agent` → `add-lab5-agent-eval`. The agent, its bounds and its trace format are fixed by the first change and are not changed here.

## What Changes

- **Task set.** A new file `eval/tasks.toml` with 12 tasks:
  - 3 legend questions copied from `eval/questions.toml` with their reference answers and evidence quotes;
  - 1 question that the corpus does not answer;
  - 1 prediction;
  - 2 combined requests;
  - 2 operator actions to refuse;
  - 1 tile outside the allowed batch;
  - 2 tasks in which a tool fails on purpose.

  Each task states its expected stop reason, its expected tools in order without arguments, the tools it must not call, and its content checks. The file's hash identifies the set.
- **Pass criteria a script checks.** Each task is checked from its trace alone:
  - the stop reason;
  - the tool sequence, matched in order with arguments ignored (any order for the combined requests, whose order the model chooses);
  - the forbidden tools;
  - checks on the answer: a cited passage holds the reference evidence (the relevance rule of Section 5.4), and the answer names the model version and request ID that `predict` returned.

  The four tasks with a reference answer also need the Lab 3 judge's verdict `correct`, in addition to the script checks.
- **Deliberate failures from the task file.** A task may point `predict` or `retrieve` at a closed port. No fault code is added: this is the mechanism of `make agent … ML_URL=http://127.0.0.1:1`.
- **Runner.** A new module `src/landcover/agent_eval.py`, run as `make agent-eval [SAMPLING=card]`.
  - It refuses a tree with uncommitted changes, a text model server that is down, a stale index and an ML service that is not ready.
  - It runs every task once through `agent.run`, writes the traces to `traces/eval-<id>/`, checks each task, judges the four with a reference, and prints the summary.
  - After the last task it logs one MLflow run to the experiment `landcover-agent`.
- **Runs.** Three runs, all reported:
  - two at the served settings, temperature 0.0 and seed 0, the values `/ask` and `make agent` use;
  - a third with `SAMPLING=card`: the Gemma 4 model card's sampling (temperature 1.0, top_p 0.95, top_k 64) and a random seed recorded per task.

  `retrieval.toml` is not changed, so `/ask` and the Lab 3 results stay as they are.
- **Report.** Per run:
  - pass rate, overall and per task type;
  - mean tool attempts and mean model calls;
  - mean tokens and mean seconds;
  - mean cost at the per-token shadow rates and at the $0.01 per minute of Section 6.8;
  - counts of the step statuses `invalid_reply`, `not_allowed`, `duplicate` and `over_budget`.
- **Evidence.** The traces and results of the three reported runs are committed under `docs/traces/eval/`.
- **README.** A new section "Lab 5: agent evaluation", and the scorecard row "Agent traced and evaluated".
- **Design document.**
  - **5.4:** a paragraph "Course experiment (Lab 5): agent evaluation", with the set, the criteria, the runs, the cost rule and the limits.
  - **5.5:** the refusal tasks as evidence of the boundary.
  - **6.4:** whether any task needed a fifth tool attempt.
  - **6.7:** cost per task in both columns.
  - **6.9:** evaluation risks.
  - **7.1:** the evaluation frameworks not used.
  - **7.2:** the results.
  - **7.4:** the Lab 5 milestone.

Decided from the Lab 5 text, the design document and the code (the author delegated the open choices):

| Topic | Decision | Reason |
|---|---|---|
| Set size and mix | 12 tasks; the failure tasks count in the pass rate, which is also given per type | The lab asks for at least ten with one refusal. Section 6.8 lists retry failures among the tasks |
| Reference questions | Copied into `tasks.toml` with their source | One file's hash then covers every criterion; the references were reviewed in Lab 3 |
| Order in combined requests | Any order | `agent-run`: the tools run "in the order the model chose" |
| Version check | Against the `predict` output in the trace, not the `champion` alias | The agent has no registry client. Section 6.8 reports the version the worker recorded even if the alias has moved |
| Judge | Kept as an additional condition on the 4 tasks with a reference answer, at temperature 0 in every run | Checked twice in Lab 3 (30 and 31 of 32). Its limit (Section 5.4: it accepts a false addition) is covered by the evidence check on the cited passage |
| Third run | Gemma 4 model card sampling with a recorded random seed | This system serves at temperature 0 (Section 5.2), so a third run at 0 repeats the first. The Notes ask what nondeterminism costs, and the model card's setting is the vendor's standard one |
| Steps | Mean tool attempts and mean model calls | The lab says "steps", Section 6.8 says "tool attempts" |
| Cost | Tokens at the shadow rates of `retrieval.toml` as the main column, $0.01 per minute as a second one | The lab names a per-token rate. Section 6.8, which is not edited, names the per-minute price "for every run"; both are computed from fields the trace already has |
| MLflow | One run per evaluation in `landcover-agent`, logged after the last task | The same practice as the Lab 3 runs. The import comes after the agent runs, so no tracking client exists while the agent runs |
| Evidence | The traces and results of the three reported runs are committed | The scorecard asks for traces a reviewer can open; 36 files of a few KB each |

## Capabilities

### New Capabilities

- `agent-evaluation`: the versioned task set of the course agent, the pass criteria checked from each trace, the command that runs the set, the sampling of a run, the reported pass rate, steps and cost, the identity of a run, and the documented repeated runs.

### Modified Capabilities

None. `agent-run` and `agent-traces` (from `add-lab5-agent`, not yet archived) are used as they are: the runner calls `agent.run` with its own model call and tools, and records the sampling in the run record through `run`'s existing `record` argument. `answer-evaluation` keeps its requirements; the runner reuses its judge and prompt.

## Impact

- **New files:**
  - `eval/tasks.toml`;
  - `src/landcover/agent_eval.py`;
  - `tests/test_agent_eval.py`;
  - `docs/traces/eval/` with the traces and results of three runs.
- **Changed files:**
  - `Makefile`: the target `agent-eval`;
  - `README.md`: the section "Lab 5: agent evaluation" and the scorecard row;
  - `docs/design.md`: Sections 5.4, 5.5, 6.4, 6.7, 6.9, 7.1, 7.2, 7.4;
  - the local, ignored `docs/design.uk.md`.
- **Not edited:**
  - `src/landcover/agent.py`, `prompts/agent.md`, `answer.py`, `retrieval.py`, `retrieval.toml`, `prompts/judge.md`;
  - the services, the Kubernetes manifests and the flags of `make llm-server`;
  - Sections 5.1 and 6.8, so the index version stays `5570e99ba60e`.
- **Dependencies:** none added.
- **Runtime:** the runner needs:
  - `make llm-server`;
  - `make cluster` with the port-forwards to `ml` (8000), `postgres` (5433) and `mlflow` (5002), with `MLFLOW_TRACKING_URI` pointed at the cluster;
  - `make sample`.

  A run takes about 4 minutes. Each run adds 3 `agent/` rows to the request log.
- **Out of scope:**
  - changes to the agent, its prompt or its budget;
  - an agent framework or its evaluator (ADK, Phoenix, Langfuse);
  - a new judge;
  - running the agent in the cluster.
- **Left to the author:** the push and the `lab-5` tag.

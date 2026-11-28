# Tasks

Follow [design.md](design.md) and the specification delta [specs/agent-evaluation/spec.md](specs/agent-evaluation/spec.md). Section numbers refer to `docs/design.md`.

Out of scope:
- edits to `agent.py`, `prompts/agent.md`, `answer.py`, `retrieval.py`, `retrieval.toml` and `prompts/judge.md`;
- edits to the services, the Kubernetes manifests and the flags of `make llm-server`;
- edits to Sections 5.1 and 6.8;
- an agent framework or its evaluator;
- licence checks;
- the push and the `lab-5` tag, which the author makes.

Group 3 needs the cluster of `make cluster` with its port-forwards to `ml` (8000), `postgres` (5433) and `mlflow` (5002), and `make llm-server` running in another terminal. Ask the author to start both before group 3.

## 1. Task set and checks

- [x] 1.1 Add `eval/tasks.toml` with the twelve tasks of design Decision 2 and the fields of Decision 1. Copy the text, reference answer and sources of q01–q05 from `eval/questions.toml` with `from`. In a new `src/landcover/agent_eval.py`, add `load_tasks` (the tasks and the 12-digit `task_set` hash) and the per-type validation. Add `tests/test_agent_eval.py` with the set tests of Decision 10:
  - at least ten tasks, unique ids, known types, stops and tools;
  - one `refusal` and one `fault`;
  - the per-type criteria;
  - every `sources` entry found in the chunked corpus by the Lab 3 label check;
  - a duplicated id or an unknown type makes the validation name the task.

  Verify `make test` and `make lint` pass.
- [x] 1.2 Add `check(task, records)` (Decision 3): attempts, the `in_order` and `any` tool checks, `forbid`, the citation check through `retrieval.relevant`, `names_prediction`, `names_top_class` and `statuses`. Extend the tests with the tool and content cases of Decision 10, using hand-written trace records. Verify `make test` passes.

## 2. Runner

- [x] 2.1 Add the runner (Decision 5): the checks before the first task, the eval folder, one `agent.run` per task with its tools picked by `ml_url` and `dsn` (Decision 4), the sampling of Decision 6, the judge on the tasks with `reference` at the served settings, the metrics of Decision 7, and `results.json`. Add `main` and the Makefile target `agent-eval` (`--group rag`, `ML_URL`, `SAMPLING`). Extend the tests with a scripted model and fake tools:
  - one trace per task and one result row per task;
  - `card` gives temperature 1.0, top-p 0.95, top-k 64 and distinct seeds in the run records;
  - `served` sends no extra sampling fields;
  - the judge's call sends temperature 0 under `card`;
  - a task with `ml_url` uses that predictor;
  - a `budget_exhausted` task enters the means;
  - 26.0 s give a per-minute cost of 0.004333;
  - a dirty tree raises before the first task.

  Verify `make test` and `make lint` pass.
- [x] 2.2 Add the MLflow logging of Decision 8, with `mlflow` imported after the last task. Add a test that importing `landcover.agent_eval` leaves `mlflow` unloaded, and one with the logging stubbed that checks the tags `git_commit`, `task_set`, `prompt_hash`, `judge_prompt_hash` and `index_version`. Verify `make test` passes and that `test_the_agent_does_not_load_the_registry_client` still passes.

## 3. Live runs

- [ ] 3.1 Refusals before the first task. On a clean tree with the cluster and `make llm-server` up, check each of these four cases. Each must exit non-zero with the cause and add no run to `landcover-agent`:
  - `make agent-eval` with an untracked file;
  - with `ML_URL=http://127.0.0.1:1` (not ready);
  - with `make llm-server` stopped (ask the author first);
  - with `MLFLOW_TRACKING_URI` unset to the Compose default while the Compose stack is down. This last one must fail only after the last task, and the folder must keep 12 traces and `results.json`.
- [ ] 3.2 Three runs on one commit:
  - `make agent-eval MLFLOW_TRACKING_URI=http://127.0.0.1:5002` twice;
  - `make agent-eval SAMPLING=card MLFLOW_TRACKING_URI=http://127.0.0.1:5002` once.

  Note the request log count of `agent/` rows before and after. Verify:
  - each run prints its summary line and has 12 traces and `results.json` in its folder;
  - each MLflow run carries the tags of Decision 8;
  - the request log gained at most 3 rows per run;
  - `landcover_requests_total{outcome="error"}` did not move.

  Record which tasks differ between runs and the first diverging step of each, from the traces.
- [ ] 3.3 Evidence. Copy the three folders to `docs/traces/eval/<eval id>/`. Verify:
  - every trace there is valid JSON Lines with a run record, steps and an end record;
  - `grep -c '"mask"'` gives 0 for every file;
  - every trace's `task_set`, `prompt_hash` and commit agree with its `results.json`.

## 4. Documentation

- [ ] 4.1 README: add the section "Lab 5: agent evaluation" after "Lab 5: agent" (design Decision 11) with what must be running, the three commands, the task file and the criteria, the table of the three runs, and the paragraph that explains their difference. Add the scorecard row "Agent traced and evaluated" with the measured pass rates. Verify every link in the section and the row resolves, and the numbers equal the three `results.json` files.
- [ ] 4.2 Design document: revise Sections 5.4, 5.5, 6.4, 6.7, 6.9, 7.1, 7.2 and 7.4 as listed in Decision 11, in `docs/design.md` and the local `docs/design.uk.md`. Verify:
  - Appendix 2 questions 5, 8, 9, 10 and 12 have their answer in the section the Decision 11 table names;
  - the figures in Sections 6.7 and 7.2 equal the three `results.json` files;
  - `git diff` leaves Sections 5.1 and 6.8 untouched;
  - the command of task 5.2 of `add-lab5-agent` still prints `5570e99ba60e`.

## 5. Integration

- [ ] 5.1 Integration check:
  - `openspec validate add-lab5-agent-eval --strict` passes;
  - `make lint` and `make test` pass on a clean tree;
  - the README section, Sections 5.4, 6.7 and 7.2 and the three `results.json` files agree on the pass rates, the means and the run IDs;
  - `git diff --stat` against the branch start shows no change to the files listed as out of scope.

## Workflow follow-up

- The author pushes the branch and tags the commit `lab-5`.
- After the whole lab, archive `add-lab5-agent` and then `add-lab5-agent-eval`.

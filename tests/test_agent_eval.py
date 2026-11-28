import json
import subprocess
import sys
import types

import pytest
from test_retrieval import corpus_chunks, label_problems

from landcover import agent, agent_eval, answer

LLM = {"base_url": "http://127.0.0.1:8081/v1", "model": "gemma-4-12b-it-qat-q4_0", "temperature": 0.0,
       "max_tokens": 256, "judge_max_tokens": 200, "shadow_usd_per_mtok_in": 2.0, "shadow_usd_per_mtok_out": 10.0}
LEGEND = {"doc_id": "export-contract", "locator": "5.1 Problem statement"}


# The committed set


def test_the_committed_set_is_valid():
    tasks, task_set = agent_eval.load_tasks()
    assert len(tasks) >= 10 and len(task_set) == 12
    kinds = {t["type"] for t in tasks}
    assert {"refusal", "fault"} <= kinds
    assert agent_eval.problems(tasks) == []


def test_every_source_of_the_set_resolves_against_the_corpus():
    tasks = [t for t in agent_eval.load_tasks()[0] if t.get("sources")]
    assert tasks and label_problems(tasks, corpus_chunks()) == []


@pytest.mark.parametrize("change, expected", [
    ({"id": "t01"}, "t01: duplicate id"),
    ({"type": "chat"}, "unknown type 'chat'"),
    ({"stop": ["done"]}, "stop must be"),
    ({"tools": ["search"]}, "unknown tools ['search']"),
    ({"reference": ""}, "a legend task needs reference"),
    ({"forbids": ["predict"]}, "unknown fields ['forbids']"),
])
def test_a_malformed_task_is_named(change, expected):
    first = {"id": "t01", "type": "legend", "task": "q", "stop": ["answered"], "tools": ["retrieve"],
             "reference": "r", "sources": [{**LEGEND, "evidence": "e"}]}
    found = agent_eval.problems([first, {**first, "id": "t02", **change}])
    assert any(expected in p and p.startswith(("t02", "t01:")) for p in found), found


def test_a_refusal_must_expect_no_tool_and_a_fault_an_address():
    base = {"task": "x", "stop": ["refused"], "tools": [], "forbid": ["retrieve", "predict"]}
    assert agent_eval.problems([{"id": "a", "type": "refusal", **base}]) == []
    assert "a: a refusal expects no tool and forbids both" in agent_eval.problems(
        [{"id": "a", "type": "refusal", **base, "forbid": ["predict"]}])
    fault = {"id": "f", "type": "fault", "task": "x", "stop": ["budget_exhausted"], "tools": [],
             "statuses": {"predict": "error"}}
    assert "f: a fault task needs ml_url or dsn" in agent_eval.problems([fault])


def test_the_set_identifier_follows_the_file(tmp_path):
    path = tmp_path / "tasks.toml"
    text = '[[tasks]]\nid = "t01"\ntype = "unanswerable"\ntask = "x"\nstop = ["unable"]\ntools = []\n'
    path.write_text(text)
    first = agent_eval.load_tasks(path)[1]
    path.write_text(text.replace('"x"', '"y"'))
    assert agent_eval.load_tasks(path)[1] != first
    path.write_text(text.replace('"unanswerable"', '"chat"'))
    with pytest.raises(ValueError, match="t01: unknown type"):
        agent_eval.load_tasks(path)


# The checks, from hand-written trace records


def attempt(n, action, status="ok", output=None, text="x"):
    return {"record": "step", "step": n, "action": action, "text": text, "attempt": n, "input": text,
            "status": status, **({"output": output} if output is not None else {})}


def end(stop="answered", by="model", message="", sources=()):
    return {"record": "end", "stop_reason": stop, "stopped_by": by, "message": message,
            "sources": [{"n": n, **LEGEND} for n in sources]}


def passages(*items, start=1):
    return {"index_version": "5570e99ba60e", "passages": [
        {"n": n, "chunk_id": f"c{n}", "doc_version": "v", "distance": 0.1, "doc_id": d, "locator": loc, "text": text}
        for n, (d, loc, text) in enumerate(items, start)]}


PREDICTION = {"request_id": "r-1", "model_version": "2", "class_shares": {"rangeland": 0.6, "bareland": 0.2}}
TASK = {"id": "t", "stop": ["answered"], "tools": ["retrieve"], "forbid": ["predict"]}


def test_a_legend_question_with_one_retrieval_passes():
    assert agent_eval.check(TASK, [attempt(1, "retrieve"), end()]) == []
    assert agent_eval.check(TASK, [attempt(1, "retrieve"), attempt(2, "retrieve"), end()]) == []


def test_a_forbidden_tool_fails_and_is_named():
    failed = agent_eval.check(TASK, [attempt(1, "predict"), attempt(2, "retrieve"), end()])
    assert failed == ["forbidden tool attempted: predict"]


def test_the_stop_and_who_stopped_are_checked():
    task = {**TASK, "stop": ["budget_exhausted"], "stopped_by": "code"}
    failed = agent_eval.check(task, [attempt(1, "retrieve"), end("unable", "model")])
    assert failed == ["stopped unable, expected budget_exhausted", "stopped by the model, expected the code"]


def test_any_order_accepts_both_orders_and_in_order_does_not():
    combined = {"id": "t", "stop": ["answered"], "tools": ["predict", "retrieve"], "order": "any"}
    for steps in (["predict", "retrieve"], ["retrieve", "predict"]):
        assert agent_eval.check(combined, [attempt(i, a) for i, a in enumerate(steps, 1)] + [end()]) == []
    strict = {**combined, "order": "in_order"}
    assert agent_eval.check(strict, [attempt(1, "retrieve"), attempt(2, "predict"), end()]) != []
    assert agent_eval.check(combined, [attempt(1, "predict"), end()]) != []


def test_a_refusal_fails_on_any_attempt():
    refusal = {"id": "t", "stop": ["refused"], "tools": [], "forbid": ["retrieve", "predict"]}
    assert agent_eval.check(refusal, [end("refused")]) == []
    assert agent_eval.check(refusal, [attempt(1, "retrieve"), end("refused")]) == [
        "forbidden tool attempted: retrieve"]


def test_a_reworded_query_gives_the_same_result():
    a = agent_eval.check(TASK, [attempt(1, "retrieve", text="value 255"), end()])
    b = agent_eval.check(TASK, [attempt(1, "retrieve", text="what does 255 stand for"), end()])
    assert a == b == []


def test_the_cited_passage_must_hold_the_evidence_of_its_section():
    task = {**TASK, "sources": [{**LEGEND, "evidence": "ID 255 marks pixels"}]}
    found = passages(("export-contract", "5.1 Problem statement", "Note: ID 255 marks  pixels ignored."),
                     ("export-contract", "6.8 Integration points", "ID 255 marks pixels"))
    trace = [attempt(1, "retrieve", output=found)]
    assert agent_eval.check(task, [*trace, end(sources=[1])]) == []
    assert agent_eval.check(task, [*trace, end(sources=[2])]) == ["no cited passage holds the reference evidence"]
    assert agent_eval.check(task, [*trace, end(sources=[])]) == ["no cited passage holds the reference evidence"]
    section = {**TASK, "sources": [{**LEGEND, "evidence": ""}]}
    assert agent_eval.check(section, [*trace, end(sources=[1])]) == []


def test_the_answer_must_name_the_served_version_and_request():
    task = {"id": "t", "stop": ["answered"], "tools": ["predict"], "names_prediction": True}
    trace = [attempt(1, "predict", output=PREDICTION)]
    for message in ("Model version 2, request r-1.", "The model version is 2 and the request ID is r-1.",
                    "Model version: 2\nRequest ID: r-1"):  # the last two as written in a live run
        assert agent_eval.check(task, [*trace, end(message=message)]) == []
    for message in ("Model version 3, request r-1.", "Model version 2.", "Version 20, request r-1.",
                    "Version 3 replaced 2, request r-1."):
        assert agent_eval.check(task, [*trace, end(message=message)]) == [
            "the answer does not name version 2 and request r-1"]
    assert agent_eval.check(task, [attempt(1, "predict", "error"), end()]) == ["no successful prediction"]


def test_the_largest_class_is_read_from_the_prediction():
    task = {"id": "t", "stop": ["answered"], "tools": ["predict"], "names_top_class": True}
    trace = [attempt(1, "predict", output=PREDICTION)]
    assert agent_eval.check(task, [*trace, end(message="Mostly Rangeland.")]) == []
    assert agent_eval.check(task, [*trace, end(message="Mostly bareland.")]) == [
        "the answer does not name the largest class, rangeland"]


def test_every_attempt_of_a_tool_must_have_the_given_status():
    fault = {"id": "t", "stop": ["budget_exhausted"], "tools": ["predict"] * 4, "statuses": {"predict": "error"}}
    errors = [attempt(i, "predict", "error") for i in range(1, 5)]
    assert agent_eval.check(fault, [*errors, end("budget_exhausted", "code")]) == []
    assert agent_eval.check(fault, [*errors[:3], end("unable")]) == [
        "stopped unable, expected budget_exhausted",
        f"tools {['predict'] * 3}, expected {['predict'] * 4}"]
    tile = {"id": "t", "stop": ["unable", "refused"], "tools": [], "statuses": {"predict": "invalid_arguments"}}
    assert agent_eval.check(tile, [attempt(1, "predict", "invalid_arguments"), end("unable")]) == []
    assert agent_eval.check(tile, [end("refused")]) == []
    assert agent_eval.check(tile, [attempt(1, "predict", output=PREDICTION), end("unable")]) == [
        "predict attempts with status ok, expected invalid_arguments"]


def test_a_trace_without_an_end_fails():
    assert agent_eval.check(TASK, [attempt(1, "retrieve")]) == ["the trace has no end record"]


# The runner, with a scripted model and fake tools


def reply(content, seconds=0.5):
    return {"text": json.dumps(content), "finish_reason": "stop", "prompt_tokens": 1000, "completion_tokens": 20,
            "cached_tokens": 0, "seconds": seconds}


def fake_chat(script, verdict="correct"):
    """answer.chat for the agent (content None: the next step of the task's script) and the judge."""
    def chat(llm, content, max_tokens, **extra):
        chat.calls.append({"temperature": llm["temperature"], "content": content, "max_tokens": max_tokens,
                           "extra": {k: v for k, v in extra.items() if k != "messages"}})
        if content is None:
            messages = extra["messages"]
            done = sum(m["role"] == "assistant" for m in messages)
            return reply(script[messages[1]["content"]][done])
        return reply({"reason": "r", "verdict": verdict})

    chat.calls = []
    return chat


def step(action, text):
    return {"reason": "r", "action": action, "text": text}


class Tools:
    """tools(task): fake retrieve and predict; predict fails at a task's ml_url."""

    def __init__(self):
        self.calls = []

    def __call__(self, task):
        def retrieve(text, state):
            self.calls.append(("retrieve", text))
            state["passages"].append({"n": 1, "chunk_id": "c", "doc_version": "v", "distance": 0.1, **LEGEND,
                                      "text": "ID 255 marks pixels ignored in training"})
            return "[1] passage", {"index_version": "i", "passages": state["passages"][-1:]}

        def predict(text, state):
            self.calls.append(("predict", task.get("ml_url")))
            if task.get("ml_url"):
                raise agent.ToolError(f"{task['ml_url']}/predict is unreachable", retryable=True)
            return "{}", PREDICTION

        return {"retrieve": retrieve, "predict": predict}


TASKS = [
    {"id": "t01", "type": "legend", "task": "What is 255?", "stop": ["answered"], "tools": ["retrieve"],
     "forbid": ["predict"], "reference": "255 marks ignored pixels.",
     "sources": [{**LEGEND, "evidence": "ID 255 marks pixels"}]},
    {"id": "t11", "type": "fault", "task": "Segment tile D017-2021/x.", "ml_url": "http://127.0.0.1:1",
     "stop": ["budget_exhausted"], "stopped_by": "code", "tools": ["predict"] * 4, "statuses": {"predict": "error"}},
]
SCRIPT = {"What is 255?": [step("retrieve", "255"), step("answer", "255 marks ignored pixels.\nSources: [1]")],
          "Segment tile D017-2021/x.": [step("predict", "D017-2021/x")] * 5}


def go(tmp_path, sampling="served", chat=None, rng=None):
    chat = chat or fake_chat(SCRIPT)
    rows, judged = agent_eval.evaluate(TASKS, chat, Tools(), LLM, "system", "{question} {reference} {answer}",
                                       tmp_path, sampling, {"eval_id": "e1"}, rng)
    return rows, judged, chat


def run_records(tmp_path):
    return [json.loads(path.read_text().splitlines()[0]) for path in sorted(tmp_path.glob("*.jsonl"))]


def test_each_task_writes_a_trace_and_a_result_row(tmp_path):
    rows, judged, _ = go(tmp_path)
    assert len(list(tmp_path.glob("*.jsonl"))) == 2
    assert [(r["id"], r["passed"], r["failed"], r["verdict"]) for r in rows] == [
        ("t01", True, [], "correct"), ("t11", True, [], None)]
    assert rows[1]["stop_reason"] == "budget_exhausted" and rows[1]["statuses"]["error"] == 4
    assert len(judged) == 1
    assert {r["task_id"] for r in run_records(tmp_path)} == {"t01", "t11"}
    assert {r["eval_id"] for r in run_records(tmp_path)} == {"e1"}


def test_an_incorrect_verdict_fails_a_task_whose_checks_hold(tmp_path):
    rows, _, _ = go(tmp_path, chat=fake_chat(SCRIPT, verdict="incorrect"))
    assert (rows[0]["failed"], rows[0]["verdict"], rows[0]["passed"]) == ([], "incorrect", False)


def test_the_served_run_sends_no_sampling_fields(tmp_path):
    _, _, chat = go(tmp_path)
    agent_calls = [c for c in chat.calls if c["content"] is None]
    assert all(c["extra"] == {"response_format": agent.STEP_FORMAT} and c["temperature"] == 0.0 for c in agent_calls)
    assert {(r["temperature"], r["seed"]) for r in run_records(tmp_path)} == {(0.0, 0)}


def test_the_card_preset_samples_with_its_own_seed_and_the_judge_stays_at_zero(tmp_path):
    _, _, chat = go(tmp_path, "card")
    records = run_records(tmp_path)
    assert {(r["temperature"], r["top_p"], r["top_k"]) for r in records} == {(1.0, 0.95, 64)}
    assert len({r["seed"] for r in records}) == 2
    agent_calls = [c for c in chat.calls if c["content"] is None]
    assert all(c["extra"]["top_k"] == 64 and c["extra"]["temperature"] == 1.0 for c in agent_calls)
    judge_calls = [c for c in chat.calls if c["content"] is not None]
    assert judge_calls and all(c["temperature"] == 0.0 and "seed" not in c["extra"] and c["max_tokens"] == 200
                               for c in judge_calls)


def test_a_task_uses_the_tools_at_its_own_addresses():
    made = []
    tools = agent_eval.toolkit({}, "http://ml", "dsn://db", lambda config, dsn: made.append(dsn) or dsn,
                               lambda ml: made.append(ml) or ml)
    assert tools({}) == {"retrieve": "dsn://db", "predict": "http://ml"}
    assert tools({"ml_url": "http://127.0.0.1:1"})["predict"] == "http://127.0.0.1:1"
    assert tools({"dsn": "dsn://closed"})["retrieve"] == "dsn://closed"
    tools({})
    assert made == ["dsn://db", "http://ml", "http://127.0.0.1:1", "dsn://closed"]


def test_the_means_count_every_task_and_both_costs(tmp_path):
    rows, judged, _ = go(tmp_path)
    result = agent_eval.metrics(rows, judged)
    assert result["pass_rate"] == 1.0 and result["pass_rate_fault"] == 1.0
    assert result["mean_tool_attempts"] == (1 + 4) / 2 and result["mean_model_calls"] == (2 + 5) / 2
    assert result["mean_cost_usd"] == pytest.approx(sum(r["cost_usd"] for r in rows) / 2)
    assert result["steps_over_budget"] == 1 and result["judge_tokens_in"] == 1000
    assert all(r["cost_minute_usd"] == pytest.approx(r["seconds"] * 0.01 / 60) for r in rows)
    assert round(26.0 * agent_eval.USD_PER_MINUTE / 60, 6) == 0.004333  # the 26.0 s combined trace


def test_a_dirty_tree_stops_before_the_first_task(monkeypatch):
    from landcover import train

    def dirty():
        raise RuntimeError("uncommitted changes; commit them first")

    monkeypatch.setattr(train, "clean_head", dirty)
    monkeypatch.setattr(agent_eval, "evaluate", lambda *a, **k: pytest.fail("a task ran"))
    monkeypatch.setattr(answer, "chat", lambda *a, **k: pytest.fail("the model was called"))
    with pytest.raises(RuntimeError, match="uncommitted"):
        agent_eval.run()


# Tracking


def test_the_runner_does_not_load_mlflow_on_import():
    code = "import sys; import landcover.agent_eval; print('mlflow' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                            cwd=agent.ROOT, env={"PYTHONPATH": str(agent.ROOT / "src")})
    assert result.stdout.strip() == "False"


def test_the_logged_run_carries_its_identity(monkeypatch, tmp_path):
    seen = {}
    fake = types.SimpleNamespace(
        set_experiment=lambda name: seen.update(experiment=name),
        start_run=lambda run_name: _Run(seen, run_name),
        log_params=lambda p: seen.update(params=p), set_tags=lambda t: seen.update(tags=t),
        log_metrics=lambda m: seen.update(metrics=m), log_artifacts=lambda d: seen.update(artifacts=d))
    monkeypatch.setitem(sys.modules, "mlflow", fake)
    identity = {key: f"v-{key}" for key in agent_eval.PARAMS + agent_eval.TAGS} | {"sampling": "card"}
    assert agent_eval.log(identity, {"pass_rate": 0.5}, tmp_path) == "run-id"
    assert seen["experiment"] == "landcover-agent" and seen["run_name"] == "agent-eval-card"
    assert {"git_commit", "task_set", "prompt_hash", "judge_prompt_hash", "index_version"} <= set(seen["tags"])
    assert seen["metrics"] == {"pass_rate": 0.5} and seen["artifacts"] == str(tmp_path)


class _Run:
    def __init__(self, seen, run_name):
        seen["run_name"] = run_name
        self.info = types.SimpleNamespace(run_id="run-id")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

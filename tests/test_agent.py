import base64
import io
import json
import subprocess
import sys
import urllib.error

import psycopg
import pytest

from landcover import agent, answer, retrieval

LLM = {"base_url": "http://127.0.0.1:8081/v1", "model": "gemma-4-12b-it-qat-q4_0", "temperature": 0.0,
       "max_tokens": 256, "shadow_usd_per_mtok_in": 2.0, "shadow_usd_per_mtok_out": 10.0}
PASSAGE = {"chunk_id": "export-contract:3", "doc_id": "export-contract", "doc_version": "0123456789ab",
           "locator": "5.1 Problem statement", "distance": 0.12, "text": "ID 255 marks ignored and invalid pixels."}


def step(action, text, reason="r"):
    return {"reason": reason, "action": action, "text": text}


def reply(text, finish_reason="stop"):
    return {"text": text, "finish_reason": finish_reason, "prompt_tokens": 2000, "completion_tokens": 50,
            "cached_tokens": 0, "seconds": 0.5}


def scripted(*items):
    """ask() that answers with the items in order: a step dict, a reply dict or an exception to raise."""
    items = iter(items)

    def ask(messages):
        ask.seen.append([dict(m) for m in messages])
        item = next(items)
        if isinstance(item, BaseException):
            raise item
        return item if "finish_reason" in item else reply(json.dumps(item))

    ask.seen = []
    return ask


class Tools(dict):
    """Fake retrieve and predict that record their calls; `fail` maps a tool to the exception it raises."""

    def __init__(self, fail=None):
        super().__init__(retrieve=self.retrieve, predict=self.predict)
        self.calls, self.fail = [], fail or {}

    def retrieve(self, text, state):
        self.calls.append(("retrieve", text))
        if "retrieve" in self.fail:
            raise self.fail["retrieve"]
        n = len(state["passages"]) + 1
        state["passages"].append({"n": n, **PASSAGE})
        return answer.passages([PASSAGE], n), {"index_version": "5570e99ba60e", "passages": state["passages"][-1:]}

    def predict(self, text, state):
        self.calls.append(("predict", text))
        if "predict" in self.fail:
            raise self.fail["predict"]
        return '{"model_version": "3"}', {"request_id": "r1", "model_version": "3", "mask_bytes": 10}


def records(end):
    with open(end["trace"]) as f:
        return [json.loads(line) for line in f]


def go(tmp_path, ask, tools=None, task="What does 255 mean?"):
    return agent.run(task, ask, Tools() if tools is None else tools, LLM, "system prompt", tmp_path)


# The loop


def test_a_combined_task_is_answered_with_two_attempts_and_cited_sources(tmp_path):
    tools = Tools()
    end = go(tmp_path, scripted(step("predict", "D017-2021/AA-S2-9_2-7"), step("retrieve", "value 255 in the mask"),
                                step("answer", "Version 3 served it; 255 marks invalid pixels.\nSources: [1]")),
             tools)
    assert tools.calls == [("predict", "D017-2021/AA-S2-9_2-7"), ("retrieve", "value 255 in the mask")]
    assert (end["stop_reason"], end["stopped_by"], end["tool_attempts"], end["model_calls"]) == ("answered", "model",
                                                                                                 2, 3)
    assert end["sources"] == [{"n": 1, "doc_id": "export-contract", "doc_version": "0123456789ab",
                               "locator": "5.1 Problem statement"}]


def test_the_model_sees_each_tool_result_before_its_next_step(tmp_path):
    ask = scripted(step("retrieve", "q"), step("answer", "a\nSources: none"))
    go(tmp_path, ask)
    assert [m["role"] for m in ask.seen[1]] == ["system", "user", "assistant", "user"]
    assert ask.seen[1][-1]["content"].startswith("Result of retrieve:\n\n[1] export-contract, 5.1 Problem statement")


def test_a_refusal_by_the_model_runs_no_tool(tmp_path):
    tools = Tools()
    end = go(tmp_path, scripted(step("refuse", "Only the operator can promote a model.")), tools,
             task="Promote version 1 to champion.")
    assert (end["stop_reason"], end["stopped_by"], end["tool_attempts"]) == ("refused", "model", 0)
    assert tools.calls == []


@pytest.mark.parametrize("before", [0, 4])
def test_an_action_outside_the_allowlist_is_refused_by_the_code(tmp_path, before):
    tools = Tools(fail={"predict": agent.ToolError("down", retryable=True)})
    tools["promote"] = lambda text, state: pytest.fail("an unlisted tool ran")
    end = go(tmp_path, scripted(*[step("predict", "D017-2021/t")] * before, step("promote", "champion 1")), tools)
    assert (end["stop_reason"], end["stopped_by"]) == ("refused", "code")
    assert "'promote' is not an allowed action" in end["message"]
    assert records(end)[-2]["status"] == "not_allowed"


def test_four_retryable_failures_spend_the_budget(tmp_path):
    tools = Tools(fail={"predict": agent.ToolError("http://127.0.0.1:1/predict is unreachable", retryable=True)})
    end = go(tmp_path, scripted(*[step("predict", "D017-2021/t")] * 5), tools)
    assert (end["stop_reason"], end["stopped_by"]) == ("budget_exhausted", "code")
    assert (end["tool_attempts"], end["model_calls"], len(tools.calls)) == (4, 5, 4)
    assert "budget of 4 tool attempts" in end["message"] and "unreachable" in end["message"]
    steps = [r for r in records(end) if r["record"] == "step"]
    assert [s["status"] for s in steps] == ["error"] * 4 + ["over_budget"]
    assert all(s["retryable"] for s in steps[:4])


def test_an_answer_on_the_fifth_call_is_kept(tmp_path):
    ask = scripted(*[step("retrieve", f"q{i}") for i in range(4)], step("answer", "a\nSources: [4]"))
    end = go(tmp_path, ask)
    assert (end["stop_reason"], end["tool_attempts"], end["model_calls"]) == ("answered", 4, 5)
    assert end["sources"][0]["n"] == 4


def test_a_call_that_succeeded_is_not_run_again_but_spends_an_attempt(tmp_path):
    tools = Tools()
    end = go(tmp_path, scripted(step("retrieve", "value 255"), step("retrieve", " value 255 "),
                                step("cannot", "The passages do not say.")), tools)
    assert tools.calls == [("retrieve", "value 255")]
    assert (end["stop_reason"], end["stopped_by"], end["tool_attempts"]) == ("unable", "model", 2)
    assert [r.get("status") for r in records(end)][2] == "duplicate"


def test_a_call_that_failed_is_run_again(tmp_path):
    tools = Tools(fail={"retrieve": agent.ToolError("the database is unreachable", retryable=True)})
    go(tmp_path, scripted(step("retrieve", "q"), step("retrieve", "q"), step("cannot", "down")), tools)
    assert tools.calls == [("retrieve", "q"), ("retrieve", "q")]


def test_invalid_arguments_and_unexpected_tool_failures_reach_the_model(tmp_path):
    tools = Tools(fail={"predict": agent.InvalidArguments("not an allowed tile"), "retrieve": KeyError("x")})
    ask = scripted(step("predict", "../etc"), step("retrieve", "q"), step("cannot", "no"))
    end = go(tmp_path, ask, tools)
    statuses = [(r.get("status"), r.get("retryable")) for r in records(end)[1:3]]
    assert statuses == [("invalid_arguments", False), ("error", False)]
    assert ask.seen[1][-1]["content"] == "Error from predict (not retryable): not an allowed tile"


@pytest.mark.parametrize("failure", [urllib.error.URLError("refused"), ValueError("bad JSON"),
                                     reply('{"reason": "r", "action": "answer", "te', "length"),
                                     reply('{"action": "answer"}')])
def test_a_failed_or_unusable_model_call_ends_unable_by_the_code(tmp_path, failure):
    end = go(tmp_path, scripted(failure))
    assert (end["stop_reason"], end["stopped_by"], end["model_calls"]) == ("unable", "code", 1)
    steps = [r for r in records(end) if r["record"] == "step"]
    assert [s["status"] for s in steps] == ([] if isinstance(failure, Exception) else ["invalid_reply"])


def test_a_text_model_failure_names_the_server(tmp_path):
    end = go(tmp_path, scripted(urllib.error.URLError("Connection refused")))
    assert end["message"].startswith("The text model at http://127.0.0.1:8081/v1 failed: URLError")


# The trace


def test_the_trace_holds_a_run_record_every_reply_and_an_end_record(tmp_path):
    end = go(tmp_path, scripted(step("retrieve", "q"), step("predict", "D017-2021/t"), step("answer", "a")))
    lines = records(end)
    assert [r["record"] for r in lines] == ["run", "step", "step", "step", "end"]
    assert lines[0]["budget"] == 4 and lines[0]["tools"] == ["retrieve", "predict"]
    assert lines[0]["shadow_usd_per_mtok_in"] == 2.0 and lines[0]["shadow_usd_per_mtok_out"] == 10.0
    tool = lines[1]
    assert (tool["attempt"], tool["input"], tool["status"], tool["output"]["index_version"]) == (1, "q", "ok",
                                                                                                 "5570e99ba60e")
    assert tool["output"]["passages"][0]["chunk_id"] == "export-contract:3"
    assert all(key in tool for key in ("model_s", "tool_s", "prompt_tokens", "completion_tokens", "reason"))


def test_every_step_is_priced_and_the_end_record_sums_them(tmp_path):
    tools = Tools(fail={"predict": agent.ToolError("down", retryable=True)})
    end = go(tmp_path, scripted(*[step("predict", "D017-2021/t")] * 5), tools)
    steps = [r for r in records(end) if r["record"] == "step"]
    assert all(s["cost_usd"] == pytest.approx(0.0045) for s in steps)
    assert end["cost_usd"] == pytest.approx(sum(s["cost_usd"] for s in steps))
    assert (end["tokens_in"], end["tokens_out"]) == (10_000, 250)
    assert records(end)[-1]["cost_usd"] == pytest.approx(5 * 0.0045)


def test_two_runs_write_two_files(tmp_path):
    first = go(tmp_path, scripted(step("answer", "a")))
    second = go(tmp_path, scripted(step("answer", "a")))
    assert first["trace"] != second["trace"] and len(list(tmp_path.glob("*.jsonl"))) == 2


def test_an_interrupted_run_keeps_its_finished_steps(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        go(tmp_path, scripted(step("retrieve", "a"), step("retrieve", "b"), KeyboardInterrupt()))
    (path,) = tmp_path.glob("*.jsonl")
    assert [json.loads(line)["record"] for line in path.read_text().splitlines()] == ["run", "step", "step"]


def test_the_run_record_takes_the_given_configuration(tmp_path):
    end = agent.run("t", scripted(step("answer", "a")), Tools(), LLM, "p", tmp_path,
                    {"prompt_hash": "abc", "ml_url": "http://127.0.0.1:1"})
    assert records(end)[0]["ml_url"] == "http://127.0.0.1:1" and records(end)[0]["prompt_hash"] == "abc"


def test_working_traces_are_ignored_by_git_and_the_evidence_copies_are_not():
    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=agent.ROOT, check=False).returncode == 0

    assert ignored("traces/x.jsonl") and not ignored("docs/traces/x.jsonl")


# The prompt and the module


def test_the_prompt_names_every_action_and_leaves_the_count_to_the_code():
    text, _ = answer.read_prompt(agent.PROMPT)
    for action in (*agent.ALLOWED, *agent.STOPS):
        assert f"- {action}:" in text
    # A number in the prompt made the model count its own calls and stop early (README, Lab 5: agent).
    assert str(agent.BUDGET) not in text and "{" not in text


def test_the_agent_does_not_load_the_registry_client():
    code = "import sys; import landcover.agent; print('mlflow' in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                            cwd=agent.ROOT, env={"PYTHONPATH": str(agent.ROOT / "src")})
    assert result.stdout.strip() == "False"


def test_an_empty_task_is_a_usage_error_before_the_model_is_called(monkeypatch):
    monkeypatch.setattr(answer, "chat", lambda *a, **k: pytest.fail("the model was called"))
    with pytest.raises(SystemExit) as exit_:
        agent.main(["   "])
    assert exit_.value.code == 2


# retrieve


@pytest.fixture
def database(monkeypatch):
    """The corpus, embedder, connection, index check and retrieval replaced; `calls` counts connections."""
    calls = {"connect": 0, "index": "5570e99ba60e"}

    def connect(dsn, connect_timeout):
        calls["connect"] += 1
        return _Conn()

    def check_index(conn, config, docs):
        if calls["index"] != "5570e99ba60e":
            raise RuntimeError(f"the index is {calls['index']}, the committed corpus and configuration give "
                               "5570e99ba60e; run make retrieval-index")
        return calls["index"]

    monkeypatch.setattr(retrieval, "load_manifest", list)
    monkeypatch.setattr(retrieval, "documents", lambda manifest: [])
    monkeypatch.setattr(retrieval, "embedder", lambda config: lambda texts: [[0.0]] * len(texts))
    monkeypatch.setattr(agent.psycopg, "connect", connect)
    monkeypatch.setattr(retrieval, "check_index", check_index)
    monkeypatch.setattr(retrieval, "retrieve", lambda conn, query, k, embed: [
        {**PASSAGE, "chunk_id": f"export-contract:{i}"} for i in range(k)])
    return calls


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_retrieval_numbers_continue_across_a_run(database):
    tool, state = agent.retriever({"top_k": 3}, "postgresql://x"), {"run_id": "r", "passages": []}
    first, _ = tool("value 255", state)
    second, output = tool("class 0", state)
    assert first.startswith("[1] ") and "[3] " in first and second.startswith("[4] ") and "[6] " in second
    assert [p["n"] for p in output["passages"]] == [4, 5, 6]
    assert output["index_version"] == "5570e99ba60e" and output["passages"][0]["distance"] == 0.12
    assert "load_s" not in output


@pytest.mark.parametrize("query", ["", "   ", "x" * 2001])
def test_an_empty_or_oversized_query_opens_no_connection(database, query):
    with pytest.raises(agent.InvalidArguments):
        agent.retriever({"top_k": 3}, "postgresql://x")(query, {"run_id": "r", "passages": []})
    assert database["connect"] == 0


def test_a_stale_index_is_not_retryable(database):
    database["index"] = "000000000000"
    with pytest.raises(agent.ToolError, match="5570e99ba60e") as err:
        agent.retriever({"top_k": 3}, "postgresql://x")("q", {"run_id": "r", "passages": []})
    assert not err.value.retryable


def test_an_unreachable_database_is_retryable(database, monkeypatch):
    def refuse(dsn, connect_timeout):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(agent.psycopg, "connect", refuse)
    with pytest.raises(agent.ToolError) as err:
        agent.retriever({"top_k": 3}, "postgresql://x")("q", {"run_id": "r", "passages": []})
    assert err.value.retryable


# predict

RESPONSE = {"request_id": "6f1c", "model_name": "landcover-segmenter", "model_version": "3", "image_commit": "abc",
            "width": 512, "height": 512, "valid_px": 262144,
            "features": {"mean_r": 1.0, "mean_g": 2.0, "mean_b": 3.0, "brightness": 123.456},
            "class_shares": {"bareland": 0.123456, "tree": 0.876544}, "dark_warning": None,
            "mask": base64.b64encode(b"mask bytes").decode()}


@pytest.fixture
def tiles(tmp_path):
    folder = tmp_path / "images"
    folder.mkdir()
    for name in ("AA-S2-9_2-7", "AF-S2-11_1-4"):
        (folder / f"{name}.tif").write_bytes(name.encode())
    return folder


@pytest.fixture
def endpoint(monkeypatch):
    """urlopen replaced: records the requests and answers with `endpoint["answer"]` or raises it."""
    sent = {"requests": [], "answer": RESPONSE}

    def urlopen(request, timeout):
        sent["requests"].append(request)
        if isinstance(sent["answer"], Exception):
            raise sent["answer"]
        return io.BytesIO(json.dumps(sent["answer"]).encode())

    monkeypatch.setattr(agent.urllib.request, "urlopen", urlopen)
    return sent


def test_an_allowed_tile_is_sent_with_an_agent_source_id_and_comes_back_without_its_mask(tiles, endpoint):
    content, output = agent.predictor("http://ml", tiles)(" D017-2021/AA-S2-9_2-7 ", {"run_id": "1a2b3c4d"})
    (request,) = endpoint["requests"]
    assert request.full_url == "http://ml/predict" and request.data == b"AA-S2-9_2-7"
    assert request.get_header("X-source-id") == "agent/1a2b3c4d/D017-2021/AA-S2-9_2-7"
    shown = json.loads(content)
    assert "mask" not in shown and "mask" not in output
    assert shown["model_version"] == "3" and shown["brightness"] == 123.5 and shown["class_shares"]["tree"] == 0.8765
    assert output["mask_bytes"] == 10 and output["mask_sha256"] == retrieval.sha256(b"mask bytes")


@pytest.mark.parametrize("tile_id", ["D073-2022/AA-S2-9_2-7", "D017-2021/../../etc/passwd", "AA-S2-9_2-7",
                                     "D017-2021/unknown", ""])
def test_a_tile_outside_the_list_sends_nothing(tiles, endpoint, tile_id):
    with pytest.raises(agent.InvalidArguments, match="AF-S2-11_1-4"):
        agent.predictor("http://ml", tiles)(tile_id, {"run_id": "r"})
    assert endpoint["requests"] == []


def test_missing_tiles_name_make_sample(tmp_path, endpoint):
    with pytest.raises(agent.ToolError, match="make sample") as err:
        agent.predictor("http://ml", tmp_path / "none")("D017-2021/AA-S2-9_2-7", {"run_id": "r"})
    assert not err.value.retryable


@pytest.mark.parametrize(("failure", "retryable"), [
    (urllib.error.HTTPError("http://ml/predict", 503, "Service Unavailable", {},
                            io.BytesIO(b'{"detail": "landcover-segmenter@champion not loaded"}')), True),
    (urllib.error.HTTPError("http://ml/predict", 400, "Bad Request", {}, io.BytesIO(b'{"detail": "not 8-bit"}')),
     False),
    (urllib.error.URLError(ConnectionRefusedError(61, "Connection refused")), True),
    (TimeoutError("timed out"), True),
])
def test_server_and_connection_errors_are_retryable_and_client_errors_are_not(tiles, endpoint, failure, retryable):
    endpoint["answer"] = failure
    with pytest.raises(agent.ToolError) as err:
        agent.predictor("http://ml", tiles)("D017-2021/AA-S2-9_2-7", {"run_id": "r"})
    assert err.value.retryable is retryable
    if isinstance(failure, urllib.error.HTTPError):
        assert "detail" in str(err.value)

import contextlib
import urllib.error

import pytest
from fastapi.testclient import TestClient

from landcover import answer, retrieval, serve_llm

ROWS = [{"chunk_id": f"c{i}", "doc_id": f"doc{i}", "doc_version": f"v{i}", "locator": f"{i} Section",
         "text": f"passage {i}", "distance": 0.1 * i} for i in range(1, 11)]


def reply(text, prompt_tokens=2000, completion_tokens=40):
    return {"text": text, "finish_reason": "stop", "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens, "cached_tokens": 0, "seconds": 1.5}


@pytest.fixture
def fakes(monkeypatch):
    """The embedder, database, index check and retrieval replaced; chat answers with `fakes["text"]`."""
    calls = {"text": "255 marks invalid pixels.\nSources: [2], [12]", "prompts": []}
    monkeypatch.setattr(retrieval, "embedder", lambda config: lambda texts: [[0.0]] * len(texts))
    monkeypatch.setattr(serve_llm, "connect", lambda timeout=3: contextlib.nullcontext())
    monkeypatch.setattr(retrieval, "check_index", lambda conn, config, docs: "abc123def456")
    monkeypatch.setattr(retrieval, "retrieve", lambda conn, question, k, embed: ROWS[:k])
    monkeypatch.setattr(serve_llm, "served_model", lambda base_url: "gemma-4-12b-it-qat-q4_0")

    def chat(llm, text, max_tokens, **extra):
        calls["prompts"].append(text)
        return reply(calls["text"])

    monkeypatch.setattr(answer, "chat", chat)
    return calls


@pytest.fixture
def client(fakes):
    with TestClient(serve_llm.app) as c:
        yield c


def test_an_answer_lists_the_passages_it_cites_within_k(client, fakes):
    response = client.post("/ask", json={"question": "What does the value 255 mean in the output mask?"})
    assert response.status_code == 200
    body = response.json()
    config = retrieval.load_config()
    _, prompt_hash = answer.read_prompt(answer.PROMPTS / "rag.md")
    assert body["cited"] == [2, 12]
    assert body["sources"] == [{"n": 2, "doc_id": "doc2", "doc_version": "v2", "locator": "2 Section"}]
    assert (body["model"], body["top_k"], body["prompt_hash"]) == (answer.load_llm()["model"], config["top_k"],
                                                                   prompt_hash)
    assert body["index_version"] == "abc123def456" and body["tokens_in"] == 2000
    [prompt] = fakes["prompts"]
    assert "[1] doc1, 1 Section" in prompt and prompt.rstrip().endswith("What does the value 255 mean in the output mask?")


def test_an_answer_without_citations_has_no_sources(client, fakes):
    fakes["text"] = "I do not know.\nSources: none"
    assert client.post("/ask", json={"question": "q"}).json()["sources"] == []


@pytest.mark.parametrize("payload", [{"question": "  "}, {"question": "x" * 2001}, {"question": 5}, {}])
def test_a_bad_question_is_refused_without_a_model_call(client, fakes, payload):
    assert client.post("/ask", json=payload).status_code == 422
    assert fakes["prompts"] == []


def counts():
    return {o: serve_llm.registry.get_sample_value("landcover_requests_total", {"endpoint": "/ask", "outcome": o})
            or 0.0 for o in ("ok", "error")}


def test_a_failing_server_gives_503_and_counts_an_error(client, monkeypatch):
    def down(llm, text, max_tokens, **extra):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(answer, "chat", down)
    before = counts()
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 503 and "Connection refused" in response.json()["detail"]
    assert counts()["error"] - before["error"] == 1


def test_metrics_count_one_answer_with_stages_and_tokens(client):
    def value(name, labels):
        return serve_llm.registry.get_sample_value(name, labels) or 0.0

    before = (counts()["ok"], value("landcover_llm_tokens_total", {"direction": "in"}),
              value("landcover_llm_stage_seconds_count", {"stage": "generate"}))
    client.post("/ask", json={"question": "q"})
    client.get("/health/ready")
    after = (counts()["ok"], value("landcover_llm_tokens_total", {"direction": "in"}),
             value("landcover_llm_stage_seconds_count", {"stage": "generate"}))
    assert [b - a for a, b in zip(before, after, strict=True)] == [1, 2000, 1]
    assert 'endpoint="/health' not in client.get("/metrics").text


def test_ready_only_when_the_server_and_the_index_respond(client, monkeypatch):
    assert client.get("/health/ready").json()["ready"] is True

    def unreachable(base_url):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(serve_llm, "served_model", unreachable)
    response = client.get("/health/ready")
    assert response.status_code == 503 and "127.0.0.1:8081" in response.json()["reason"]
    assert client.get("/health/live").status_code == 200

    def stale(conn, config, docs):
        raise RuntimeError("the index is 111111111111, the committed corpus and configuration give 222222222222")

    monkeypatch.setattr(retrieval, "check_index", stale)
    reason = client.get("/health/ready").json()["reason"]
    assert "111111111111" in reason and "222222222222" in reason


def test_the_server_address_comes_from_the_environment(fakes, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://host.docker.internal:8081/v1")
    seen = []
    monkeypatch.setattr(serve_llm, "served_model", lambda base_url: seen.append(base_url) or "other-model")
    with TestClient(serve_llm.app) as c:
        reason = c.get("/health/ready").json()["reason"]
    assert seen == ["http://host.docker.internal:8081/v1"] and "serves other-model" in reason

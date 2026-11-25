"""Lab 4 LLM service: POST /ask answers a question from the Lab 3 index with the text model outside the container.

    uvicorn landcover.serve_llm:app --host 0.0.0.0 --port 8000

The text model name and settings, top-k, the chunk settings, the embedding model and the prompt come from
retrieval.toml and prompts/rag.md as committed; only LLM_BASE_URL and WAREHOUSE_DSN come from the environment.
"""

import json
import os
import time
import urllib.request
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    ProcessCollector,
    generate_latest,
)

from landcover import answer, retrieval

IMAGE_COMMIT = os.environ.get("IMAGE_COMMIT", "unknown")
MAX_QUESTION_CHARS = int(os.environ.get("MAX_QUESTION_CHARS", "2000"))
SECONDS = (0.5, 1, 2.5, 5, 10, 15, 20, 30, 60, 120)

registry = CollectorRegistry()  # per service: both services share metric names
ProcessCollector(registry=registry)
REQUESTS = Counter("landcover_requests", "Requests by endpoint and outcome", ["endpoint", "outcome"],
                   registry=registry)
LATENCY = Histogram("landcover_request_seconds", "Request latency", ["endpoint"], buckets=SECONDS,
                    registry=registry)
STAGE = Histogram("landcover_llm_stage_seconds", "Time per stage of an answer", ["stage"], buckets=SECONDS,
                  registry=registry)
TOKENS = Counter("landcover_llm_tokens", "Tokens the text model server reported", ["direction"],
                 registry=registry)

setup = {}  # filled at start-up from the committed configuration


def connect(timeout=3):
    return psycopg.connect(os.environ["WAREHOUSE_DSN"], connect_timeout=timeout)


def served_model(base_url):
    """The model ID the server lists first."""
    with urllib.request.urlopen(f"{base_url}/models", timeout=2) as response:
        return json.load(response)["data"][0]["id"]


@asynccontextmanager
async def lifespan(app):
    config = retrieval.load_config()
    llm = answer.load_llm()
    llm["base_url"] = os.environ.get("LLM_BASE_URL") or llm["base_url"]
    template, prompt_hash = answer.read_prompt(answer.PROMPTS / "rag.md")
    setup.update(config=config, llm=llm, template=template, prompt_hash=prompt_hash,
                 docs=retrieval.documents(retrieval.load_manifest()), embed=retrieval.embedder(config))
    yield


app = FastAPI(title="landcover-llm", lifespan=lifespan)


def respond(question):
    """(status, content, outcome) of one question; a failing dependency gives 503 with its reason."""
    config, llm = setup["config"], setup["llm"]
    try:
        with connect() as conn:
            index = retrieval.check_index(conn, config, setup["docs"])
            start = time.perf_counter()
            rows = retrieval.retrieve(conn, question, config["top_k"], setup["embed"])
            retrieval_s = time.perf_counter() - start
        prompt = answer.fill(setup["template"], question=question, passages=answer.passages(rows))
        reply = answer.chat(llm, prompt, llm["max_tokens"])
    except (psycopg.Error, OSError, RuntimeError, ValueError, KeyError) as err:
        return 503, {"detail": f"{type(err).__name__}: {err}"}, "error"
    STAGE.labels("retrieve").observe(retrieval_s)
    STAGE.labels("generate").observe(reply["seconds"])
    TOKENS.labels("in").inc(reply["prompt_tokens"])
    TOKENS.labels("out").inc(reply["completion_tokens"])
    numbers = answer.cited(reply["text"])
    sources = [{"n": n, **{key: rows[n - 1][key] for key in ("doc_id", "doc_version", "locator")}}
               for n in numbers if 1 <= n <= len(rows)]
    return 200, {"answer": reply["text"], "cited": numbers, "sources": sources, "model": llm["model"],
                 "top_k": config["top_k"], "index_version": index, "prompt_hash": setup["prompt_hash"],
                 "image_commit": IMAGE_COMMIT, "tokens_in": reply["prompt_tokens"],
                 "tokens_out": reply["completion_tokens"], "retrieval_s": retrieval_s,
                 "generation_s": reply["seconds"]}, "ok"


@app.post("/ask")
def ask(payload: dict):  # a dict parameter is the JSON body
    start = time.perf_counter()
    question = payload.get("question")
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= MAX_QUESTION_CHARS:
        status, content, outcome = 422, {"detail": f"question must be text of 1 to {MAX_QUESTION_CHARS}"
                                                   " characters"}, "invalid"
    else:
        status, content, outcome = respond(question.strip())
    REQUESTS.labels("/ask", outcome).inc()
    LATENCY.labels("/ask").observe(time.perf_counter() - start)
    return JSONResponse(content, status_code=status)


@app.get("/health/live")
def live():
    return {"live": True}


@app.get("/health/ready")
def ready():
    llm, reasons = setup["llm"], []
    try:
        served = served_model(llm["base_url"])
        if served != llm["model"]:
            reasons.append(f"the text model server serves {served}, retrieval.toml names {llm['model']}")
    except (OSError, ValueError, KeyError, IndexError) as err:
        reasons.append(f"text model server {llm['base_url']} unreachable: {type(err).__name__}: {err}")
    try:
        with connect(timeout=2) as conn:
            index = retrieval.check_index(conn, setup["config"], setup["docs"])
    except (psycopg.Error, RuntimeError, KeyError) as err:
        reasons.append(f"corpus index not usable: {type(err).__name__}: {err}")
    if reasons:
        return JSONResponse({"ready": False, "reason": "; ".join(reasons)}, status_code=503)
    return {"ready": True, "model": llm["model"], "index_version": index, "image_commit": IMAGE_COMMIT}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

"""Lab 5 agent: one task answered by a loop in which the text model picks the retriever or the prediction endpoint.

    python -m landcover.agent "TASK" [--ml URL] [--traces DIR]      # make agent TASK="..." [ML_URL=...]

No framework. Each model call returns one JSON step (STEP_FORMAT) that names a tool or a stop; the code checks the
allowlist and the budget, runs the tool and gives the model its result (openspec add-lab5-agent, design Decisions
1-10). Every run writes traces/<time>-<run id>.jsonl. Needs make llm-server, and for the tools the port-forwards of
make cluster: postgres on 5433 (WAREHOUSE_DSN) and ml (--ml, default ML_URL or http://127.0.0.1:8000).
"""

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from landcover import answer, retrieval

ROOT = retrieval.ROOT
PROMPT = answer.PROMPTS / "agent.md"
TRACES = ROOT / "traces"
# The allowlist. A constant, not configuration: run() checks every action against it before anything runs.
ALLOWED = ("retrieve", "predict")
BUDGET = 4  # tool attempts per task, docs/design.md 6.4: a combined request uses two, two are left for transient failures
STOPS = {"answer": "answered", "cannot": "unable", "refuse": "refused"}
MAX_TASK_CHARS = 2000  # as for /ask
TILE_BATCH = "D017-2021"  # the public tiles predict accepts: the development batch
TILES = ROOT / "data" / "raw" / TILE_BATCH / "images"
PREDICT_TIMEOUT = 30  # seconds; a 512x512 tile takes 1.3 s (docs/design.md 7.3)
FIELDS = ("reason", "action", "text")
STEP_FORMAT = {"type": "json_schema", "json_schema": {"name": "step", "strict": True, "schema": {
    "type": "object",
    "properties": {field: {"type": "string"} for field in FIELDS},  # action is free text: the allowlist is in code
    "required": list(FIELDS),
    "additionalProperties": False,
}}}


class InvalidArguments(ValueError):
    """A tool argument rejected before anything was sent."""


class ToolError(Exception):
    """A tool that could not produce its result; `retryable` says whether calling again can help."""

    def __init__(self, message, retryable):
        super().__init__(message)
        self.retryable = retryable


def describe(err):
    """One line for an error, with the body of an HTTP error, at most 300 characters."""
    if isinstance(err, urllib.error.HTTPError):
        return f"HTTP {err.code}: {err.read().decode(errors='replace')}"[:300]
    return f"{type(err).__name__}: {err}"[:300]


def cost(llm, tokens_in, tokens_out):
    """Shadow cost in USD at the per-million-token rates of retrieval.toml (docs/design.md 6.7)."""
    return (tokens_in * llm["shadow_usd_per_mtok_in"] + tokens_out * llm["shadow_usd_per_mtok_out"]) / 1_000_000


# The tools: tool(text, state) -> (content for the model, output for the trace). state holds the run ID and the
# passages shown so far.


def retriever(config, dsn):
    """The Lab 3 retriever at top_k of retrieval.toml; the embedding model is loaded on the first call."""
    loaded = {}

    def retrieve(query, state):
        query = query.strip()
        if not 1 <= len(query) <= MAX_TASK_CHARS:
            raise InvalidArguments(f"the query must be text of 1 to {MAX_TASK_CHARS} characters")
        if not dsn:
            raise ToolError("WAREHOUSE_DSN is not set", retryable=False)
        output = {}
        if not loaded:
            start = time.perf_counter()
            loaded.update(docs=retrieval.documents(retrieval.load_manifest()), embed=retrieval.embedder(config))
            output["load_s"] = time.perf_counter() - start  # run() keeps it out of the tool's seconds
        try:
            with psycopg.connect(dsn, connect_timeout=3) as conn:
                index = retrieval.check_index(conn, config, loaded["docs"])
                rows = retrieval.retrieve(conn, query, config["top_k"], loaded["embed"])
        except psycopg.OperationalError as err:
            raise ToolError(f"the database is unreachable: {describe(err)}", retryable=True) from None
        except RuntimeError as err:  # a stale or missing index
            raise ToolError(str(err), retryable=False) from None
        start = len(state["passages"]) + 1
        shown = [{"n": n, **{key: row[key] for key in ("chunk_id", "doc_id", "doc_version", "locator", "distance",
                                                       "text")}} for n, row in enumerate(rows, start)]
        state["passages"] += shown
        return answer.passages(rows, start), {**output, "index_version": index, "passages": shown}

    return retrieve


def summary(body):
    """The prediction without its mask (docs/design.md 6.5): what the model sees, and the mask's size and hash."""
    mask = base64.b64decode(body.get("mask") or "")
    kept = {key: body[key] for key in ("request_id", "model_name", "model_version", "width", "height", "valid_px",
                                       "dark_warning")}
    kept["class_shares"] = {name: round(share, 4) for name, share in body["class_shares"].items()}
    kept["brightness"] = round(body["features"]["brightness"], 1)
    return kept, {"mask_bytes": len(mask), "mask_sha256": retrieval.sha256(mask)}


def predictor(ml, tiles=TILES):
    """/predict of the deployed ML service for one public tile, logged with an agent/ source ID."""

    def predict(tile_id, state):
        tile_id = tile_id.strip()
        names = sorted(path.stem for path in Path(tiles).glob("*.tif"))
        if not names:
            raise ToolError(f"no tiles in {tiles}; run make sample", retryable=False)
        batch, _, name = tile_id.partition("/")
        if batch != TILE_BATCH or name not in names:
            raise InvalidArguments(f"{tile_id!r} is not an allowed tile; give {TILE_BATCH}/<tile> with one of: "
                                   + ", ".join(names))
        request = urllib.request.Request(f"{ml}/predict", data=(Path(tiles) / f"{name}.tif").read_bytes(),
                                         headers={"X-Source-Id": f"agent/{state['run_id']}/{tile_id}"})
        try:
            with urllib.request.urlopen(request, timeout=PREDICT_TIMEOUT) as response:
                body = json.load(response)
        except urllib.error.HTTPError as err:  # 5xx: not loaded or failed; 4xx: the image was refused
            raise ToolError(f"{ml}/predict answered {describe(err)}", retryable=err.code >= 500) from None
        except OSError as err:  # refused connection, unknown host, timeout
            raise ToolError(f"{ml}/predict is unreachable: {describe(err)}", retryable=True) from None
        kept, mask = summary(body)
        return json.dumps(kept), {**kept, **mask}

    return predict


# The loop


def parse(reply):
    """The step a reply holds, or None when the reply was cut off or is not one."""
    if reply["finish_reason"] != "stop":
        return None
    try:
        step = json.loads(reply["text"])
    except (TypeError, ValueError):
        return None
    if not isinstance(step, dict) or set(step) != set(FIELDS) or not all(isinstance(step[f], str) for f in FIELDS):
        return None
    return step


def sources(message, passages):
    """Document, version and locator of each passage number an answer names, as /ask reports them."""
    shown = {p["n"]: p for p in passages}
    return [{"n": n, **{key: shown[n][key] for key in ("doc_id", "doc_version", "locator")}}
            for n in answer.cited(message) if n in shown]


def run(task, ask, tools, llm, prompt, trace_dir=TRACES, record=None):
    """Answer one task and write its trace; returns the end record.

    ask(messages) returns a reply as answer.chat does; tools maps each name of ALLOWED to tool(text, state).
    `record` adds fields to the run record. The run makes at most BUDGET tool attempts and BUDGET + 1 model calls.
    """
    run_id, started = uuid.uuid4().hex[:8], datetime.now(UTC)
    path = Path(trace_dir) / f"{started:%Y%m%dT%H%M%SZ}-{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"run_id": run_id, "passages": []}
    messages = [{"role": "system", "content": prompt}, {"role": "user", "content": task}]
    steps, succeeded, calls, attempts, last = [], set(), 0, 0, None
    clock = time.perf_counter()
    with path.open("w") as trace:

        def write(line):
            trace.write(json.dumps(line) + "\n")
            trace.flush()

        write({"record": "run", "run_id": run_id, "started_at": started.isoformat(), "task": task,
               "model": llm["model"], "temperature": llm["temperature"], "max_tokens": llm["max_tokens"],
               "budget": BUDGET, "tools": list(ALLOWED), "shadow_usd_per_mtok_in": llm["shadow_usd_per_mtok_in"],
               "shadow_usd_per_mtok_out": llm["shadow_usd_per_mtok_out"], **(record or {})})

        def log(step, **fields):
            steps.append({**step, **fields})
            write(steps[-1])

        while True:  # every pass spends an attempt or stops, so it ends by call BUDGET + 1
            calls += 1
            try:
                reply = ask(messages)
            except (OSError, ValueError, KeyError) as err:
                outcome = "unable", "code", f"The text model at {llm['base_url']} failed: {describe(err)}"
                break
            step = {"record": "step", "step": calls, "prompt_tokens": reply["prompt_tokens"],
                    "completion_tokens": reply["completion_tokens"], "cached_tokens": reply["cached_tokens"],
                    "model_s": reply["seconds"], "finish_reason": reply["finish_reason"],
                    "cost_usd": cost(llm, reply["prompt_tokens"], reply["completion_tokens"])}
            parsed = parse(reply)
            if parsed is None:
                log(step, status="invalid_reply", text=reply["text"])
                outcome = "unable", "code", (f"The text model returned no usable step (finish_reason "
                                             f"{reply['finish_reason']}).")
                break
            step.update(parsed)
            action, text = parsed["action"], parsed["text"]
            if action in STOPS:
                log(step, status="stop")
                outcome = STOPS[action], "model", text
                break
            if action not in ALLOWED:  # the allowlist: nothing outside it ever runs
                log(step, status="not_allowed")
                outcome = "refused", "code", f"Refused: {action!r} is not an allowed action ({', '.join(ALLOWED)})."
                break
            if attempts == BUDGET:
                log(step, status="over_budget")
                outcome = "budget_exhausted", "code", (f"Stopped: the budget of {BUDGET} tool attempts is spent. "
                                                       f"The last tool result: {last}")
                break
            attempts += 1
            step.update(attempt=attempts, input=text.strip())
            key = (action, text.strip())
            if key in succeeded:
                log(step, status="duplicate")
                result = last = f"Not run: {action} with this text already succeeded; its result is above."
            else:
                start = time.perf_counter()
                try:
                    content, output = tools[action](text, state)
                except InvalidArguments as err:
                    status, error, retryable = "invalid_arguments", str(err), False
                except ToolError as err:
                    status, error, retryable = "error", str(err), err.retryable
                except Exception as err:  # noqa: BLE001  any other failure of a tool is reported, not raised
                    status, error, retryable = "error", describe(err), False
                else:
                    status = "ok"
                tool_s = time.perf_counter() - start
                if status == "ok":
                    succeeded.add(key)
                    log(step, status=status, output=output, tool_s=tool_s - output.get("load_s", 0.0))
                    result, last = f"Result of {action}:\n\n{content}", "ok"
                else:
                    log(step, status=status, error=error, retryable=retryable, tool_s=tool_s)
                    result = last = (f"Error from {action} ({'retryable' if retryable else 'not retryable'}): "
                                     f"{error}")
            messages += [{"role": "assistant", "content": reply["text"]}, {"role": "user", "content": result}]

        reason, by, message = outcome
        end = {"record": "end", "stop_reason": reason, "stopped_by": by, "message": message,
               "sources": sources(message, state["passages"]) if reason == "answered" else [],
               "tool_attempts": attempts, "model_calls": calls,
               "tokens_in": sum(s["prompt_tokens"] for s in steps),
               "tokens_out": sum(s["completion_tokens"] for s in steps),
               "seconds": time.perf_counter() - clock, "cost_usd": sum(s["cost_usd"] for s in steps)}
        write(end)
    return {**end, "trace": str(path)}


# The command


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def server_build(llm):
    try:
        return answer.server_build(llm)
    except RuntimeError as err:  # down, or another model: the run records it, and a down server ends it unable
        return f"unknown ({err})"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.agent")
    parser.add_argument("task", help=f"the task, 1 to {MAX_TASK_CHARS} characters")
    parser.add_argument("--ml", default=os.environ.get("ML_URL") or "http://127.0.0.1:8000",
                        help="the ML service; default ML_URL or http://127.0.0.1:8000")
    parser.add_argument("--traces", default=str(TRACES), help="the trace folder; default traces/")
    args = parser.parse_args(argv)
    task = args.task.strip()
    if not 1 <= len(task) <= MAX_TASK_CHARS:
        parser.error(f"the task must be text of 1 to {MAX_TASK_CHARS} characters")
    llm, config = answer.load_llm(), retrieval.load_config()
    prompt, prompt_hash = answer.read_prompt(PROMPT)
    tools = {"retrieve": retriever(config, os.environ.get("WAREHOUSE_DSN")), "predict": predictor(args.ml)}

    def ask(messages):
        return answer.chat(llm, None, llm["max_tokens"], messages=messages, response_format=STEP_FORMAT)

    end = run(task, ask, tools, llm, prompt, args.traces, {
        "git_commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain")), "mode": "json_schema",
        "server_build": server_build(llm), "seed": 0,  # answer.chat sends seed 0
        "prompt_hash": prompt_hash, "top_k": config["top_k"], "ml_url": args.ml})
    print(end["message"])
    print(f"{end['stop_reason']} (stopped by the {end['stopped_by']}): {end['tool_attempts']} of {BUDGET} tool "
          f"attempts, {end['model_calls']} model calls, tokens {end['tokens_in']} in / {end['tokens_out']} out, "
          f"{end['seconds']:.1f} s, shadow cost ${end['cost_usd']:.4f}, trace {end['trace']}")


if __name__ == "__main__":
    main()

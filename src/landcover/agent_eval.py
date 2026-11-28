"""Lab 5 agent evaluation: run the tasks of eval/tasks.toml through the agent, check each from its trace, log one run.

    python -m landcover.agent_eval [--sampling served|card] [--ml URL] [--traces DIR]   # make agent-eval [SAMPLING=card]

Every task runs once through agent.run with the tools and prompt of `make agent`; its trace alone decides whether it
passed (openspec add-lab5-agent-eval, design Decisions 1-8). Needs make llm-server, the port-forwards of make cluster
(ml 8000, postgres 5433, mlflow 5002 named by MLFLOW_TRACKING_URI) and make sample. mlflow is imported only after
the last task, so no tracking client exists while the agent runs.
"""

import argparse
import functools
import json
import os
import random
import re
import sys
import tomllib
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

import psycopg

from landcover import agent, answer, retrieval

TASKS = retrieval.ROOT / "eval" / "tasks.toml"
TYPES = ("legend", "unanswerable", "predict", "combined", "refusal", "invalid_tile", "fault")
STOP_REASONS = ("answered", "unable", "refused", "budget_exhausted")
TOOL_STATUSES = ("ok", "error", "invalid_arguments", "duplicate")
KEYS = {"id", "type", "task", "stop", "stopped_by", "tools", "order", "forbid", "tile", "ml_url", "dsn", "from",
        "reference", "sources", "names_prediction", "names_top_class", "statuses"}
REQUIRED = {"legend": ("reference", "sources"), "predict": ("tile", "names_prediction"),
            "combined": ("tile", "names_prediction", "sources"), "fault": ("statuses",)}
COUNTED = ("invalid_reply", "not_allowed", "duplicate", "over_budget")  # step statuses reported per run
USD_PER_MINUTE = 0.01  # docs/design.md 6.8: the declared shadow price per minute of run time, reported beside tokens
# The single sampling configuration the Gemma 4 model card recommends for all uses
# (https://ai.google.dev/gemma/docs/core/model_card_4.md); the service itself answers at temperature 0 (design 5.2).
CARD = {"temperature": 1.0, "top_p": 0.95, "top_k": 64}
EXPERIMENT = "landcover-agent"


# The task set


def problems(tasks):
    """What is wrong with the set, each problem naming its task; empty for a valid set."""
    found, seen = [], set()
    for t in tasks:
        name = t.get("id", "?")
        if name in seen:
            found.append(f"{name}: duplicate id")
        seen.add(name)
        if unknown := set(t) - KEYS:
            found.append(f"{name}: unknown fields {sorted(unknown)}")
        if t.get("type") not in TYPES:
            found.append(f"{name}: unknown type {t.get('type')!r}")
        if not str(t.get("task", "")).strip():
            found.append(f"{name}: no task text")
        if not t.get("stop") or set(t["stop"]) - set(STOP_REASONS):
            found.append(f"{name}: stop must be a list of {', '.join(STOP_REASONS)}")
        if t.get("stopped_by", "model") not in ("model", "code"):
            found.append(f"{name}: stopped_by must be model or code")
        if not isinstance(t.get("tools"), list):
            found.append(f"{name}: tools must be a list")
        tools = set(t.get("tools") or []) | set(t.get("forbid", [])) | set(t.get("statuses", {}))
        if tools - set(agent.ALLOWED):
            found.append(f"{name}: unknown tools {sorted(tools - set(agent.ALLOWED))}")
        if t.get("order", "in_order") not in ("in_order", "any"):
            found.append(f"{name}: order must be in_order or any")
        if set(t.get("statuses", {}).values()) - set(TOOL_STATUSES):
            found.append(f"{name}: statuses must be of {', '.join(TOOL_STATUSES)}")
        for key in REQUIRED.get(t.get("type"), ()):
            if not t.get(key):
                found.append(f"{name}: a {t['type']} task needs {key}")
        if t.get("type") == "refusal" and (t.get("tools") or set(t.get("forbid", [])) != set(agent.ALLOWED)):
            found.append(f"{name}: a refusal expects no tool and forbids both")
        if t.get("type") == "fault" and not (t.get("ml_url") or t.get("dsn")):
            found.append(f"{name}: a fault task needs ml_url or dsn")
    return found


def load_tasks(path=TASKS):
    """The tasks and the set identifier, the first 12 hex digits of the SHA-256 of the file; refuses a bad set."""
    data = Path(path).read_bytes()
    tasks = tomllib.loads(data.decode()).get("tasks", [])
    if found := problems(tasks):
        raise ValueError(f"{path}: " + "; ".join(found))
    return tasks, retrieval.sha256(data)[:12]


# The checks: a pure function of a task and its trace


def tools_match(expected, tried, order="in_order"):
    """in_order: expected is a subsequence of the attempted tools, arguments ignored; any: a sub-multiset."""
    if order == "any":
        return not Counter(expected) - Counter(tried)
    rest = iter(tried)
    return all(tool in rest for tool in expected)


def check(task, records):
    """The failed checks of one task's trace records, in words; empty when every script check holds."""
    if not records or records[-1].get("record") != "end":
        return ["the trace has no end record"]
    end, failed = records[-1], []
    if end["stop_reason"] not in task["stop"]:
        failed.append(f"stopped {end['stop_reason']}, expected {' or '.join(task['stop'])}")
    if task.get("stopped_by") and end["stopped_by"] != task["stopped_by"]:
        failed.append(f"stopped by the {end['stopped_by']}, expected the {task['stopped_by']}")
    attempts = [r for r in records if r.get("record") == "step" and "attempt" in r]
    tried = [r["action"] for r in attempts]
    order = task.get("order", "in_order")
    if not tools_match(task["tools"], tried, order):
        failed.append(f"tools {tried}, expected {task['tools']}{' in any order' if order == 'any' else ''}")
    failed += [f"forbidden tool attempted: {tool}" for tool in task.get("forbid", []) if tool in tried]
    for tool, status in task.get("statuses", {}).items():
        if other := [r["status"] for r in attempts if r["action"] == tool and r["status"] != status]:
            failed.append(f"{tool} attempts with status {', '.join(other)}, expected {status}")
    ok = [r for r in attempts if r["status"] == "ok"]
    message = end["message"]
    if task.get("sources"):
        shown = {p["n"]: p for r in ok if r["action"] == "retrieve" for p in r["output"]["passages"]}
        if not any(s["n"] in shown and retrieval.relevant(shown[s["n"]], task["sources"]) for s in end["sources"]):
            failed.append("no cited passage holds the reference evidence")
    if task.get("names_prediction") or task.get("names_top_class"):
        predictions = [r["output"] for r in ok if r["action"] == "predict"]
        if not predictions:
            failed.append("no successful prediction")
        else:
            p = predictions[-1]
            version = re.escape(str(p["model_version"]))
            if task.get("names_prediction") and (p["request_id"] not in message or not re.search(
                    rf"\bversion\s+{version}\b", message, flags=re.IGNORECASE)):
                failed.append(f"the answer does not name version {p['model_version']} and request {p['request_id']}")
            top = max(p["class_shares"], key=p["class_shares"].get)
            if task.get("names_top_class") and top.lower() not in message.lower():
                failed.append(f"the answer does not name the largest class, {top}")
    return failed


# The runner


def toolkit(config, ml, dsn, make_retriever=agent.retriever, make_predictor=agent.predictor):
    """tools(task): the agent's tools at the task's own addresses (ml_url, dsn) or the command's, each built once."""
    retrievers, predictors = {}, {}

    def tools(task):
        d, m = task.get("dsn", dsn), task.get("ml_url", ml)
        if d not in retrievers:
            retrievers[d] = make_retriever(config, d)
        if m not in predictors:
            predictors[m] = make_predictor(m)
        return {"retrieve": retrievers[d], "predict": predictors[m]}

    return tools


def sampling_for(sampling, rng):
    """(fields sent with every model call of a task, fields for its run record)."""
    if sampling == "served":  # retrieval.toml as it is: answer.chat sends its temperature and seed 0
        return {}, {"seed": 0}
    seed = rng.randrange(2**31)  # without its own seed a sampled run repeats itself
    return {**CARD, "seed": seed}, {"seed": seed, "top_p": CARD["top_p"], "top_k": CARD["top_k"]}


def read_trace(path):
    with open(path) as f:
        return [json.loads(line) for line in f]


def evaluate(tasks, chat, tools, llm, prompt, judge_template, folder, sampling="served", record=None, rng=None):
    """Run every task once through agent.run, check it from its trace and judge those with a reference.

    chat has the signature of answer.chat; tools(task) gives the task's tools. Returns (rows, judged replies).
    The judge always uses `llm` as configured (temperature 0), whatever the sampling of the agent.
    """
    rng = rng or random.SystemRandom()
    rows = []
    for task in tasks:
        extra, fields = sampling_for(sampling, rng)
        task_llm = {**llm, "temperature": extra.get("temperature", llm["temperature"])}
        ask = functools.partial(chat, task_llm, None, llm["max_tokens"], response_format=agent.STEP_FORMAT, **extra)
        addresses = {key: task[key] for key in ("ml_url", "dsn") if key in task}
        end = agent.run(task["task"], lambda messages, ask=ask: ask(messages=messages), tools(task), task_llm, prompt,
                        folder, {**(record or {}), "task_id": task["id"], **fields, **addresses})
        records = read_trace(end["trace"])
        rows.append({
            "id": task["id"], "type": task["type"], "failed": check(task, records), "verdict": None,
            "judge_reason": None, "stop_reason": end["stop_reason"], "stopped_by": end["stopped_by"],
            "tool_attempts": end["tool_attempts"], "model_calls": end["model_calls"], "tokens_in": end["tokens_in"],
            "tokens_out": end["tokens_out"], "seconds": end["seconds"], "cost_usd": end["cost_usd"],
            "cost_minute_usd": end["seconds"] * USD_PER_MINUTE / 60, "seed": fields["seed"],
            "statuses": dict(Counter(r["status"] for r in records if r.get("record") == "step")),
            "message": end["message"], "trace": Path(end["trace"]).name})
    judged_tasks = [(t, r) for t, r in zip(tasks, rows, strict=True)
                    if t.get("reference") and r["stop_reason"] == "answered"]
    judged = answer.judge_all([{"id": t["id"], "question": t["task"], "answer": t["reference"]} for t, _ in judged_tasks],
                              [{"text": r["message"]} for _, r in judged_tasks],
                              lambda text, **kw: chat(llm, text, llm["judge_max_tokens"], **kw), judge_template)
    for (_, row), j in zip(judged_tasks, judged, strict=True):
        row["verdict"], row["judge_reason"] = j["verdict"], j["reason"]
    for task, row in zip(tasks, rows, strict=True):
        row["passed"] = not row["failed"] and (not task.get("reference") or row["verdict"] == "correct")
    return rows, judged


def metrics(rows, judged):
    """Pass rate overall and per type, means per task (every task counts, failures included), step status counts."""
    n = len(rows)
    result = {"pass_rate": sum(r["passed"] for r in rows) / n}
    for kind in sorted({r["type"] for r in rows}):
        of_kind = [r for r in rows if r["type"] == kind]
        result[f"pass_rate_{kind}"] = sum(r["passed"] for r in of_kind) / len(of_kind)
    for key in ("tool_attempts", "model_calls", "tokens_in", "tokens_out", "seconds", "cost_usd", "cost_minute_usd"):
        result[f"mean_{key}"] = sum(r[key] for r in rows) / n
    for status in COUNTED:
        result[f"steps_{status}"] = sum(r["statuses"].get(status, 0) for r in rows)
    result["judge_tokens_in"] = sum(j["prompt_tokens"] for j in judged)
    result["judge_tokens_out"] = sum(j["completion_tokens"] for j in judged)
    return result


PARAMS = ("llm_model", "llm_server_build", "sampling", "temperature", "top_p", "top_k", "max_tokens", "budget",
          "top_k_retrieval", "ml_url", "tasks", "judge_model", "shadow_usd_per_mtok_in", "shadow_usd_per_mtok_out",
          "usd_per_minute")
TAGS = ("git_commit", "task_set", "prompt_hash", "judge_prompt_hash", "index_version", "eval_id")


def log(identity, result, folder):
    """One MLflow run in landcover-agent with the identity, the metrics and the run's folder; returns its ID."""
    import mlflow  # only now: no tracking client exists while the agent runs

    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=f"agent-eval-{identity['sampling']}") as run:
        mlflow.log_params({key: identity[key] for key in PARAMS})
        mlflow.set_tags({key: identity[key] for key in TAGS})
        mlflow.log_metrics(result)
        mlflow.log_artifacts(str(folder))  # results.json and the traces
    return run.info.run_id


def ready(ml):
    try:
        with urllib.request.urlopen(f"{ml}/health/ready", timeout=5):
            pass
    except OSError as err:  # HTTPError included
        raise RuntimeError(f"the ML service at {ml} is not ready ({agent.describe(err)})") from None


def run(sampling="served", ml="http://127.0.0.1:8000", traces=agent.TRACES):
    """Check the system, run the set once, write results.json, log one MLflow run; returns the printed text."""
    from landcover.train import clean_head

    commit = clean_head()
    llm, config = answer.load_llm(), retrieval.load_config()
    build = answer.server_build(llm)
    tasks, task_set = load_tasks()
    prompt, prompt_hash = answer.read_prompt(agent.PROMPT)
    judge, judge_hash = answer.read_prompt(answer.PROMPTS / "judge.md")
    dsn = os.environ.get("WAREHOUSE_DSN")
    if not dsn:
        raise RuntimeError("WAREHOUSE_DSN is not set")
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            index = retrieval.check_index(conn, config, retrieval.documents(retrieval.load_manifest()))
    except psycopg.OperationalError as err:
        raise RuntimeError(f"the database of WAREHOUSE_DSN is unreachable: {agent.describe(err)}") from None
    ready(ml)
    missing = [t["id"] for t in tasks if t.get("tile") and (
        t["tile"].partition("/")[0] != agent.TILE_BATCH
        or not (agent.TILES / f"{t['tile'].partition('/')[2]}.tif").exists())]
    if missing:
        raise RuntimeError(f"tasks {', '.join(missing)} name tiles missing from {agent.TILES}; run make sample")

    eval_id = uuid.uuid4().hex[:8]
    folder = Path(traces) / f"eval-{eval_id}"
    record = {"eval_id": eval_id, "git_commit": commit, "dirty": False, "mode": "json_schema", "server_build": build,
              "prompt_hash": prompt_hash, "top_k": config["top_k"], "ml_url": ml}
    rows, judged = evaluate(tasks, answer.chat, toolkit(config, ml, dsn), llm, prompt, judge, folder, sampling, record)
    result = metrics(rows, judged)
    sampled = CARD if sampling == "card" else {"temperature": llm["temperature"], "top_p": "server", "top_k": "server"}
    identity = {"eval_id": eval_id, "git_commit": commit, "task_set": task_set, "prompt_hash": prompt_hash,
                "judge_prompt_hash": judge_hash, "index_version": index, "llm_model": llm["model"],
                "llm_server_build": build, "sampling": sampling, **sampled, "max_tokens": llm["max_tokens"],
                "budget": agent.BUDGET, "top_k_retrieval": config["top_k"], "ml_url": ml, "tasks": len(tasks),
                "judge_model": llm["model"], "shadow_usd_per_mtok_in": llm["shadow_usd_per_mtok_in"],
                "shadow_usd_per_mtok_out": llm["shadow_usd_per_mtok_out"], "usd_per_minute": USD_PER_MINUTE}
    (folder / "results.json").write_text(json.dumps({"identity": identity, "metrics": result, "tasks": rows},
                                                    indent=2) + "\n")
    try:
        run_id = log(identity, result, folder)
    except Exception as err:  # noqa: BLE001  the results stay in the folder whatever the tracking server did
        raise RuntimeError(f"could not log to MLFLOW_TRACKING_URI {os.environ.get('MLFLOW_TRACKING_URI')} "
                           f"({type(err).__name__}: {err}); the traces and results.json are in {folder}") from None
    failed = [f"{r['id']}: " + "; ".join(r["failed"] + (["judged incorrect"] if r["verdict"] == "incorrect" else []))
              for r in rows if not r["passed"]]
    passed = sum(r["passed"] for r in rows)
    return "\n".join([*failed, (
        f"run {run_id[:8]} ({sampling}): passed {passed} of {len(rows)} ({result['pass_rate']:.3f}), "
        f"mean {result['mean_tool_attempts']:.2f} tool attempts and {result['mean_model_calls']:.2f} model calls, "
        f"shadow cost ${result['mean_cost_usd']:.4f} per task (${result['mean_cost_minute_usd']:.4f} at "
        f"${USD_PER_MINUTE}/min), tasks {task_set}, prompt {prompt_hash}, index {index}, folder {folder}")])


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.agent_eval")
    parser.add_argument("--sampling", choices=["served", "card"], default="served",
                        help="served: retrieval.toml as /ask uses it (default); card: the Gemma 4 model card sampling")
    parser.add_argument("--ml", default=os.environ.get("ML_URL") or "http://127.0.0.1:8000",
                        help="the ML service; default ML_URL or http://127.0.0.1:8000")
    parser.add_argument("--traces", default=str(agent.TRACES), help="the parent of the eval folder; default traces/")
    args = parser.parse_args(argv)
    try:
        print(run(args.sampling, args.ml, args.traces))
    except (ValueError, RuntimeError, OSError) as err:
        sys.exit(f"error: {err}")


if __name__ == "__main__":
    main()

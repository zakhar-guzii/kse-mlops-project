"""Lab 3 answers: answer the evaluation set with a prompt file, judge the answers, log one MLflow run.

Run as `python -m landcover.answer eval [--top-k N]` (make answer-eval [TOP_K=N], docs/design.md 5.2 and 5.4)
with the text model server of `make llm-server` up; a run with top-k needs the group rag and a current index. The client speaks the OpenAI chat completions protocol over the standard library.
"""

import argparse
import json
import os
import re
import sys
import time
import tomllib
import urllib.request
from contextlib import ExitStack
from pathlib import Path

import numpy as np
import psycopg

from landcover.retrieval import (
    CONFIG,
    ROOT,
    check_index,
    documents,
    embedder,
    evaluate,
    load_config,
    load_manifest,
    load_questions,
    retrieve,
    sha256,
)

PROMPTS = ROOT / "prompts"
LLM_KEYS = ("base_url", "model", "temperature", "max_tokens", "judge_max_tokens",
            "shadow_usd_per_mtok_in", "shadow_usd_per_mtok_out")
RETRIEVAL_KEYS = ("chunk_size", "chunk_overlap", "embedding_model", "embedding_revision")
VERDICTS = ("correct", "incorrect")
JUDGE_FORMAT = {"type": "json_schema", "json_schema": {"name": "verdict", "strict": True, "schema": {
    "type": "object",
    "properties": {"reason": {"type": "string"}, "verdict": {"type": "string", "enum": list(VERDICTS)}},
    "required": ["reason", "verdict"],
    "additionalProperties": False,
}}}


def load_llm(path=CONFIG):
    """The table [llm] of the configuration; there are no defaults, so a missing key stops the command."""
    table = tomllib.loads(Path(path).read_text()).get("llm", {})
    missing = [key for key in LLM_KEYS if key not in table]
    if missing:
        raise ValueError(f"{path} lacks {', '.join(f'llm.{key}' for key in missing)}")
    return {key: table[key] for key in LLM_KEYS}


def read_prompt(path):
    """The prompt text and its hash, the first 12 hex digits of the SHA-256 of the file."""
    data = Path(path).read_bytes()
    return data.decode(), sha256(data)[:12]


def fill(template, **values):
    """Replace each {name} given in one pass over the template, so a value is never filled again; a name the prompt
    lacks raises, and other braces stay."""
    for key in values:
        if f"{{{key}}}" not in template:
            raise ValueError(f"the prompt has no placeholder {{{key}}}")
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m[1], m[0]), template)


def passages(rows, start=1):
    """Retrieved rows as numbered passages in the given order from `start`: "[n] doc_id, locator", then the text."""
    return "\n\n".join(f"[{n}] {row['doc_id']}, {row['locator']}\n{row['text'].strip()}"
                       for n, row in enumerate(rows, start))


def cited(text):
    """The passage numbers an answer names as [n] or [n, m], first mention first, each once; "Sources: none" gives []."""
    groups = re.findall(r"\[(\d+(?:\s*,\s*\d+)*)\]", text)
    return list(dict.fromkeys(int(n) for group in groups for n in re.findall(r"\d+", group)))


def chat(llm, content, max_tokens, **extra):
    """One user message to <base_url>/chat/completions; the reply with its usage and client-side seconds."""
    body = {"model": llm["model"], "messages": [{"role": "user", "content": content}],
            "temperature": llm["temperature"], "max_tokens": max_tokens, "seed": 0,
            "reasoning_effort": "none", **extra}  # Gemma 4 otherwise spends max_tokens on reasoning text
    request = urllib.request.Request(f"{llm['base_url']}/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        reply = json.load(response)
    seconds = time.perf_counter() - start
    usage, choice = reply["usage"], reply["choices"][0]
    return {"text": choice["message"]["content"], "finish_reason": choice["finish_reason"],
            "prompt_tokens": usage["prompt_tokens"], "completion_tokens": usage["completion_tokens"],
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),  # None: not reported
            "seconds": seconds}


def answer_all(questions, ask, template, search=None):
    """Every question through the answer prompt, in order; only the first call skips the prompt cache.

    With `search` (question text to ranked rows) each question is retrieved first and the prompt gets the rows
    as numbered passages; the record then carries the rows and the seconds the retrieval took.
    """
    answers = []
    for i, q in enumerate(questions):
        values, extra = {"question": q["question"]}, {}
        if search:
            start = time.perf_counter()
            rows = search(q["question"])
            extra = {"rows": rows, "retrieval_s": time.perf_counter() - start}
            values["passages"] = passages(rows)
        # cache_prompt is llama.cpp's own field; remove it for a server that rejects unknown fields.
        answers.append({**ask(fill(template, **values), **({"cache_prompt": False} if i == 0 else {})), **extra})
    return answers


def names_a_passage(answer, k):
    return any(1 <= n <= k for n in cited(answer["text"]))


def judge_all(questions, answers, ask, template):
    """Each answer judged against its reference answer; anything but the two verdicts names the question."""
    judged = []
    for q, a in zip(questions, answers, strict=True):
        record = ask(fill(template, question=q["question"], reference=q["answer"], answer=a["text"]),
                     response_format=JUDGE_FORMAT)
        try:
            parsed = json.loads(record["text"])
        except json.JSONDecodeError:
            parsed = {}
        if not isinstance(parsed, dict) or parsed.get("verdict") not in VERDICTS:
            raise ValueError(f"{q['id']}: the judge returned no verdict of {' or '.join(VERDICTS)}: "
                             f"{record['text']!r}")
        judged.append({**record, "verdict": parsed["verdict"], "reason": parsed.get("reason", "")})
    return judged


def summarise(answers, judged, llm, found=None, k=0):
    """The run's metrics: answer share, answer-call tokens, seconds, shadow cost and latency; judge tokens apart.

    Latency is retrieval plus the answer call; compute_s is the answer calls only. With `found`, retrieval.evaluate
    of the rows the answers were given at k, the metrics add hit rate, MRR, the retrieval seconds and the answers
    naming a passage. cold_calls is left out when the server did not report cached tokens for every call.
    """
    seconds = [a["seconds"] for a in answers]
    tokens_in = sum(a["prompt_tokens"] for a in answers)
    tokens_out = sum(a["completion_tokens"] for a in answers)
    p50, p95 = np.percentile([a.get("retrieval_s", 0.0) + a["seconds"] for a in answers], [50, 95])
    retrieved, cached = {}, [a["cached_tokens"] for a in answers]
    if found:
        retrieved = {"hit_rate": found["hit_rate"], "mrr": found["mrr"],
                     "retrieval_s": sum(a["retrieval_s"] for a in answers),
                     "cited_answers": sum(names_a_passage(a, k) for a in answers)}
    return {
        "answer_correct": sum(j["verdict"] == "correct" for j in judged) / len(answers),
        **retrieved,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "compute_s": sum(seconds),
        "shadow_cost_usd": (tokens_in * llm["shadow_usd_per_mtok_in"]
                            + tokens_out * llm["shadow_usd_per_mtok_out"]) / 1_000_000,
        "latency_p50_s": float(p50),
        "latency_p95_s": float(p95),
        **({"cold_calls": cached.count(0)} if None not in cached else {}),
        "judge_tokens_in": sum(j["prompt_tokens"] for j in judged),
        "judge_tokens_out": sum(j["completion_tokens"] for j in judged),
    }


def results(questions, answers, judged, found=None):
    """Per question: the answer, how it ended, its verdict and reason, its tokens and seconds.

    With `found`, as for summarise, also the rank of the first relevant passage, the retrieved chunk ids in order, the passage
    numbers the answer names and the retrieval seconds.
    """
    rows = [{"id": q["id"], "answer": a["text"], "finish_reason": a["finish_reason"], "verdict": j["verdict"],
             "reason": j["reason"], "prompt_tokens": a["prompt_tokens"], "completion_tokens": a["completion_tokens"],
             "cached_tokens": a["cached_tokens"], "seconds": a["seconds"]}
            for q, a, j in zip(questions, answers, judged, strict=True)]
    if found:
        for row, a, record in zip(rows, answers, found["results"], strict=True):
            row.update(rank=record["rank"], retrieved=[r["chunk_id"] for r in record["retrieved"]],
                       cited=cited(a["text"]), retrieval_s=a["retrieval_s"])
    return rows


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def server_build(llm):
    """The model the server serves, checked against the configuration, and the build it reports."""
    try:
        served = _get(f"{llm['base_url']}/models")["data"][0]["id"]
    except OSError as err:
        raise RuntimeError(f"no text model server at {llm['base_url']} ({err}); start it with make llm-server")
    if served != llm["model"]:
        raise RuntimeError(f"the server serves {served}, retrieval.toml names {llm['model']}")
    try:  # llama.cpp only; another server records "unknown"
        return _get(f"{llm['base_url'].removesuffix('/v1')}/props")["build_info"]
    except (OSError, KeyError, ValueError):
        return "unknown"


def run(top_k=0):
    """Answer and judge the set and log one MLflow run; returns the printed line.

    top_k 0 is the plain baseline. top_k > 0 retrieves that many passages per question from the current index
    (group rag, WAREHOUSE_DSN) and answers with prompts/rag.md.
    """
    import mlflow

    from landcover.train import clean_head

    commit = clean_head()
    llm = load_llm()
    build = server_build(llm)
    questions, eval_set = load_questions()
    template, prompt_hash = read_prompt(PROMPTS / ("rag.md" if top_k else "plain.md"))
    judge, judge_hash = read_prompt(PROMPTS / "judge.md")

    def ask(text, **extra):
        return chat(llm, text, llm["max_tokens"], **extra)

    retrieval_params, index_tag = {}, {}
    with ExitStack() as stack:
        search = None
        if top_k:
            config = load_config()
            conn = stack.enter_context(psycopg.connect(os.environ["WAREHOUSE_DSN"]))
            index_tag = {"index_version": check_index(conn, config, documents(load_manifest()))}
            retrieval_params = {key: config[key] for key in RETRIEVAL_KEYS}
            embed = embedder(config)

            def search(question):
                return retrieve(conn, question, top_k, embed)

        answers = answer_all(questions, ask, template, search)
    judged = judge_all(questions, answers, lambda text, **extra: chat(llm, text, llm["judge_max_tokens"], **extra),
                       judge)
    found = evaluate(questions, [a["rows"] for a in answers], top_k) if top_k else None
    metrics = summarise(answers, judged, llm, found, top_k)

    mlflow.set_experiment("landcover-answers")
    with mlflow.start_run(run_name=f"answer-rag-k{top_k}" if top_k else "answer-plain") as run:
        mlflow.log_params({"llm_model": llm["model"], "llm_server_build": build, "temperature": llm["temperature"],
                           "max_tokens": llm["max_tokens"], "top_k": top_k, **retrieval_params,
                           "judge_model": llm["model"],
                           "judge_max_tokens": llm["judge_max_tokens"], "questions": len(questions),
                           "shadow_usd_per_mtok_in": llm["shadow_usd_per_mtok_in"],
                           "shadow_usd_per_mtok_out": llm["shadow_usd_per_mtok_out"]})
        mlflow.set_tags({"git_commit": commit, "eval_set": eval_set,
                         "prompt_hash": prompt_hash, "judge_prompt_hash": judge_hash, **index_tag})
        mlflow.log_metrics(metrics)
        mlflow.log_dict(results(questions, answers, judged, found), "results.json")
    kind = (f"rag top_k {top_k}" if top_k else "plain")
    found = (f", hit rate {metrics['hit_rate']:.3f}, MRR {metrics['mrr']:.3f}" if top_k else "")
    index = f", index {index_tag['index_version']}" if top_k else ""
    return (f"run {run.info.run_id[:8]}: {kind}, {len(questions)} questions, "
            f"correct {metrics['answer_correct']:.3f}{found}, "
            f"tokens {metrics['tokens_in']} in / {metrics['tokens_out']} out, p50 {metrics['latency_p50_s']:.1f} s, "
            f"p95 {metrics['latency_p95_s']:.1f} s, shadow cost ${metrics['shadow_cost_usd']:.4f} "
            f"(prompt {prompt_hash}, judge {judge_hash}{index}, questions {eval_set})")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.answer")
    parser.add_argument("command", choices=["eval"])
    parser.add_argument("--top-k", type=int, default=0,
                        help="retrieve this many passages per question and answer with prompts/rag.md (group rag); "
                             "default 0, the plain prompt")
    args = parser.parse_args(argv)
    if args.top_k < 0:
        parser.error("--top-k must be 0 or more")
    try:
        print(run(args.top_k))
    except (ValueError, RuntimeError, OSError) as err:
        sys.exit(f"error: {err}")


if __name__ == "__main__":
    main()

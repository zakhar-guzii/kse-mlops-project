"""Lab 3 retrieval index: corpus checks, section-bounded chunking, the index build (docs/design.md, 5.2 and 6.1).

Run as `python -m landcover.retrieval index` (make retrieval-index) or `python -m landcover.retrieval eval
[--top-k N]` (make retrieval-eval, docs/design.md 5.4); the embedding model needs the group rag.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import tomllib
from pathlib import Path

import numpy as np
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "retrieval.toml"
MANIFEST = ROOT / "corpus" / "manifest.toml"
QUESTIONS = ROOT / "eval" / "questions.toml"
CONFIG_KEYS = ("chunk_size", "chunk_overlap", "embedding_model", "embedding_revision", "top_k")
INDEX_FORMAT = "1"  # raise when the chunking or the passage:/query: text given to the model changes

HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$")
FENCE = re.compile(r"^[ \t]*(```|~~~)")
CHECK_QUESTION = "What does the value 255 mean in the output mask?"


def load_config(path=CONFIG):
    """The five retrieval settings; there are no defaults, so a missing key stops the build."""
    config = tomllib.loads(Path(path).read_text())
    missing = [key for key in CONFIG_KEYS if key not in config]
    if missing:
        raise ValueError(f"{path} lacks {', '.join(missing)}")
    if not 0 <= config["chunk_overlap"] < config["chunk_size"]:
        raise ValueError(f"{path}: chunk_overlap {config['chunk_overlap']} must be at least 0 and below "
                         f"chunk_size {config['chunk_size']}")
    if config["top_k"] < 1:
        raise ValueError(f"{path}: top_k {config['top_k']} must be at least 1")
    return {key: config[key] for key in CONFIG_KEYS}


def load_manifest(path=MANIFEST):
    return tomllib.loads(Path(path).read_text())["documents"]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def doc_version(text):
    """First 12 hex digits of the SHA-256 of the indexed text: same content, same version."""
    return sha256(text.encode())[:12]


def extract_sections(text, numbers):
    """Each `## <number> ` section up to the next `## ` heading, joined in the order given."""
    parts = []
    for number in numbers:
        match = re.search(rf"^## {re.escape(number)} .*?(?=^## |\Z)", text, flags=re.MULTILINE | re.DOTALL)
        if not match:
            raise ValueError(f"docs/design.md has no Section {number}")
        parts.append(match.group(0).strip())
    return "\n\n".join(parts) + "\n"


def documents(manifest, root=ROOT):
    """(doc_id, title, text) for every manifest entry; a copy that does not hash to its entry stops the build."""
    docs = []
    for entry in manifest:
        data = (root / entry["file"]).read_bytes()
        if "sections" in entry:
            text = extract_sections(data.decode(), entry["sections"])
        else:
            if sha256(data) != entry["sha256"]:
                raise ValueError(f"{entry['doc_id']}: {entry['file']} does not match its SHA-256 in the manifest")
            text = data.decode()
        docs.append((entry["doc_id"], entry["title"], text))
    return docs


def split_sections(text, title):
    """(locator, body) per Markdown section; headings inside fenced blocks are text, empty bodies are dropped."""
    sections, lines, fenced = [], [], False
    path = [(0, title)]  # (heading level, heading text); text before the first heading takes the title

    def flush():
        body = "\n".join(lines).strip()
        if body:
            sections.append((" > ".join(name for _, name in path), body))
        lines.clear()

    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        heading = None if fenced else HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            path = [(lv, name) for lv, name in path if 0 < lv < level] + [(level, heading.group(2))]
        else:
            lines.append(line)
    flush()
    return sections


def chunk(text, size, overlap):
    """Windows of at most `size` characters; consecutive windows share `overlap` characters.

    A window ends at the last line break in its final third, else at the last whitespace, else at `size`.
    """
    chunks, start = [], 0
    while start + size < len(text):
        end = start + size
        cut = text.rfind("\n", start + size * 2 // 3, end)
        if cut == -1:
            cut = max(text.rfind(" ", start, end), text.rfind("\t", start, end))
        if cut > start + overlap:
            end = cut
        chunks.append(text[start:end])
        start = end - overlap
    chunks.append(text[start:])
    return chunks


def chunk_documents(docs, size, overlap):
    """Chunk rows with doc_id, doc_version, locator, ordinal (position in the document) and text."""
    rows = []
    for doc_id, title, text in docs:
        version = doc_version(text)
        ordinal = 0
        for locator, body in split_sections(text, title):
            for piece in chunk(body, size, overlap):
                rows.append({"chunk_id": f"{doc_id}:{ordinal}", "doc_id": doc_id, "doc_version": version,
                             "locator": locator, "ordinal": ordinal, "text": piece})
                ordinal += 1
    return rows


def index_version(config, versions):
    """First 12 hex digits of the SHA-256 over the build format, the settings that shape the index and the documents'
    versions."""
    key = [INDEX_FORMAT, config["chunk_size"], config["chunk_overlap"], config["embedding_model"], config["embedding_revision"],
           sorted(versions.items())]
    return sha256(json.dumps(key).encode())[:12]


def vector(values):
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def build_index(dsn, docs, config, embed):
    """Replace the schema retrieval in one transaction, ending with the self-check; any failure keeps the old index.

    `embed` maps a list of texts to a list of vectors. Returns the index_meta row and the best check result.
    """
    rows = chunk_documents(docs, config["chunk_size"], config["chunk_overlap"])
    vectors = embed([f"passage: {r['locator']}\n{r['text']}" for r in rows])
    query = embed([f"query: {CHECK_QUESTION}"])[0]
    meta = {
        "index_version": index_version(config, {doc_id: doc_version(text) for doc_id, _, text in docs}),
        "embedding_model": config["embedding_model"],
        "embedding_revision": config["embedding_revision"],
        "chunk_size": config["chunk_size"],
        "chunk_overlap": config["chunk_overlap"],
        "documents": len(docs),
        "chunks": len(rows),
    }
    with psycopg.connect(dsn) as conn:  # commits on success, rolls back on any exception
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute("DROP SCHEMA IF EXISTS retrieval CASCADE")
        conn.execute("CREATE SCHEMA retrieval")
        conn.execute(f"""
            CREATE TABLE retrieval.chunks (
                chunk_id text PRIMARY KEY,
                doc_id text NOT NULL,
                doc_version text NOT NULL,
                locator text NOT NULL,
                ordinal integer NOT NULL,
                text text NOT NULL,
                embedding vector({len(query)}) NOT NULL
            )""")
        conn.execute("""
            CREATE TABLE retrieval.index_meta (
                index_version text NOT NULL,
                built_at timestamptz NOT NULL DEFAULT now(),
                embedding_model text NOT NULL,
                embedding_revision text NOT NULL,
                chunk_size integer NOT NULL,
                chunk_overlap integer NOT NULL,
                documents integer NOT NULL,
                chunks integer NOT NULL
            )""")
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO retrieval.chunks VALUES (%s, %s, %s, %s, %s, %s, %s::vector)",
                [(r["chunk_id"], r["doc_id"], r["doc_version"], r["locator"], r["ordinal"], r["text"], vector(v))
                 for r, v in zip(rows, vectors, strict=True)],
            )
        conn.execute(
            "INSERT INTO retrieval.index_meta (index_version, embedding_model, embedding_revision, chunk_size,"
            " chunk_overlap, documents, chunks) VALUES (%(index_version)s, %(embedding_model)s,"
            " %(embedding_revision)s, %(chunk_size)s, %(chunk_overlap)s, %(documents)s, %(chunks)s)",
            meta,
        )
        best = _check(conn, query, config["top_k"])
    return meta, best


def _search(conn, query, k):
    """The k chunks nearest to an embedded query: an exact scan, ties broken by chunk_id."""
    return conn.cursor(row_factory=dict_row).execute(
        "SELECT chunk_id, doc_id, doc_version, locator, text, embedding <=> %s::vector AS distance"
        " FROM retrieval.chunks ORDER BY distance, chunk_id LIMIT %s",
        (vector(query), k),
    ).fetchall()


def retrieve(conn, question, k, embed):
    """The k chunks nearest to a question, nearest first (docs/design.md 6.8)."""
    return _search(conn, embed([f"query: {question}"])[0], k)


def _check(conn, query, top_k):
    """Fail unless a chunk of export-contract Section 5.1 is among the top_k nearest by cosine distance."""
    found = _search(conn, query, top_k)
    if not any(r["doc_id"] == "export-contract" and r["locator"].startswith("5.1") for r in found):
        listed = "; ".join(f"{r['doc_id']}, {r['locator']}, {r['distance']:.3f}" for r in found)
        raise RuntimeError(f'check "{CHECK_QUESTION}" found no chunk of export-contract Section 5.1 '
                           f"in the top {top_k}: {listed}")
    return found[0]


def check_index(conn, config, docs):
    """Fail unless the index in the database was built from these documents and settings."""
    expected = index_version(config, {doc_id: doc_version(text) for doc_id, _, text in docs})
    try:
        row = conn.execute("SELECT index_version FROM retrieval.index_meta").fetchone()
    except psycopg.errors.UndefinedTable:  # no index was ever built in this database
        row = None
    if row is None or row[0] != expected:
        raise RuntimeError(f"the index is {row[0] if row else 'missing'}, the committed corpus and configuration "
                           f"give {expected}; run make retrieval-index")
    return expected


def load_questions(path=QUESTIONS):
    """The evaluation set and its identifier, the first 12 hex digits of the SHA-256 of the file."""
    data = Path(path).read_bytes()
    return tomllib.loads(data.decode())["questions"], sha256(data)[:12]


def _flat(text):
    return " ".join(text.split())


def relevant(row, sources):
    """A chunk of a cited section that holds that source's evidence quote, whitespace runs ignored."""
    return any(row["doc_id"] == s["doc_id"] and row["locator"] == s["locator"]
               and _flat(s["evidence"]) in _flat(row["text"]) for s in sources)


def evaluate(questions, retrieved, k):
    """Hit rate and MRR at k, with one record per question; `retrieved` holds each question's ranked rows."""
    records = []
    for q, rows in zip(questions, retrieved, strict=True):
        rows = rows[:k]
        rank = next((i for i, row in enumerate(rows, 1) if relevant(row, q["sources"])), None)
        records.append({"id": q["id"], "rank": rank, "retrieved": [
            {key: row[key] for key in ("chunk_id", "doc_id", "locator", "distance")} for row in rows]})
    n = len(records)
    return {"hit_rate": sum(r["rank"] is not None for r in records) / n,
            "mrr": sum(1 / r["rank"] for r in records if r["rank"]) / n,
            "results": records}


def embedder(config):
    """The configured model at its pinned revision, on the CPU, with normalised output."""
    from sentence_transformers import SentenceTransformer  # group rag

    model = SentenceTransformer(config["embedding_model"], revision=config["embedding_revision"], device="cpu")
    return lambda texts: model.encode(texts, batch_size=32, normalize_embeddings=True).tolist()


def run_eval(top_k):
    """Evaluate the set at top_k against the current index and log one MLflow run; returns the printed line."""
    import mlflow

    from landcover.train import clean_head

    commit = clean_head()
    config = load_config()
    questions, eval_set = load_questions()
    retrieved, seconds = [], []
    with psycopg.connect(os.environ["WAREHOUSE_DSN"]) as conn:
        version = check_index(conn, config, documents(load_manifest()))
        embed = embedder(config)
        for q in questions:
            start = time.perf_counter()
            retrieved.append(retrieve(conn, q["question"], top_k, embed))
            seconds.append(time.perf_counter() - start)
    result = evaluate(questions, retrieved, top_k)
    p50, p95 = np.percentile(seconds, [50, 95])
    mlflow.set_experiment("landcover-retrieval")
    with mlflow.start_run(run_name=f"retrieval-k{top_k}") as run:
        mlflow.log_params({"top_k": top_k, **{key: config[key] for key in CONFIG_KEYS if key != "top_k"},
                           "questions": len(questions)})
        mlflow.set_tags({"git_commit": commit, "index_version": version, "eval_set": eval_set})
        mlflow.log_metrics({"hit_rate": result["hit_rate"], "mrr": result["mrr"], "retrieval_s": sum(seconds),
                            "latency_p50_s": float(p50), "latency_p95_s": float(p95)})
        mlflow.log_dict(result["results"], "results.json")
    return (f"run {run.info.run_id[:8]}: top_k {top_k}, {len(questions)} questions, hit rate "
            f"{result['hit_rate']:.3f}, MRR {result['mrr']:.3f}, p50 {p50:.3f} s, p95 {p95:.3f} s (index {version}, questions {eval_set})")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m landcover.retrieval")
    parser.add_argument("command", choices=["index", "eval"])
    parser.add_argument("--top-k", type=int, help="eval only; default: top_k of retrieval.toml")
    args = parser.parse_args(argv)
    if args.top_k is not None and args.top_k < 1:
        parser.error("--top-k must be 1 or more")
    try:
        config = load_config()
        if args.command == "eval":
            print(run_eval(config["top_k"] if args.top_k is None else args.top_k))
            return
        docs = documents(load_manifest())  # checks the copies before the model loads or the database is touched
        meta, best = build_index(os.environ["WAREHOUSE_DSN"], docs, config, embedder(config))
    except (ValueError, RuntimeError) as err:
        sys.exit(f"error: {err}")
    print(f"index {meta['index_version']}: {meta['documents']} documents, {meta['chunks']} chunks "
          f"({meta['embedding_model']}, {meta['chunk_size']}/{meta['chunk_overlap']})")
    print(f'check "{CHECK_QUESTION}" -> {best["doc_id"]}, {best["locator"]}, distance {best["distance"]:.3f}')


if __name__ == "__main__":
    main()

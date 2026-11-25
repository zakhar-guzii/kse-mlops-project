import hashlib
import itertools
import os
import re
import uuid

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from landcover import retrieval

SECTION = " ".join(f"word{i}" for i in range(400)) + "\nlast line of the section"


def test_chunks_respect_size_overlap_and_cover_the_section():
    chunks = retrieval.chunk(SECTION, 300, 50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    for a, b in itertools.pairwise(chunks):
        assert a[-50:] == b[:50]
    # Every character of the section lies in some chunk, in order.
    rebuilt = chunks[0] + "".join(c[50:] for c in chunks[1:])
    assert rebuilt == SECTION


def test_a_window_ends_at_a_line_break_in_its_last_third():
    text = "a" * 250 + "\n" + "b" * 200
    assert retrieval.chunk(text, 300, 50)[0] == "a" * 250


def test_a_short_section_is_one_chunk():
    assert retrieval.chunk("short", 300, 50) == ["short"]


def test_sections_get_separate_chunks_and_heading_paths():
    text = "intro\n# Paper\n## 1 One\nfirst\n### 1.1 Sub\nsecond\n## 2 Two\nthird\n"
    sections = retrieval.split_sections(text, "Title")
    assert sections == [
        ("Title", "intro"),
        ("Paper > 1 One", "first"),
        ("Paper > 1 One > 1.1 Sub", "second"),
        ("Paper > 2 Two", "third"),
    ]
    rows = retrieval.chunk_documents([("d", "Title", text)], 1200, 200)
    assert [r["locator"] for r in rows] == [s[0] for s in sections]
    assert [r["ordinal"] for r in rows] == [0, 1, 2, 3]
    assert len({r["doc_version"] for r in rows}) == 1


def test_a_heading_inside_a_fenced_block_is_not_a_section():
    text = "## Config\n```yaml\n# not a heading\nkey: 1\n```\n"
    assert retrieval.split_sections(text, "T") == [("Config", "```yaml\n# not a heading\nkey: 1\n```")]


def test_doc_version_follows_content():
    assert retrieval.doc_version("a") == retrieval.doc_version("a")
    assert retrieval.doc_version("a") != retrieval.doc_version("b")
    assert len(retrieval.doc_version("a")) == 12


def test_config_has_every_setting():
    assert set(retrieval.load_config()) == set(retrieval.CONFIG_KEYS)


def test_every_copy_hashes_to_its_manifest_entry():
    manifest = retrieval.load_manifest()
    assert [e["doc_id"] for e in manifest] == [
        "oem-paper", "flair-hub", "naip-dictionary", "qgis-raster", "export-contract"]
    for entry in manifest:
        if "sha256" in entry:
            data = (retrieval.ROOT / entry["file"]).read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["doc_id"]


def test_export_contract_is_read_from_the_design_document():
    docs = {d: t for d, _, t in retrieval.documents(retrieval.load_manifest())}
    contract = docs["export-contract"]
    assert contract.startswith("## 5.1 Problem statement")
    assert "\n## 6.8 Integration points" in contract
    assert "## 5.2" not in contract and "## 6.9" not in contract
    rows = retrieval.chunk_documents([("export-contract", "", contract)], 1200, 200)
    assert any(r["locator"] == "5.1 Problem statement" and "| 255 | 0 |" in r["text"] for r in rows)


def test_a_missing_design_section_is_named():
    with pytest.raises(ValueError, match="no Section 9.9"):
        retrieval.extract_sections("## 5.1 Problem statement\ntext\n", ["5.1", "9.9"])


def test_an_edited_copy_stops_the_build(tmp_path):
    (tmp_path / "copy.md").write_text("edited\n")
    manifest = [{"doc_id": "x", "title": "X", "file": "copy.md", "sha256": "0" * 64}]
    with pytest.raises(ValueError, match="^x: copy.md does not match"):
        retrieval.documents(manifest, root=tmp_path)


@pytest.fixture
def index_dsn():
    """A fresh database of a random name, without the vector extension, on the server TEST_DSN names; dropped after."""
    server = os.environ.get("TEST_DSN")
    if not server:
        pytest.skip("TEST_DSN is not set")
    name = f"retrieval_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {name}")
    yield make_conninfo(server, dbname=name)
    with psycopg.connect(server, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE {name} WITH (FORCE)")


def test_the_guard_names_the_build_command_before_the_first_index(index_dsn):
    with psycopg.connect(index_dsn) as conn, pytest.raises(RuntimeError, match="missing.*run make retrieval-index"):
        retrieval.check_index(conn, retrieval.load_config(), retrieval.documents(retrieval.load_manifest()))


def stub_embed(texts):
    """The question and the chunks of Section 5.1 share one vector; every other chunk points elsewhere."""
    near = ("query: ", "passage: 5.1 Problem statement\n")
    return [[1.0, 0.0, 0.0] if t.startswith(near) else [0.0, 1.0, 0.0] for t in texts]


def wrong_embed(texts):
    """The question lands on every chunk except those of Section 5.1, so the self-check fails."""
    return [[0.0, 1.0, 0.0] if t.startswith("query: ") else v for t, v in zip(texts, stub_embed(texts), strict=True)]


def test_rebuilding_gives_the_same_index_and_a_failed_build_keeps_it(index_dsn):
    config = retrieval.load_config()
    docs = retrieval.documents(retrieval.load_manifest())
    first, best = retrieval.build_index(index_dsn, docs, config, stub_embed)
    assert (best["doc_id"], best["locator"]) == ("export-contract", "5.1 Problem statement")
    second, _ = retrieval.build_index(index_dsn, docs, config, stub_embed)
    assert first == second and first["documents"] == 5

    def meta():
        with psycopg.connect(index_dsn) as conn:
            return conn.execute(
                "SELECT index_version, documents, chunks, (SELECT count(*) FROM retrieval.chunks)"
                " FROM retrieval.index_meta").fetchall()

    assert meta() == [(first["index_version"], 5, first["chunks"], first["chunks"])]
    with pytest.raises(RuntimeError, match="no chunk of export-contract Section 5.1"):
        retrieval.build_index(index_dsn, docs, {**config, "chunk_size": 900}, wrong_embed)
    assert meta() == [(first["index_version"], 5, first["chunks"], first["chunks"])]


def test_retrieve_ranks_chunks_and_the_guard_names_a_stale_index(index_dsn):
    config = retrieval.load_config()
    docs = retrieval.documents(retrieval.load_manifest())
    retrieval.build_index(index_dsn, docs, config, stub_embed)
    with psycopg.connect(index_dsn) as conn:
        ten = retrieval.retrieve(conn, "any question", 10, stub_embed)
        assert len(ten) == 10
        assert all(set(r) == {"chunk_id", "doc_id", "doc_version", "locator", "text", "distance"} for r in ten)
        assert [r["distance"] for r in ten] == sorted(r["distance"] for r in ten)
        assert retrieval.retrieve(conn, "any question", 3, stub_embed) == ten[:3]
        assert retrieval.check_index(conn, config, docs)
        with pytest.raises(RuntimeError, match="run make retrieval-index"):
            retrieval.check_index(conn, {**config, "chunk_size": config["chunk_size"] + 1}, docs)


def row(doc_id, locator, text="", chunk_id="c"):
    return {"chunk_id": chunk_id, "doc_id": doc_id, "locator": locator, "text": text, "distance": 0.5}


QUOTE = {"doc_id": "d", "locator": "1 One", "evidence": "the quoted words"}
HIT, MISS = row("d", "1 One", "before the quoted words after"), row("d", "1 One", "another passage")


def test_relevance_needs_the_section_and_the_quote():
    assert retrieval.relevant(HIT, [QUOTE])
    assert not retrieval.relevant(MISS, [QUOTE])
    assert not retrieval.relevant({**HIT, "doc_id": "other"}, [QUOTE])
    assert retrieval.relevant(row("d", "1 One", "the quoted\n  words"), [QUOTE])


def ranked(*ranks):
    """Ten rows per question with its relevant row at the given rank, or none for None."""
    return [[HIT if i == rank else MISS for i in range(1, 11)] for rank in ranks]


def questions(*names):
    return [{"id": n, "question": n, "sources": [QUOTE]} for n in names]


def test_hit_rate_and_mrr_at_5():
    result = retrieval.evaluate(questions("a", "b", "c"), ranked(1, 3, None), 5)
    assert round(result["hit_rate"], 3) == 0.667 and round(result["mrr"], 3) == 0.444
    assert [r["rank"] for r in result["results"]] == [1, 3, None]
    assert all(len(r["retrieved"]) == 5 for r in result["results"])


def test_a_relevant_chunk_beyond_k_is_a_miss():
    result = retrieval.evaluate(questions("a"), ranked(4), 3)
    assert result["hit_rate"] == 0 and result["mrr"] == 0 and result["results"][0]["rank"] is None


# The evaluation set (eval/questions.toml): labels resolve against the corpus and questions do not quote it.

NAMES = {"oem-paper": ["OpenEarthMap", "OEM"], "flair-hub": ["FLAIR"],
         "naip-dictionary": ["NAIP", "National Agriculture Imagery Program"], "qgis-raster": ["QGIS"]}


def corpus_chunks():
    config = retrieval.load_config()
    docs = retrieval.documents(retrieval.load_manifest())
    return retrieval.chunk_documents(docs, config["chunk_size"], config["chunk_overlap"])


def label_problems(questions, chunks):
    """Each source's section exists and one of its chunks holds the quote; names the question otherwise."""
    problems = []
    for q in questions:
        for s in q["sources"]:
            section = [c for c in chunks if (c["doc_id"], c["locator"]) == (s["doc_id"], s["locator"])]
            if not section:
                problems.append(f"{q['id']}: no section {s['doc_id']} / {s['locator']}")
            elif not any(retrieval.relevant(c, [s]) for c in section):
                problems.append(f"{q['id']}: no chunk of {s['locator']} holds {s['evidence']!r}")
    return problems


def words(text):
    return re.findall(r"\w+", text.lower())


def paraphrase_problems(questions, chunks):
    """A question names a document it points at, or shares four consecutive words with a relevant chunk."""
    problems = []
    for q in questions:
        for doc_id in {s["doc_id"] for s in q["sources"]}:
            for name in NAMES.get(doc_id, []):
                if re.search(rf"\b{re.escape(name)}\b", q["question"], flags=re.IGNORECASE):
                    problems.append(f"{q['id']}: names {name}")
        asked = words(q["question"])
        grams = {tuple(asked[i:i + 4]) for i in range(len(asked) - 3)}
        for c in chunks:
            if retrieval.relevant(c, q["sources"]):
                said = words(c["text"])
                shared = grams & {tuple(said[i:i + 4]) for i in range(len(said) - 3)}
                if shared:
                    problems.append(f"{q['id']}: shares {' '.join(min(shared))!r} with {c['chunk_id']}")
    return problems


def test_the_set_is_complete():
    questions, eval_set = retrieval.load_questions()
    assert len(questions) >= 30 and len(eval_set) == 12
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids))
    assert [q["id"] for q in questions if not q.get("answer", "").strip() or not q.get("sources")] == []
    for entry in retrieval.load_manifest():
        cited = sum(any(s["doc_id"] == entry["doc_id"] for s in q["sources"]) for q in questions)
        assert cited >= 3, f"{entry['doc_id']} is a source of {cited} questions"


def test_every_source_resolves_against_the_corpus():
    assert label_problems(retrieval.load_questions()[0], corpus_chunks()) == []


def test_questions_do_not_quote_their_sources():
    assert paraphrase_problems(retrieval.load_questions()[0], corpus_chunks()) == []


def test_reference_answers_are_one_sentence():
    """The judge compares with the reference, so it holds the direct answer only (answer-evaluation spec)."""
    long = [q["id"] for q in retrieval.load_questions()[0]
            if ";" in q["answer"] or re.search(r"[.!?]\s", q["answer"].strip())]
    assert long == []


def test_index_version_ignores_top_k_only():
    config = retrieval.load_config()
    versions = {"a": "1"}
    base = retrieval.index_version(config, versions)
    assert retrieval.index_version({**config, "top_k": 99}, versions) == base
    for key, value in [("chunk_size", 1), ("chunk_overlap", 1), ("embedding_model", "m"), ("embedding_revision", "r")]:
        assert retrieval.index_version({**config, key: value}, versions) != base
    assert retrieval.index_version(config, {"a": "2"}) != base


def test_index_version_follows_the_build_format(monkeypatch):
    config, versions = retrieval.load_config(), {"a": "1"}
    base = retrieval.index_version(config, versions)
    monkeypatch.setattr(retrieval, "INDEX_FORMAT", retrieval.INDEX_FORMAT + "-next")
    assert retrieval.index_version(config, versions) != base


@pytest.mark.parametrize(("key", "value"), [("chunk_overlap", 600), ("chunk_overlap", -1), ("top_k", 0)])
def test_a_setting_out_of_bounds_is_refused(tmp_path, key, value):
    scratch = tmp_path / "retrieval.toml"
    text = retrieval.CONFIG.read_text()
    assert re.search(r"^chunk_size = 600$", text, flags=re.MULTILINE)
    scratch.write_text(re.sub(rf"^{key} = .*$", f"{key} = {value}", text, count=1, flags=re.MULTILINE))
    with pytest.raises(ValueError, match=key):
        retrieval.load_config(scratch)


def test_a_top_k_of_zero_is_a_usage_error():
    with pytest.raises(SystemExit) as stop:
        retrieval.main(["eval", "--top-k", "0"])
    assert stop.value.code == 2


def test_readme_states_the_document_count_of_the_manifest():
    readme = (retrieval.ROOT / "README.md").read_text()
    stated = re.search(r"The corpus has (\d+) documents", readme)
    assert stated and int(stated.group(1)) == len(retrieval.load_manifest())


def test_readme_states_the_question_count_of_the_set():
    readme = (retrieval.ROOT / "README.md").read_text()
    stated = re.search(r"\[eval/questions.toml\]\(eval/questions.toml\) has (\d+) questions", readme)
    assert stated and int(stated.group(1)) == len(retrieval.load_questions()[0])

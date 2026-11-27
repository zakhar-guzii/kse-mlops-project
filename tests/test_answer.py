import json
import re
import tomllib

import pytest

from landcover import answer, retrieval

PLACEHOLDERS = {"plain.md": ["question"], "rag.md": ["passages", "question"],
                "judge.md": ["question", "reference", "answer"]}


# Prompts

def test_prompt_hash_follows_the_file(tmp_path):
    copy = tmp_path / "plain.md"
    copy.write_bytes((answer.PROMPTS / "plain.md").read_bytes())
    text, first = answer.read_prompt(copy)
    assert re.fullmatch(r"[0-9a-f]{12}", first)
    assert answer.read_prompt(answer.PROMPTS / "plain.md")[1] == first
    copy.write_text(text.replace("English", "Englisch", 1))
    assert answer.read_prompt(copy)[1] != first


@pytest.mark.parametrize("name", PLACEHOLDERS)
def test_each_prompt_has_its_placeholders(name):
    text, _ = answer.read_prompt(answer.PROMPTS / name)
    for key in PLACEHOLDERS[name]:
        assert f"{{{key}}}" in text, f"prompts/{name} lacks {{{key}}}"


def test_filling_a_missing_placeholder_raises():
    plain, _ = answer.read_prompt(answer.PROMPTS / "plain.md")
    with pytest.raises(ValueError, match=r"no placeholder \{reference\}"):
        answer.fill(plain, question="q", reference="r")
    assert answer.fill("a {x} {y} {}", x="1", y="{x}") == "a 1 {x} {}"


def test_a_filled_value_that_looks_like_a_placeholder_is_kept():
    judge, _ = answer.read_prompt(answer.PROMPTS / "judge.md")
    text = answer.fill(judge, question="Is {answer} a placeholder?", reference="R {question}", answer="A")
    assert "Question: Is {answer} a placeholder?" in text and "Reference answer: R {question}" in text


# Passages and citations

ROWS = [{"chunk_id": f"c{i}", "doc_id": doc, "locator": loc, "text": text, "distance": 0.1 * i}
        for i, (doc, loc, text) in enumerate([("oem-paper", "2.2 Data > Classes", "Bareland is class 1.\n"),
                                              ("export-contract", "5.1 Classes", "Bareland is 0."),
                                              ("qgis-docs", "Raster > Styling", "Use a paletted renderer.")], 1)]


def test_three_rows_render_as_numbered_passages_in_order():
    assert answer.passages(ROWS) == ("[1] oem-paper, 2.2 Data > Classes\nBareland is class 1.\n\n"
                                     "[2] export-contract, 5.1 Classes\nBareland is 0.\n\n"
                                     "[3] qgis-docs, Raster > Styling\nUse a paletted renderer.")


def test_passages_can_be_numbered_from_a_later_start():
    assert answer.passages(ROWS[:2], start=11) == ("[11] oem-paper, 2.2 Data > Classes\nBareland is class 1.\n\n"
                                                   "[12] export-contract, 5.1 Classes\nBareland is 0.")


@pytest.mark.parametrize(("text", "numbers"), [("It is 0.\nSources: [2], [4]", [2, 4]),
                                               ("I do not know.\nSources: none", []),
                                               ("It is 0 [7].\nSources: [7], [3]", [7, 3]),
                                               ("It is 0.\nSources: [3, 9], [2]", [3, 9, 2]),
                                               ("Version [1.2] of the page.\nSources: none", [])])
def test_cited_reads_each_passage_number_once(text, numbers):
    assert answer.cited(text) == numbers


# Configuration

def test_llm_table_has_every_key_and_a_missing_one_is_named(tmp_path):
    assert set(answer.load_llm()) == set(answer.LLM_KEYS)
    scratch = tmp_path / "retrieval.toml"
    scratch.write_text(retrieval.CONFIG.read_text().replace("judge_max_tokens = ", "# judge_max_tokens = "))
    with pytest.raises(ValueError, match="lacks llm.judge_max_tokens$"):
        answer.load_llm(scratch)


def test_the_llm_table_leaves_the_retrieval_settings_alone(tmp_path):
    scratch = tmp_path / "retrieval.toml"
    scratch.write_text(retrieval.CONFIG.read_text().split("[llm]")[0])
    assert "llm" not in tomllib.loads(scratch.read_text())
    assert retrieval.load_config(scratch) == retrieval.load_config()


# Answering, judging and the metrics, with a fake model

LLM = {"model": "m", "shadow_usd_per_mtok_in": 2.0, "shadow_usd_per_mtok_out": 10.0}
QUESTIONS = [{"id": f"q{i:02d}", "question": f"question {i}", "answer": f"reference {i}"} for i in range(1, 33)]
TEMPLATE = "Q: {question}"
JUDGE = "Q: {question} R: {reference} A: {answer}"


def record(text="", prompt=0, completion=0, cached=0, seconds=0.0):
    return {"text": text, "finish_reason": "stop", "prompt_tokens": prompt, "completion_tokens": completion,
            "cached_tokens": cached, "seconds": seconds}


def test_only_the_first_answer_call_is_cold():
    calls = []

    def ask(text, **extra):
        calls.append((text, extra))
        return record(text)

    answers = answer.answer_all(QUESTIONS[:3], ask, TEMPLATE)
    assert [a["text"] for a in answers] == ["Q: question 1", "Q: question 2", "Q: question 3"]
    assert [extra for _, extra in calls] == [{"cache_prompt": False}, {}, {}]


def judge_ask(verdicts):
    """The judge returns the verdict listed for the question in its prompt, with 50 tokens in and 5 out."""
    def ask(text, **extra):
        assert extra == {"response_format": answer.JUDGE_FORMAT}
        number = int(re.search(r"question (\d+)", text).group(1))
        return record(json.dumps({"reason": "r", "verdict": verdicts[number - 1]}), 50, 5)
    return ask


def test_eight_of_32_correct_and_judge_tokens_kept_apart():
    answers = [record("a", 1000, 100, cached=0 if i == 0 else 20, seconds=1.0) for i in range(32)]
    verdicts = ["correct"] * 8 + ["incorrect"] * 24
    judged = answer.judge_all(QUESTIONS, answers, judge_ask(verdicts), JUDGE)
    metrics = answer.summarise(answers, judged, LLM)
    assert f"{metrics['answer_correct']:.3f}" == "0.250"
    assert (metrics["tokens_in"], metrics["tokens_out"]) == (32_000, 3_200)
    assert (metrics["judge_tokens_in"], metrics["judge_tokens_out"]) == (1_600, 160)
    assert metrics["shadow_cost_usd"] == pytest.approx((32_000 * 2 + 3_200 * 10) / 1e6)
    assert metrics["cold_calls"] == 1 and metrics["compute_s"] == 32.0
    rows = answer.results(QUESTIONS, answers, judged)
    assert rows[0]["id"] == "q01" and rows[0]["verdict"] == "correct" and rows[8]["verdict"] == "incorrect"


def test_shadow_cost_of_a_million_tokens_in_and_100k_out():
    metrics = answer.summarise([record(prompt=1_000_000, completion=100_000, seconds=1.0)],
                               [{**record(), "verdict": "correct"}], LLM)
    assert f"{metrics['shadow_cost_usd']:.2f}" == "3.00"


def test_latency_percentiles_interpolate_linearly():
    answers = [record(seconds=float(s)) for s in range(1, 11)]  # 1..10 seconds
    metrics = answer.summarise(answers, [{**record(), "verdict": "incorrect"}] * 10, LLM)
    assert metrics["latency_p50_s"] == pytest.approx(5.5)
    assert metrics["latency_p95_s"] == pytest.approx(9.55)
    assert metrics["cold_calls"] == 10


def test_unknown_cache_telemetry_logs_no_cold_calls():
    answers = [record(cached=None, seconds=1.0), record(cached=5, seconds=1.0)]
    metrics = answer.summarise(answers, [{**record(), "verdict": "correct"}] * 2, LLM)
    assert "cold_calls" not in metrics


# The retrieval-augmented path, with a fake search

RAG = "P:\n{passages}\nQ: {question}"


def fake_search(question):
    """Three rows per question; question n has its relevant chunk at rank n % 4 (0 means a miss)."""
    n = int(question.split()[-1])
    return [{**row, "chunk_id": f"{n}-{i}", "doc_id": "d", "locator": "s",
             "text": f"evidence {n}" if i == n % 4 else "other"} for i, row in enumerate(ROWS, 1)]


SOURCED = [{**q, "sources": [{"doc_id": "d", "locator": "s", "evidence": f"evidence {i}"}]}
           for i, q in enumerate(QUESTIONS, 1)]


def test_each_prompt_holds_its_passages_before_its_question():
    calls = []

    def ask(text, **extra):
        calls.append(extra)
        return record(text)

    answers = answer.answer_all(QUESTIONS[:3], ask, RAG, fake_search)
    first = answers[0]
    assert first["text"] == "P:\n" + answer.passages(fake_search("question 1")) + "\nQ: question 1"
    assert first["rows"] == fake_search("question 1") and first["retrieval_s"] >= 0
    assert calls == [{"cache_prompt": False}, {}, {}]
    assert "retrieval_s" not in answer.answer_all(QUESTIONS[:1], ask, TEMPLATE)[0]


def rag_answers(text="It is x.\nSources: none", **times):
    return [{**record(text, 100, 10, **times), "rows": fake_search(q["question"]), "retrieval_s": 0.5}
            for q in SOURCED]


def found(answers, k):
    return retrieval.evaluate(SOURCED, [a["rows"] for a in answers], k)


def test_latency_adds_retrieval_to_the_answer_call():
    answers = rag_answers(seconds=2.0)
    metrics = answer.summarise(answers, [{**record(), "verdict": "correct"}] * 32, LLM, found(answers, 3), 3)
    assert metrics["latency_p50_s"] == pytest.approx(2.5)
    assert metrics["retrieval_s"] == pytest.approx(16.0) and metrics["compute_s"] == pytest.approx(64.0)


def test_hit_rate_and_mrr_equal_the_retrieval_evaluation():
    answers = rag_answers()
    metrics = answer.summarise(answers, [{**record(), "verdict": "correct"}] * 32, LLM, found(answers, 3), 3)
    expected = retrieval.evaluate(SOURCED, [fake_search(q["question"]) for q in SOURCED], 3)
    assert (metrics["hit_rate"], metrics["mrr"]) == (expected["hit_rate"], expected["mrr"]) == (0.75, 11 / 24)
    rows = answer.results(SOURCED, answers, [{**record(), "verdict": "correct", "reason": ""}] * 32, found(answers, 3))
    assert [r["rank"] for r in rows] == [r["rank"] for r in expected["results"]]
    assert rows[0]["retrieved"] == ["1-1", "1-2", "1-3"] and rows[0]["retrieval_s"] == 0.5


def test_a_number_above_k_is_recorded_and_not_counted():
    answers = rag_answers()
    answers[0]["text"], answers[1]["text"] = "It is 0.\nSources: [2]", "It is 0.\nSources: [7]"
    judged = [{**record(), "verdict": "correct", "reason": ""}] * 32
    assert answer.summarise(answers, judged, LLM, found(answers, 5), 5)["cited_answers"] == 1
    rows = answer.results(SOURCED, answers, judged, found(answers, 5))
    assert [r["cited"] for r in rows[:3]] == [[2], [7], []]


def test_a_plain_run_logs_no_retrieval_metrics():
    answers = [record(seconds=1.0)] * 2
    judged = [{**record(), "verdict": "correct", "reason": ""}] * 2
    assert not {"hit_rate", "mrr", "retrieval_s", "cited_answers"} & set(answer.summarise(answers, judged, LLM))
    assert "rank" not in answer.results(QUESTIONS[:2], answers, judged)[0]


@pytest.mark.parametrize("text", ['{"reason": "r", "verdict": "partly"}', "correct", "[]"])
def test_an_unreadable_verdict_names_the_question(text):
    with pytest.raises(ValueError, match="^q02: the judge returned no verdict"):
        answer.judge_all(QUESTIONS[:2], [record("a")] * 2,
                         lambda prompt, **extra: record(text if "question 2" in prompt else
                                                        '{"reason": "r", "verdict": "correct"}'), JUDGE)


# The checks of the judge (eval/judge-check*.toml, docs/design.md 5.4)

CHECKS = [("judge-check.toml", "Lab 3: LLM baseline"), ("judge-check-rag.toml", "Lab 3: retrieval-augmented answers")]


def check_matches_readme(path, section, readme):
    """The rows label exactly the questions of the set, once each, and the README section's judge table has the
    file's counts."""
    rows = tomllib.loads(path.read_text())["answers"]
    ids = [r["id"] for r in rows]
    assert sorted(ids) == sorted(q["id"] for q in retrieval.load_questions()[0]), f"eval/{path.name}"
    assert all(r["judge"] in answer.VERDICTS and r["label"] in answer.VERDICTS for r in rows)
    body = re.search(rf"^## {re.escape(section)}\n(.*?)(?=^## |\Z)", readme, flags=re.MULTILINE | re.DOTALL)
    assert body, f"README has no section {section}"
    for verdict in answer.VERDICTS:
        match = re.search(rf"^\| Judge `{verdict}` \| (\d+) \| (\d+) \|$", body.group(1), flags=re.MULTILINE)
        assert match, f"README section {section} has no judge table row for {verdict}"
        counts = [sum(r["judge"] == verdict and r["label"] == label for r in rows) for label in answer.VERDICTS]
        assert [int(n) for n in match.groups()] == counts, f"{section}: {verdict}"


@pytest.mark.parametrize(("name", "section"), CHECKS)
def test_judge_check_covers_the_set_and_matches_the_readme(name, section):
    check_matches_readme(retrieval.ROOT / "eval" / name, section, (retrieval.ROOT / "README.md").read_text())


def test_a_label_for_no_question_fails(tmp_path):
    source = retrieval.ROOT / "eval" / "judge-check.toml"
    scratch = tmp_path / "judge-check.toml"
    scratch.write_text(source.read_text() + '\n[[answers]]\nid = "q99"\nanswer = "a"\njudge = "correct"\n'
                       'label = "correct"\n')
    with pytest.raises(AssertionError):
        check_matches_readme(scratch, CHECKS[0][1], (retrieval.ROOT / "README.md").read_text())


def test_a_changed_count_in_either_judge_table_fails():
    readme = (retrieval.ROOT / "README.md").read_text()
    for name, section in CHECKS:
        path = retrieval.ROOT / "eval" / name
        head, rest = readme.split(f"## {section}\n", 1)
        changed = head + f"## {section}\n" + re.sub(r"(\| Judge `correct` \| )(\d+)",
                                                     lambda m: m.group(1) + str(int(m.group(2)) + 1), rest, count=1)
        with pytest.raises(AssertionError):
            check_matches_readme(path, section, changed)

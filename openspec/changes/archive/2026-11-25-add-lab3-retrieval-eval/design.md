# Design

## Context

See [proposal.md](proposal.md) for motivation, scope and the decisions settled with the author. Section numbers without a file name refer to `docs/design.md`.

Facts checked for this design on 2026-11-24:

- With the committed configuration (600/100) the corpus gives 575 chunks in 102 sections: `flair-hub` 290 chunks in 25 sections (the largest section has 74), `oem-paper` 152 in 25 (largest 30), `qgis-raster` 97 in 31 (largest 8), `naip-dictionary` 21 in 19 (largest 2), `export-contract` 15 in 2 (Section 5.1 has 4, Section 6.8 has 11).
- `src/landcover/retrieval.py` has no public query function. Its private `_check` runs `ORDER BY embedding <=> $1::vector, chunk_id LIMIT k`, an exact scan with a deterministic tie-break, so the first three results of a search with k = 10 are the results of a search with k = 3.
- `landcover.train.identity` refuses a working tree with uncommitted changes before it returns the commit; `landcover.train.git` is the helper it uses. Training runs go to the MLflow experiment `landcover`. The `Makefile` exports `MLFLOW_TRACKING_URI` and `WAREHOUSE_DSN` for host commands.
- `mlflow` is a main dependency; `sentence-transformers` is in the group `rag`, which CI does not install. CI gives the tests a PostgreSQL server with pgvector through `TEST_DSN`.
- A read-only probe of the live index with 12 hand-written paraphrased questions, whose expected sources were not checked against the text, gave hit rate 0.58, 0.67, 0.75 and 0.75 at k = 1, 3, 5 and 10. Both questions aimed at `naip-dictionary` missed the first 20 results. A question about the code of bare soil returned `oem-paper` first, where bareland is class 1; the export uses 0, which only `export-contract` states.
- The README states index version `56be0057b30e` with 575 chunks; Section 5.1 states the first build's `25fcac866b12` with 572.
- Section 6.8 already gives the contract of `retrieve`: question text in, passages with `doc_id`, `doc_version` and section locator out.

## Goals / Non-Goals

**Goals:**

- One command that a reviewer reruns and that gives the same two numbers for the same commit and index.
- A question set whose labels a test can check without a model: a wrong section or an invented quote fails CI.
- The evaluation calls the same `retrieve` that the Lab 4 service will call.
- No new file besides the question set: the code goes into the existing module and the existing test file.

**Non-Goals:**

- A script that generates questions, a judge, an answer path, a prompt file.
- A sweep runner, a list of sweep values in a file, several values of k in one run.
- A second index, an approximate index, a rebuild inside the evaluation.
- Statistical tests or confidence intervals on 32 questions.

## Decisions

### 1. The question set is one TOML file

`eval/questions.toml`, read with the standard library like the manifest and the configuration:

```toml
[[questions]]
id = "q01"
question = "..."
answer = "..."

[[questions.sources]]
doc_id = "export-contract"
locator = "5.1 Problem statement"
evidence = "<verbatim quote from that section>"
```

A question has one source in most cases. A second source is added only when another section gives the same reference answer; a section that discusses the topic and gives a different answer is not a source. The bare-soil case in Context is the reason: `oem-paper` defines bareland and gives the wrong code for this system.

The identifier of the set, `eval_set`, is the first 12 hexadecimal digits of the SHA-256 of the file, the same form as `doc_version`.

Alternatives considered: JSON Lines is the usual format of evaluation sets, but the repository already reads two TOML files with `tomllib`, and TOML takes comments and long strings that the author has to read. A column for the language is not added; the set has one language.

### 2. How the questions are written

Claude drafts the set while this change is applied; the author reads it. For each question:

1. Read the section in the corpus copy (or Section 5.1 or 6.8 of the design document).
2. Write a question that a GIS user could ask about the export package, the input imagery or its display. Ask for the thing by its properties: no dataset or product name of the document it points at, no heading text, no sentence of the passage.
3. Write the reference answer in one or two English sentences that the passage supports.
4. Copy the evidence quote from the passage: the shortest span that holds the answer, at most 100 characters.
5. Take the locator from the output of `split_sections`, not by typing the heading path.

Questions per document: `export-contract` 6, `qgis-raster` 8, `oem-paper` 8, `flair-hub` 6, `naip-dictionary` 4, 32 in total. Every question has an answer in the corpus.

The author then reads each row against its section and confirms it or reports defects. The drafting model is not the embedding model and not the text model that will answer in the next change, which avoids a set written by the system under test. The README names the model that drafted the set.

Alternatives considered: writing the set by hand is several hours over 248 KB of text, half of it one paper, and the lab allows generation that is declared and read. A committed generator script that calls the local text model would produce the set with the model that later answers it, would need that server running, and is code kept for an artifact made once; the corpus copies of the previous change were made the same way, by hand and reviewed.

### 3. A relevant chunk holds the evidence quote

A retrieved chunk is relevant to a question when its `doc_id` and locator equal those of a source and its text contains that source's evidence. Both texts are compared after runs of whitespace are replaced by one space, so a line break inside a quote does not matter.

A section label alone would count any of the 74 chunks of the largest FLAIR-HUB section, or any of the 11 chunks of Section 6.8, as a hit. A chunk number would be exact and would break on the first change of chunk size. The quote is exact and belongs to the text, not to the chunking.

A quote no longer than the overlap normally lies whole in at least one chunk. This is not relied on: a test chunks the corpus with the committed configuration and fails for a source whose quote no chunk of its section contains. If a later change tries another chunk size, that test names the quotes to shorten.

The measure is conservative. A chunk that states the same fact in other words elsewhere is a miss until the author adds it as a source.

### 4. `retrieve` and one search statement

`retrieve(conn, question, k, embed)` embeds `query: <question>` and returns the k nearest chunks as rows with `chunk_id`, `doc_id`, `doc_version`, `locator`, `text` and `distance`. The SQL statement moves from `_check` into one search helper that both use, so the self-check of the build tests the statement that serves.

The evaluation calls `retrieve` once per question, as the service will. Embedding 32 questions one at a time takes well under a second on the CPU, so a batch path would be a second code path for no gain.

### 5. Metrics are pure functions

`evaluate(questions, search, k)` takes the questions and a function from question text to ranked rows, and returns the two metrics with one record per question: the question's `id`, the rank of the first relevant chunk or none, and the retrieved `chunk_id`, `doc_id`, `locator` and `distance`. The definitions are those of the specification. The function needs no database and no model, so the tests give it a fake search with known ranks.

### 6. The command and its two guards

`python -m landcover.retrieval eval [--top-k N]`, run by `make retrieval-eval` with the group `rag`; `TOP_K=<n>` passes `--top-k`. Without it, the command uses `top_k` of `retrieval.toml`. Before it embeds anything it stops when:

- `git status --porcelain` is not empty. The run's `git_commit` then names the code and the question file exactly. This is the rule of `landcover.train`, and its `git` helper is reused; it and `mlflow` are imported inside the command, so `make retrieval-index` loads neither.
- the `index_version` in `retrieval.index_meta` differs from the one computed from the committed corpus and configuration. The message says to run `make retrieval-index`. Without this guard a changed chunk size in the file would be logged as a parameter of an index that was built with the old one.

The command prints one line, for example:

```
run 1a2b3c4d: top_k 5, 32 questions, hit rate 0.781, MRR 0.612 (index 56be0057b30e, questions 9f8e7d6c5b4a)
```

### 7. What a run holds

| Kind | Content |
|---|---|
| Experiment | `landcover-retrieval`, so the runs do not sit among segmentation runs with other metric columns |
| Run name | `retrieval-k<top_k>` |
| Parameters | `top_k`, `chunk_size`, `chunk_overlap`, `embedding_model`, `embedding_revision`, `questions` (the count) |
| Tags | `git_commit`, `index_version`, `eval_set` |
| Metrics | `hit_rate`, `mrr` |
| Artifact | `results.json`: the per-question records of Decision 5 |

The metric names do not contain k, so MLflow shows the three runs in one column with `top_k` beside it. The run has no `data_version` tag: it reads no training data, and `index_version` already covers every document version and every setting that shapes the index.

Alternative considered: putting `index_version` into the `data_version` tag would satisfy the existing tracking requirement unchanged, but that tag holds a DVC hash everywhere else, and `reproduce` reads it as one.

### 8. Three runs at 3, 5 and 10

The comparison is three invocations: `make retrieval-eval TOP_K=3`, `make retrieval-eval` and `make retrieval-eval TOP_K=10`. `retrieval.toml` keeps 5; the other two values exist only as arguments and in the results table. Each run stands alone and can be repeated by its own command.

Because the search is exact, the three runs are three cuts of one ranking, so the hit rate and the MRR cannot fall as k grows. The table therefore shows how much k buys and cannot choose k. The choice needs the answer metric and the latency of the next change, where a larger k also means more prompt tokens: about 450, 750 and 1,500 tokens of passages at 150 tokens per chunk. `top_k` in the configuration is not changed here.

k = 1 is not one of the values because there the hit rate equals the MRR and the row carries one number.

Alternative considered: one invocation that searches once with k = 10 and logs three runs. It saves two model loads and needs the list of values in the code or in a file, which the single-configuration requirement of the index forbids for top-k.

### 9. Tests

In `tests/test_retrieval.py`, with no model and no network:

- metrics: the two scenarios of the specification, through `evaluate` with a fake search;
- relevance: the right section without the quote is not relevant; the quote across a line break is;
- the set: at least 30 questions, unique identifiers, a reference answer on every question, at least three questions per document of the manifest, every source's section present in the chunked corpus, every quote contained in a chunk of its section;
- paraphrase: no question contains a name of a document it points at, and no question shares four consecutive words with a chunk relevant to it. The names are a small table in the test (`oem-paper`: OpenEarthMap, OEM; `flair-hub`: FLAIR; `naip-dictionary`: NAIP, National Agriculture Imagery Program; `qgis-raster`: QGIS). Words are compared in lower case without punctuation;
- `retrieve`, through `TEST_DSN` and skipped without it: on the stub index of the existing test it returns k rows with all fields in order of distance, the result for k = 3 is the start of the result for k = 10, and the index guard raises when the configuration's chunk size differs from the built one;
- README: the stated number of questions equals the number in the set.

The MLflow call is a few lines with no branch and is checked by the three real runs, not by a mock.

### 10. Documentation

`README.md` gains "Lab 3: retrieval evaluation" after the index section: the three commands, one printed line, the table (top-k, hit rate, MRR, run ID) with the index version, `eval_set` and commit, the number of questions and their split by document, the definition of a hit, the sentence that Claude drafted the questions and the author read them, the document with the most misses at k = 5, and the statement that the table cannot choose k. No scorecard row is added: the row "LLM component evaluated" also asks for an answer metric.

`docs/design.md`:

- **4**: the functional requirement on the GIS assistant says that questions and answers are in English.
- **5.2**: in the Lab 3 paragraph, the sentences on the questions and on hit@k and MRR become present tense and name `eval/questions.toml`, `make retrieval-eval` and Section 7.2. The comparison of answer correctness with the plain-prompt baseline, the prompts, cost and latency stay planned.
- **5.4**: a paragraph "Course experiment (Lab 3): retrieval" with the set, how it was produced, the relevant-chunk rule, the two metrics, the three values, and the limit that one question is 3.1 points of hit rate.
- **6.1**: the sentence under "Lab 3 retrieval pipeline" and the labels of the question and retrieve boxes say that `retrieve` is built and is driven by the evaluation set; the LLM and answer boxes stay marked as the next change.
- **7.2**: a subsection "Lab 3 retrieval results" with the same table as the README.

Sections 5.1 and 6.8 are not edited. They are the document `export-contract`, so an edit would change the index version under the runs and could break an evidence quote. `docs/design.uk.md` gets the same passages.

### 11. Review fixes

After the review of the finished Lab 3 branch:

- **Evaluation on explicit rows.** `evaluate(questions, retrieved, k)` takes the ranked rows of each question instead of a search function. `run_eval` retrieves, timing each search, and passes the rows; the answer path scores the rows its answers were given with the same function, once, instead of feeding them back through a fake search.
- **Seconds of a retrieval run.** A run also logs `retrieval_s`, the seconds of the 32 searches including the embedding of each question, and `latency_p50_s` and `latency_p95_s` per question. Loading the model is not counted.
- **The commit.** `clean_head()` in `train.py` checks that the tree is clean and returns `HEAD` in one place; `run_eval` reads it before any work and tags that value, so a commit made during a run cannot be recorded for it.
- **top-k.** `--top-k` must be 1 or more; an explicit 0 no longer falls back to the configured value silently.
- **Sources.** A question may cite a second passage that also states its answer. In the top-k 10 run, q23 retrieved the second half of its evidence sentence, which the chunking had split, so its evidence is shortened to the part one chunk holds whole; q25 gains the sentence and the table rows of Section IV-A that leave out codes 15 to 18, and q28 the two passages that state 19 classes, and its reference answer says 19 with 4 optional. q29 keeps the code it asks about: the dictionary lists CNIR, CLR and CIR, so a question that asks for the code of colour infrared imagery would have two answers. q25 and q26 say that they ask about the dataset's published experiment, not about this project's model, whose crosswalk and split differ.

## Risks / Trade-offs

- [Drafted questions may copy the wording of the passage they were written from] → The paraphrase test of Decision 9 and the author's reading. A hit rate of 1.0 at k = 3 would be a reason to reread the set, not a result.
- [A drafted label may be wrong: a section that does not answer, a quote that was not copied exactly] → The test resolves every section and quote against the corpus; the author reads every reference answer against its section.
- [32 questions are few: one question moves the hit rate by 3.1 points] → The README and Section 5.4 say so. The table reports what was measured and decides nothing by a difference of one or two questions.
- [Strict paraphrase can make questions about `naip-dictionary` hard to find, as in the probe] → That is a finding for the table. The README names the document with the most misses; this change does not tune the index.
- [The evaluation refuses a dirty tree, so results are pasted into the README after the runs] → The table gives each run's commit, as Section 7.2 does for Lab 2.
- [An edit of Section 5.1 or 6.8 after this change changes the index version and may break a quote] → The index guard stops the evaluation until the index is rebuilt, and the quote test names the broken source.
- [The requirement added to `retrieval-index` targets a capability that is not yet under `openspec/specs/`] → The first task checks that `add-lab3-retrieval-index` is archived and stops otherwise.

# Proposal

## Why

Lab 3 (step 4) requires the query path "question, retrieve top-k, prompt with the retrieved chunks, answer", with the prompt as a second versioned file. Step 5 requires one retrieval parameter varied across three values and tabled as "value, hit rate, MRR, answer metric" in the README and in Section 7.2, and steps 1, 6 and 7 require Sections 5.3, 5.4, 6.3, 6.7 and 7.1 revised from measured runs and the three Lab 3 scorecard rows. The repository has the index, the retrieval metrics and a plain-prompt baseline, but no answer has yet been produced from a retrieved passage, so the table has no answer column and `top_k` in the configuration is an unmeasured default.

This is the fourth and last of the consecutive Lab 3 changes. It joins the three earlier ones and prepares the hand-in.

## What Changes

- Add a third prompt file, `prompts/rag.md`, with numbered passages and the question. The model uses the passages first and names the passages that state its answer; when none does, it may answer from its own knowledge and says that no passage supports the answer.
- Extend `make answer-eval` with `TOP_K=<n>`: the command retrieves n passages per question through the existing `retrieve`, answers with `prompts/rag.md`, judges with the unchanged judge prompt and logs one run to the experiment `landcover-answers` with the index version, the retrieval settings, hit rate, MRR, the answer metric, tokens, shadow cost and latency. Without `TOP_K` the command stays the plain baseline.
- Run it at top-k 3, 5 and 10 and table the three runs beside the baseline row in the README and in Section 7.2.
- Repeat the check of the judge on the run at top-k 10, this time with labels written before any verdict of that run is seen.
- Choose `top_k` by a rule fixed before the runs and write the chosen value into `retrieval.toml`.
- State why the prompt cache reused one token per call in the baseline run, with the measurement that shows it.
- Revise Sections 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.7, 7.1, 7.2 and 7.4 of the design document, redraw Figure 7 with the retrieval edge built, add the evaluation-loop diagram of the lab's Appendix 3 as Figure 8, and add the three Lab 3 rows to the maturity scorecard.

Decisions settled with the author:

| Topic | Decision |
|---|---|
| Grounding | Permissive with disclosure: passages first, own knowledge allowed when no passage states the answer, and the answer then says so. The lab text does not restrict this (checked in `labs/lab-3.pdf`); Sections 5.1 and 6.8 of the design require a citation and "report that limitation", which the disclosure satisfies without editing them |
| Rule for top-k | The smallest of 3, 5 and 10 whose answer metric is no more than two questions (0.0625) below the best of the three. Fixed before the runs |
| Check of the judge | On the run at top-k 10, which has the most answers the judge should accept. Labels by Claude without sight of that run's verdicts, reviewed by the author; the threshold stays 29 of 32 and is passed before top-k is chosen |
| Retrieval metrics of an answer run | Computed in the same run from the passages it retrieved, so one run is one row of the table |
| Latency | End to end: retrieval plus the answer call. Retrieval seconds are logged apart |
| Command | `make answer-eval` stays plain; `make answer-eval TOP_K=<n>` is retrieval-augmented and needs the group `rag` |
| Baseline row | Not rerun: the installed server is the build of the baseline run, `b12359-b1b770d90`, and the question set, the plain prompt and the judge prompt are unchanged |
| Citations | The prompt numbers the passages and asks for the numbers used. The run records them; no citation metric is computed |
| Section 6.7 | The monthly totals stay. A paragraph adds the measured tokens and shadow cost per answer beside the 6,400 input tokens budgeted per call |
| Memory | Measured next to the Compose stack. The measurement next to Minikube that Section 6.2 promises moves to Lab 4 |
| Prompt cache | Investigated in this change |
| Archiving | Not in this change. The two unchecked boxes of the earlier Lab 3 changes are left as they are |

Defaults proposed here, for the author to confirm when reviewing this change:

| Topic | Default | Reason |
|---|---|---|
| `--swa-full` | Not added to `make llm-server`. The cause and the measured effect are documented, and the flag is named in Section 6.3 as the first latency lever for Lab 4 | It changes the server under the baseline row, which would then be rerun and relabelled, to save about 0.4 s of a 4.3 s call |
| Evaluation-loop diagram | Added as Figure 8 | Appendix 3 of the lab gives two diagrams to redraw; the earlier changes drew the first |
| Support count | The run logs how many answers cite a passage | It is the only evidence that the disclosure rule works, and costs one regular expression |
| `gis-assistant` | One sentence and one scenario added for an answer that no passage supports | The specification now says "answers from retrieved passages"; the prompt chosen here is the one Lab 4 serves |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `answer-evaluation`: seven added requirements: the retrieval-augmented prompt file, the retrieval-augmented run and its index lineage, the disclosure of support, end-to-end latency, the comparison across three values of top-k with the rule that chooses one, and the check of the judge on a retrieval-augmented run. This capability is introduced by `add-lab3-llm-baseline`, which is implemented but not archived; its requirements are not changed, so the delta only adds.
- `gis-assistant`: the requirement "Use the project retriever and prediction service" gains the case of a documentation question that no retrieved passage answers.

## Impact

- New files: `prompts/rag.md`, `eval/judge-check-rag.toml`, `docs/diagrams/lab3-evaluation-loop.svg`.
- Changed code: `src/landcover/answer.py` (the retrieval-augmented path and the `--top-k` argument), `tests/test_answer.py`, `Makefile` (target `answer-eval`), `retrieval.toml` (only `top_k`, and only if the rule chooses another value than 5).
- Changed documents: `README.md` (a section "Lab 3: retrieval-augmented answers", corrected sentences in the two earlier Lab 3 sections, the opening paragraph and three scorecard rows), `docs/design.md` (Sections 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.7, 7.1, 7.2 and 7.4), `docs/diagrams/lab3-retrieval.svg`, and the same passages of the local, ignored `docs/design.uk.md`. Sections 5.1 and 6.8 are not edited, so `export-contract` and the index version `56be0057b30e` do not change.
- Running stack: three runs in the MLflow experiment `landcover-answers`. The index is read, not rebuilt. The text model server runs with the command of `make llm-server`, unchanged.
- Dependencies: none added. A retrieval-augmented run uses the existing group `rag`; the plain run still needs no group.
- Out of scope: a second prompt variant or a comparison of grounding rules, a sweep over chunk size or the embedding model, any fix for a weak retrieval result, a citation-correctness metric, a second judge model, `--swa-full` in the server command, a rerun of the baseline, the Lab 4 text service, a measurement next to Minikube, Sections 5.1 and 6.8, archiving any Lab 3 change, and the `lab-3` tag, which the author sets.

# Tasks

Follow [design.md](design.md). Documentation only: no training, runtime code or resource provisioning. Saving the public AWS Pricing Calculator estimate is in scope.

## 1. Tighten the English design

- [x] 1.1 Rewrite the intro, §1 and §§2–4 under Decision 1 with the Decision 2 wording; verify one intro sentence, a five-sentence overview, three metric levels, seven NFR rows each with a number or assumption, and no "arbitrary size" or "any size".
- [x] 1.2 Revise §5.2: timeline before the checklist, shortened answers 1–2, the E1 wording and the NAIP scope (Decision 4); verify four checklist answers and that the freshness, re-upload, split and holdout rules each appear once.
- [x] 1.3 Revise §§5.3–5.5: random-forest definition and parameters, the RGB paragraph, weight links with the limitation (Decision 5), no teacher sentence, the support wording; verify the links resolve and that model activation is stated only in §5.5 and §6.4.
- [x] 1.4 Revise §§6.2–6.5: the Colab exchange matching the diagram (Decision 6), one MLflow/W&B sentence, the cloud placement with the recovery sentence (Decision 8), the LLM memory assumption, and §6.3 references to §2 and §4; verify that `bridge`, `IMDS` and `Airflow DAG` do not appear in §6.2.
- [x] 1.5 Revise §§6.6–6.9 and §7.1: the reference windows (Decision 3), no duplicate accuracy paragraph, the calculator status, the S5 timing, trimmed risks and alternatives with section references; verify each threshold has a window, reason and action, and §7.1 keeps at least two alternatives with decisions.

## 2. Update the diagrams

- [x] 2.1 Update `docs/diagrams/context.svg`: remove the template caption and add questions and cited answers to the GIS-user arrows; render it and verify the labels are readable and unclipped.
- [x] 2.2 Redraw `docs/diagrams/data-flow.svg` per Decision 7; render it at 800 and 900 px and verify both lanes, the training-only version point, both gate rules, the dashed manual import, readable labels and an updated `<desc>`.
- [x] 2.3 Update `docs/diagrams/deployment.svg` (D3 labels, legend, caption removed) and the §6.1 alt texts and captions; render it and verify the labels fit and the component names match §6.2.

## 3. README, verification log and translation

- [x] 3.1 Create `docs/verification.md` with the dated history and the superseded estimate, and rewrite README in the order of Decision 9; verify README has no dated history bullets, its overview equals §1, and its links resolve.
- [x] 3.2 Synchronize `docs/design.uk.md` with the final English text and apply the round-2 wording fixes; verify 22 headings and identical numbers, links and SVG references.
- [x] 3.3 Create and save the AWS Pricing Calculator estimate from the reviewed inputs, verify its public share link, and update the design, translation and README. Reconcile the saved totals with $301.75 / $338.25 and record the actual links, totals and any differences in `docs/verification.md`.

## 4. Verify the document set

- [x] 4.1 Check the Lab 1 structure in English and Ukrainian and review the text for repetition, clarity and useful content; word count is informational, without a fixed ceiling. Verify the round-2 contradictions are absent, local links resolve, `openspec validate refine-lab1-design --strict` and `make lint` pass, and `git diff --stat` touches only the intended files. Record the results in `docs/verification.md` with each round-2 item mapped to its closing text.

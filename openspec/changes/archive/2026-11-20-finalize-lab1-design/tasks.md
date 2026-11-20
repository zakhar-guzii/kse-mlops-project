# Tasks

Apply revises Lab 1 documentation. Verify the contracts below by reading the examples and diagrams. Runtime demonstrations are deliverables of their respective later labs.

## 1. Explain the GIS assistant

- [x] 1.1 Revise §§2, 4 and 6.8 of `docs/design.md` with the combined GeoTIFF/255 example and the two tool contracts. Walk through a documentation-only question and an asynchronous prediction, identifying the service called, caller, job state, actual model version, source citation and output.
- [x] 1.2 Align §§5.5 and 6.4–6.5 with the allowlist, four-attempt budget, redacted traces and original 24-hour expiry. Check pending, failed, expired, foreign-job, operator-only and budget-exhausted cases against the assistant spec. Confirm direct upload remains usable during an LLM outage.

## 2. Explain anomalies, drift and operator response

- [x] 2.1 Update §§4, 5.5 and 6.6 with the brightness example and the detector table. Read off the unit, reference, provisional threshold and action for invalid input, a dark valid image, input drift and same-model prediction drift. Check that insufficient samples produce an explicit status and a valid unusual image still contributes to the window.
- [x] 2.2 Replace the first-days-of-service reference with versioned training statistics and state the Lab 4 demonstration in §§6.6 and 6.9. Verify that requests flow through the endpoint, two eligible windows reach the dashboard, a crossing reaches the operator by email and only labelled controls support an IoU claim.

## 3. Connect Labs 2–5 without changing the project scope

- [x] 3.1 Update §§4, 5.2–5.4 and the ingestion contract in §6.8. Walk the same named interval twice, an expected-new scan with no additions and a deliberately invalid batch through the watermark and feature table. Check that the text distinguishes ingestion replay from OEM training replay, names the sampled-data retrieval/checksum and gives each tile a key and feature version.
- [x] 3.2 Add the majority rule before the CPU RF, retaining B4 as the neural candidate. Trace a valid bareland pixel, an ignored pixel and an overlapping tile through evaluation. Verify the named CPU model can be reproduced in the planned Lab 2 workflow from data version and Git SHA with a stated metric tolerance.
- [x] 3.3 Update the relevant handoffs in §§5–6 and write one sentence per lab in §7.4. Verify that Lab 3 and Lab 4 share retrieval configuration, Lab 4 loads the reported prediction version by alias, and Lab 5 reuses both tools and specifies the evaluation and trace evidence in the change design. Keep §§7.2–7.3 as placeholders.
- [x] 3.4 Align §§4, 6.2 and 6.7 on a zero-additional-spend reviewer path. Check that local CPU and text inference suffice for the course, existing Colab access is optional, and the saved calculator and workload assumptions describe only the hypothetical AWS scenario. Check that cloud call estimates do not imply a mandatory agent tool sequence.

## 4. Align diagrams and submission evidence

- [x] 4.1 Correct the data-flow SVG and §6.1 caption. Trace acceptance through queue and worker, retrieval and prediction to their actual services, and new labelled data through ingestion and the quality gate. Render the affected diagrams at README width and check legibility, seven layers, version point, divergence and agreement with §§6.2 and 6.8.
- [x] 4.2 Restore both Lab 1 maturity scorecard rows with reviewer evidence in `README.md`, fix its dangling final sentence and the clean-clone link to the ignored handout in the design. Verify the five-sentence overview, all 22 numbered headings and tracked local links. Identify the commit for any cited CI run.
- [x] 4.3 Walk the defense example from upload through QGIS export, cited answer, drift alert and operator decision using the final text and diagrams. Run `make lint`, `git diff --check` and strict OpenSpec validation. Verify later-lab metrics, traces, alerts and benchmarks are described as future evidence.

## Workflow follow-up

- At submission, verify the default-branch CI run for the actual final commit. Confirm which revision the instructor accepts before tagging it `lab-1`.

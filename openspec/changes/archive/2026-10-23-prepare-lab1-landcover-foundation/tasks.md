# Tasks

This implementation checklist covers **Lab 1 only**. Checkboxes record verified completion. Labs 2–5 runtime components are described in the design but are not built by this change; capability specifications are skipped through `skip_specs: true`.

## 1. Design document and Lab 1 coverage

- [x] 1.1 Create `docs/design.md` from sections 1–7.4 of the planning design: a 3–5 sentence overview, motivation, three levels of success metrics, all seven NFR categories, and scope/out-of-scope; verify exact numbering against the PDF, explicit assumptions, and the absence of fabricated benchmark results.
- [x] 1.2 Include the data checklist, time fields/freshness/replay policy, raw/clean/features formats, taxonomy mapping, training/serving features, OEM control-set independence, NAIP agreement, the Colab bundle, and promotion/rollback; check expected-new with old bytes, intentional replay, NAIP without masks, and a train+val teacher without claiming independence.
- [x] 1.3 Add three Mermaid diagrams and a consistent local/cloud component table; check syntax/rendering using an available tool and manually verify the seven layers, raw/derived version points, conditional raw gate, annotation+mask gate, training/serving divergence, Colab, and two application services. If no renderer is available, explicitly mark the rendering check as incomplete.
- [x] 1.4 Complete security/privacy, monitoring, upstream/downstream contracts, and a concrete corpus manifest plan with names/versions/links; verify 24h expiry for queued/running jobs, proposed 30-day log retention, ignore-vs-NoData, RGB-only serving, secrets outside Git, and the absence of fabricated snapshot hashes.
- [x] 1.5 Add at least two alternatives with pros/cons/rejection reasons, risk-to-mitigation mappings, placeholders 7.2/7.3, and one sentence for each of Labs 2–5; check the document against PDF pages 2–4 and coverage of the 20 questions in Appendix 2. Explicitly preserve the absence of full future-lab assignments and unresolved data/teacher gates; do not create separate study notes or research files.

## 2. Cloud estimate as a concrete delivery gate

- [x] 2.1 Reproduce the design's us-east-1/730h scenario in AWS Pricing Calculator with EKS, EC2, EBS, MWAA, managed MLflow, RDS jobs/index, S3, ECR, CloudWatch, networking, and SES; verify regional EC2/RDS/MLflow/NAT rates, justify NAT/endpoints/egress, and select dashboards/alarms. Completion evidence requires an estimate ID/URL, date, and inputs; do not create paid cloud resources. Use the interactive UI or the provider's published calculation engine, official regional assets and public estimate service; verify a saved estimate by fetching and recalculating it. If no verifiable provider estimate can be obtained, leave this task incomplete and report the concrete blocker.
- [x] 2.2 Update section 6.7 and corresponding cloud labels from the saved calculator estimate, recalculate the total, and distinguish verified rates, capacity assumptions, and excluded costs; include GPU model work and LLM/embedding costing proxies for the user-authorized full-cloud scenario, check double counting across managed MLflow/RDS/shared worker, and preserve the actual $0 budget. Do not describe the preliminary manually calculated $1109.94 as calculator output.

## 3. Pinned development environment and local commands

- [x] 3.1 Add `.python-version` with 3.12.13 and development dependencies Ruff 0.17.2/pre-commit 4.7.0 in `pyproject.toml`, and update `uv.lock`; verify `uv lock --check` and `uv sync --locked` using the selected Python. If these exact pins are incompatible/unavailable, document the reason and a verified minimal compatible pin without adding the ML/runtime stack.
- [x] 3.2 Create a `Makefile` with `setup` invoking `uv sync --locked` and `lint` invoking `uv run --locked ruff check .`; verify both commands and that lint does not automatically modify source. Do not create an artificial Python application just to provide lint inputs.
- [x] 3.3 Create `.pre-commit-config.yaml` with a local hook using the same locked Ruff and rules; verify `uv run --locked pre-commit validate-config` and `uv run --locked pre-commit run --all-files`. Do not automatically install global hooks or tooling outside the required environment.

## 4. README and lint CI

- [x] 4.1 Populate `README.md` with five sentences about the problem, setup/lint commands, a design link, and two initial maturity rows; verify the sentence count, local links, and truthful CI/clean-clone evidence without an unverified green status.
- [x] 4.2 Create `.github/workflows/lint.yml` for push and pull_request with pinned Python/uv and calls to `make setup` and `make lint`; verify workflow structure and consistency with local commands, without training/container/deploy/test jobs outside Lab 1 scope. Document uv/Python prerequisites in the README.

## 5. Integration verification before review

- [x] 5.1 Run the documented setup/lint and pre-commit commands in a clean temporary copy of the final tree, verify the locked environment and diagram/link readability; record actual results in README/design without presenting a copy of unpublished changes as a verified remote clean clone.
- [x] 5.2 Check the complete diff against the authorized file scope, the absence of datasets/checkpoints/secrets/runtime code, and consistency between the document and all three diagrams; run `git diff --check` and `openspec validate prepare-lab1-landcover-foundation --strict`. Review all incomplete delivery gates before claiming Lab 1 is ready.

## Workflow follow-up

- Commit/push only after a separate explicit instruction; verify green lint CI on the default branch itself.
- After publication, run `make setup` and `make lint` in a genuine clean clone of the submission commit and update evidence if needed.
- Create the `lab-1` tag and provide the repository link only after submission acceptance is satisfied.
- Archive the change after tracked tasks and review are complete; do not disguise an incomplete calculator/rendering gate as complete.
- Read the full Labs 2–5 assignments before their separate implementation changes.

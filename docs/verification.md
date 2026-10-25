# Verification log

Dated evidence for the Lab 1 repository, newest first. An entry proves only the state it names.

## 2026-10-25 — refine-lab1-design

Checked on 2026-10-25 (Europe/Kyiv): commit `586706d` plus the working changes for `refine-lab1-design`, including the local, ignored Ukrainian translation. This entry verifies the current documents, including fixes already present in that commit; it does not claim a new commit, CI run or clean clone.

The user confirmed that conciseness means clear, useful text without unnecessary repetition, not a 6,763-word ceiling. The proposed 100-image minimum for the input reference was dropped; the 14-day input reference, 7-day comparison windows and fewer-than-50-images rule remain.

Checks performed:

- Compared both designs with the Lab 1 PDF: 22 numbered sections in the required order, three metric levels, seven NFR categories, four data-checklist answers, three diagrams, alternatives, placeholders and four milestones.
- Checked relative Markdown targets in README, both designs, this log and the active change artifacts. The five-sentence README overview equals English §1. Both languages have matching links, SVG references, code blocks and numeric values after decimal and thousands-separator normalization.
- Inspected all three current SVGs at 800 and 900 px, rendered after their source files changed: readable labels, no clipping, separate training/upload lanes, a training-only version point, both validation rules, the dashed manual Colab import and complete managed-equivalent labels. SVG XML, titles and accessible descriptions pass.
- `UV_CACHE_DIR=/tmp/kse-mlops-commit-uv-cache UV_OFFLINE=true make lint`: passed. `openspec validate refine-lab1-design --strict`: passed (`skip_specs: true`; documentation only). `git diff --check`: passed.
- Repeated the document, link, heading-anchor, lint, strict OpenSpec and whitespace checks after inserting the final saved estimate. `git diff --stat` is limited to README, the English design, this log and the active OpenSpec planning files; the ignored Ukrainian translation was checked separately. Historical verification entries are unchanged from `586706d`.

The final prose pass removed repeated explanations in §§2, 5.2–5.3 and 5.5, and split dense infrastructure, performance and monitoring paragraphs by decision. Short summaries required by the overview, metrics, requirements, risks and alternatives remain, with section references. After the calculator insertion, `wc -w` reports 7,024 words in English (previously 7,116) and 6,836 in Ukrainian; the counts are context, not acceptance limits.

### Saved AWS Pricing Calculator estimate

The [saved AWS Pricing Calculator estimate](https://calculator.aws/#/estimate?id=5149b216245db885ab6f9aa1f752302f6d636b13) was verified on 2026-10-25 by reopening it in a fresh unauthenticated browser: US East (N. Virginia), USD, Linux On-Demand, with a 730-hour infrastructure month. All 16 entries are present: 14 in the base group and two EC2 entries in the training group. The saved page shows:

| Scenario | Calculator display | Design at listed rates | Difference |
|---|---:|---:|---:|
| Steady month | $299.48 | $301.75 | −$2.27 |
| Training increment | $36.17 | $36.50 | −$0.33 |
| Training month | $335.65 | $338.25 | −$2.60 |

Upfront cost is $0. The displayed annual $4,027.80 repeats a training month twelve times; the design budgets occasional training.

The displayed base reconciles to $301.751383333, or $301.75, by adding the omitted domain ($16/year = $1.333333333/month), $0.1275 for storing 5 GB of CloudWatch logs instead of the calculator's compressed 0.75 GB, the automatically waived Cognito ($0.30) and basic health-check ($0.50) fees, SNS's sub-cent charge ($0.00205), and $0.0085 of per-service display rounding.

The training increment reconciles to $36.495945205, or $36.50: $36.17 + $0.30 for 60 temporary IPv4 address-hours + $0.027945205 for continuous EBS prorating − $0.002 of display rounding. The EBS correction replaces the UI's 0.03/0.05 instance-month fractions with 20/730 and 40/730. Both groups therefore reconcile to $338.247328538, or $338.25.

The Sonnet 5.5 Global form needs integer hourly inputs, so its entered token proxy costs $124.8048 instead of the exact workload's $124.80; both display as $124.80. This $0.0048 representation difference is reported separately, not added again to the reconciliation. Conditional free-allowance totals remain separate because the calculator does not apply every allowance consistently.

The final saved link is also recorded in English §6.7, the Ukrainian translation and README. No AWS resources were provisioned.

### Round-2 closure map

| Items | Closing text or artifact |
|---|---|
| S1, E3 | [§6.6](design.md#66-monitoring-and-alarms): frozen input and model-dependent references, comparison windows, insufficient-data rule, thresholds and operator actions |
| S2, E13 | [§6.7](design.md#67-cost): verified public estimate and saved totals, reconciled above; the superseded estimate remains in the historical entry below |
| S3 | [§5.3](design.md#53-techniques): published initialization weights and limitations; [§6.2](design.md#62-infra) and [supporting Decision 8](../openspec/changes/refine-lab1-design/design.md#8-supporting-rationale-cloud-operations-moved-from-62): stale-attempt fencing and certificate recovery |
| S4 | [§1](design.md#1-overview), [§4](design.md#4-requirements-and-constraints) and [README](../README.md): different image sizes within explicit bounds |
| S5, E2 | [§6.5](design.md#65-data-privacy) and [§6.8](design.md#68-integration-points): `accepted_at` + 24 h, including queue and processing time; latency retains the §3 conditions |
| E1, E7, N1 | [§5.2](design.md#52-data): no reference masks for uploads; timeline before the four checklist answers; considered NAIP years, regions and monitoring-only role |
| E4–E6 | [§6.2](design.md#62-infra): memory fit is an assumption; introduction and [§1](design.md#1-overview): one opening sentence and a five-sentence overview, repeated in README |
| E8–E10 | [§5.3](design.md#53-techniques): baseline before parameters, 8-bit RGB rule, concise model alternatives without the generic comparison paragraph |
| E11–E12, E14 | [§6.2](design.md#62-infra): one MLflow/W&B sentence and concise topology; network and lease details in supporting Decision 8; [§7.1](design.md#71-alternatives): short trade-offs and section references |
| D1–D2 | [Data-flow SVG](diagrams/data-flow.svg): training-only versioning and freshness, upload checks, operator-started Colab run and manual import |
| D3 | [Deployment SVG](diagrams/deployment.svg) and [§6.1](design.md#61-high-level-design): RDS/OpenSearch and CloudWatch/Model Monitor equivalents, legend, alt texts and captions |
| R1–R4 | [README](../README.md): overview, repository map, setup, two scorecard rows and concise submission status; dated historical evidence is preserved below |

The alternative-weight links resolve without downloading weights: the Satlas file page is public, and GeoSeg's public Drive folder lists `stseg_base.pth` (463.3 MB). The official [GeoSeg README](https://raw.githubusercontent.com/WangLibo1995/GeoSeg/main/README.md) names that folder for pretrained backbones, and [`FTUNetFormer.py`](https://raw.githubusercontent.com/WangLibo1995/GeoSeg/main/geoseg/models/FTUNetFormer.py) uses `pretrain_weights/stseg_base.pth` by default. These are initialization weights, not OEM-8 checkpoints.

`openspec instructions apply --change refine-lab1-design --json` reports 12/12 tasks complete (`all_done`). The change remains unarchived.

No runtime, model training, deployment, paid calls, current CI or submission-clone checks were run. Apart from the calculator inputs and the alternative-weight links above, the design's external sources were not refreshed.

## 2026-10-24 — rewrite-lab1-design

The rewritten design passed document checks: 22 numbered sections in English and in the local Ukrainian translation, resolving local links, the three SVG diagrams rendered at document width in headless Chrome and inspected visually, independently recomputed cost tables, `openspec validate rewrite-lab1-design --strict` and `make lint`.

## 2026-10-23 — earlier design version

- The three Mermaid diagrams of the earlier design rendered and were checked visually, and local documentation links were checked. SVG files replaced the Mermaid diagrams on 2026-10-24.
- The saved [AWS Calculator estimate](https://calculator.aws/#/estimate?id=52dedcbc1a8747f5028990e050593d9dab6c4ac1), verified on 2026-10-23 (Europe/Kyiv), was $1,229.81/month and $0 upfront. It priced the superseded EKS, MWAA and legacy managed MLflow design, not the current one.

## 2026-10-22 — repository tooling

- A clean temporary copy passed `make setup`, `make lint`, pre-commit configuration validation and all-file execution, and `uv lock --check`, with Python 3.12.13, Ruff 0.17.2 and pre-commit 4.7.0. The checks modified no source files. This was a local copy, not a remote clone.
- A later genuine clone of published commit `934858b` passed the same checks. A temporary Python error made lint and pre-commit fail and an installed test hook block a commit; the corrected code passed. The test hook and probe commits existed only in the temporary clone; the working repository has no automatic hooks.

# Tasks

Implement this documentation change only after an explicit apply request. Follow [design.md](design.md), including its G + 1–35 coverage map. All checks below concern delivered documents/diagrams; no model training, runtime implementation or cloud deployment is required.

## 1. Rewrite the English problem, data and model design

- [ ] 1.1 Rewrite §§1–4 with separate GIS/operator roles, multi-user continuous service, success metrics and justified resource assumptions; verify the 3–5-sentence overview, three metric levels, seven required NFR categories and unchanged numbered structure against Lab 1.
- [ ] 1.2 Rewrite §§5.1–5.2 with OEM-8, the rejected building-only framing and its reason, the selected FLAIR timeline/crosswalk, development/final partitions, nullable dates, freshness/replay example, storage/versioning and retrieval corpus; verify the rejected framing, all four data-checklist answers and that regional labels are not claimed to cover all eight classes.
- [ ] 1.3 Rewrite §5.3 with the RF baseline, exact U-Net/EfficientNet-B4 initialization/preprocessing and linked FT-UNetFormer/Satlas comparison; verify supervised updates resume the full approved checkpoint, serving inputs are identified, and no teacher or extra-model training is required.
- [ ] 1.4 Rewrite §§5.4–5.5 with the numbered evaluation protocol, first neural approval requiring OEM-8 mIoU above RF on the same development control, selected 2 pp update policy, strict alternative, hypothetical examples and operator activation/rollback; check baseline-versus-initial and approved-versus-update comparisons, export/resource gates, examples, exactly-2-pp boundary, unchanged-regional-score failure, incomplete-class-coverage handling and isolation of both final holdouts.

## 2. Rewrite the service, governance and cost sections

- [ ] 2.1 Rewrite §§6.2–6.4 with the minimal local/managed/selected-cloud component table, Colab export/import, MLflow plus optional W&B, confirmed Gemma/Sonnet choices, ECS/EC2/RDS/EIP topology, resource budgets and authentication; verify capacity arithmetic, two application-service roles, actual worker rollout and user/operator permissions agree with the planning design.
- [ ] 2.2 Rewrite §§6.5–6.6, §§6.8–6.9 and §§7.1–7.4: 24-hour expiry, no feedback ingestion, concise monitoring/recipient rules, external owner contracts, concrete risks and required alternatives/placeholders/milestones; verify signed access and late outputs cannot extend expiry, temporary versions are covered, no publisher SLA is invented, and each monitoring threshold has a window/reason/action.
- [ ] 2.3 Rewrite §6.7 from the 24-hour inputs and prepare/reconcile replacement provider-calculator inputs; independently recompute 104/108 GB storage, main $301.75/$289.23 steady and $338.25/$325.73 active totals, and 2200-task sensitivity. Verify no duplicate infrastructure/token/egress accounting and direct dated rate sources. Record calculator publication accurately; save/link a replacement only if separately authorized after the concrete estimate is reviewable, otherwise mark that submission evidence pending.

## 3. Create and integrate the three SVG diagrams

- [ ] 3.1 Create `docs/diagrams/context.svg` with one system boundary, external owners, GIS consumer and operator/alert recipient; render and visually verify readable labels, payload arrows, distinct actors and unclipped SVG title/description content.
- [ ] 3.2 Create `docs/diagrams/data-flow.svg` with all seven layers, version point, quality gate, offline/online divergence, approved registry alias and monitoring loop; render and verify arrow visibility, correct supervised flow and separation of inference re-upload from training freshness.
- [ ] 3.3 Create `docs/diagrams/deployment.svg` in the appendix's simple placement style and replace the three Mermaid blocks in §6.1 with SVG references; render and verify legibility at normal document width, correct host/Minikube boundaries, managed equivalents and component-name agreement with §6.2.

## 4. Synchronize the translation and mirrored README content

- [ ] 4.1 Synchronize `docs/design.uk.md` from the completed English document, sharing the three SVGs and retaining the English-authoritative notice; verify all 22 numbered sections, decisions, tables, numbers, source links and localized captions match, and remove the leading `e`.
- [ ] 4.2 Align README's five-sentence overview, current design/diagram/estimate references and English/translation wording; verify valid historical setup/lint/CI evidence remains dated and the old calculator/Mermaid checks are not presented as verification of the new artifacts.
- [ ] 4.3 Check local links in both documents/README and add direct primary citations for consequential claims; verify the Lab link resolves to `../labs/lab-1.pdf` locally, the PDF/ignored translation availability is accurately described, and the tracked design does not depend solely on ignored research files. Preserve `.gitignore` and unrelated files.

## 5. Verify the integrated document set

- [ ] 5.1 Reconcile every G/1–35 review row with the delivered EN/UK text and SVGs; verify actor/taxonomy/split/promotion/retention/component/cost consistency, all structural Lab 1 checks, successful diagram embedding and absence of stale first-version teacher/single-user/on-demand claims.
- [ ] 5.2 Review the final scoped diff and explicit ignored-file contents, run whitespace/link checks and `openspec validate rewrite-lab1-design --strict`, and record the document-validation outcome; verify no runtime/dependency/config edits, downloads, paid actions or unapproved calculator publication entered this change.

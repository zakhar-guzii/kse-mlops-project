# Tasks

Follow [design.md](design.md). These tasks edit documentation only. Floci and AWS integration checks are described for later labs, not executed by this change. Capability specs are deliberately skipped with `skip_specs: true`.

## 1. Update the English design

- [x] 1.1 Revise the storage table in Section 5.2 and infrastructure table in Section 6.2 to select Floci for local S3; verify that both tables agree, DVC/MLflow/corpus storage remain consistent and no active storage choice still names pgsty/silo or MinIO.
- [x] 1.2 Add the concise Section 6.2 explanation following Decisions 1–3; verify that it covers standard S3 operations, environment-specific configuration, persistent disk storage and emulation limits in the existing plain English style, cites supporting official documentation and makes no claim of measured performance, complete AWS equivalence or a completed integration.
- [x] 1.3 Update Section 7.4 to place the S3, 128 MiB/multipart, signed URL, restart and DVC/MLflow checks in Lab 2, with Minikube reachability checked when introduced; verify that these checks are future work, full deployment stays in Lab 4 and Section 6.5's exact expiry and unversioned temporary-storage rules remain intact.

## 2. Align diagrams and reading aids

- [x] 2.1 Update the object-storage card and `<desc>` in `docs/diagrams/deployment.svg` for Floci and the DVC remote; render the SVG at 800 and 1000 px and verify readable, unclipped labels, correct Minikube/host/Colab boundaries and the existing managed-equivalent legend.
- [x] 2.2 Review `context.svg`, `data-flow.svg` and Section 6.1's alt text/captions against the revised design; correct only affected wording, render both remaining SVGs and verify that external actors, seven layers, PostgreSQL queue and manual Colab import still match the text.
- [x] 2.3 Review README and synchronize the affected passages of `docs/design.uk.md` if that local translation exists; verify that README retains accurate Lab 1 status and setup commands, translation numbers/links/decisions match English, its source disclaimer remains and `git check-ignore docs/design.uk.md` still confirms its ignored status. Do not create a missing translation.

## 3. Check the document set

- [x] 3.1 Read the revised passages and diagram text together; verify consistent terminology, no repeated Floci explanation, working local links and supporting source links, and no change to the selected cloud stack, costs, job queue, local identity/LLM, training exchange or privacy contract. Historical mentions in archived changes remain untouched.
- [x] 3.2 Run `openspec validate align-lab1-design-with-floci --strict` and `git diff --check`; verify both pass and review the changed-file list against the proposal's document-only scope, inspecting the ignored translation separately if edited. Do not add runtime code, dependencies, infrastructure manifests or generated preview files to the change.

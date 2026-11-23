# Tasks

Follow [design.md](design.md) and the specs under [specs/](specs/). Section numbers refer to `docs/design.md`. Do not ingest OpenEarthMap, score the 2022 batch, change the ingestion pipeline or its tables, add MLflow authentication, or create the `lab-2` tag.

Who runs what:

- Groups 1 to 6 are implementation. Their verification uses only short local check runs: the rule, the random forest, and a U-Net of one or two epochs on the Mac. These runs are not the recorded results and use no Colab compute.
- Group 7 records the author's saved runs and registers the trained models.
- Groups 8 and 9 continue after the author's runs exist.

Training refuses an uncommitted tree. Before a task that runs a training command, commit the work with the author's approval. The author does every push.

## 1. Tracking server in the stack

- [x] 1.1 Add `mlflow==3.16.1`, `scikit-learn` and `scikit-image` to the project dependencies and a dependency group `nn` with `torch`, `segmentation-models-pytorch==0.5.0` and `timm`, all pinned exactly, and refresh `uv.lock`; verify `make setup`, `make lint` and `make test` pass and that `uv sync --locked` installs no `torch`. If `mlflow` and `dvc` do not resolve together, apply the fallback in the design's risks and record it.
- [x] 1.2 Add `docker/mlflow/Dockerfile`, the `mlflow` service, the `landcover-mlflow` bucket in `create-bucket`, the `mlflow` database line in `sql/warehouse.sql` and the two client variables in the `Makefile`, as in design Decision 7; recreate the volume and reload the six batches as in the Migration Plan. Verify `curl -fs http://localhost:5001/health` succeeds after `make up`, the `mlflow` database holds MLflow's tables, both buckets exist, the port is bound to `127.0.0.1`, and both row-count tables of the README still read 16 per batch.
- [x] 1.3 Add the MLflow address and the volume note to the README stack section, and revise Section 6.2 (MLflow row, "Lab 2 stack" paragraph), Section 6.4 and the MLflow card and `<desc>` of `docs/diagrams/deployment.svg` as in design Decision 12; verify the README commands run as written, the diagram renders unclipped and no active document says the course MLflow has authentication.

## 2. Models and evaluation

- [x] 2.1 Add the batch roles next to the batch registry, and in `src/landcover/models.py` the tile loader and the evaluation of design Decision 5, with `tests/test_models.py`; verify the tests cover a hand-computed confusion matrix, ignored pixels, a prediction of an unscored class counted as a miss, and a scored class without pixels failing by name.
- [x] 2.2 Implement the majority-class rule and the random forest with its per-class pixel draw (design Decision 4); verify tests show the rule predicts the most frequent training class everywhere, the draw never exceeds the cap or includes an ignored pixel, and the same seed gives the same positions.
- [x] 2.3 Implement `python -m landcover.train` with the identity checks and the result directory of design Decisions 3 and 6, and ignore `runs/` in Git; verify a modified tracked file and a changed raw file each stop the run before any tile is read, that the rule and the forest complete with the stack stopped, that two forest runs report identical scores, that the hash in `run.json` equals the model file's, and that no file of `D073-2022` is opened.
- [x] 2.4 Implement the U-Net fit and prediction; verify with a two-epoch check run on the Mac that the result holds `model.pt`, two history entries and the device, and note the seconds per epoch for the hand-over. If MPS fails, apply the fallback in the design's risks.

## 3. Logging, registration and promotion

- [x] 3.1 Implement the model wrapper and the `log` step of design Decisions 6 and 8 and the `make train` and `make import` targets; verify check runs of the rule and the forest show parameters, scores, both lineage tags and a stored model, that a result with an altered model file creates no run, and that a recorded score changed by more than the bound is refused with both scores printed.
- [x] 3.2 Implement `make register` and `make champion`; verify the new version carries both tags equal to its run's, that it loads from the Mac through the server and returns a 512×512 mask of class IDs for one development tile, and that promoting a second version and then the first leaves exactly one `champion`.
- [x] 3.3 Add the training, import, registration and promotion commands to the README, and report the artifact upload and download check in the storage checks of Section 7.4; verify the commands run as written.

## 4. Reproduction

- [x] 4.1 Implement `make reproduce VERSION=<n>` as in design Decision 9; verify that reproducing a check version of the forest succeeds with both scores printed, that the new run has the `reproduces` tag, that `git status` and the current branch are unchanged afterwards and no worktree remains, and that tests show a difference above the tolerance and a mismatching data version each give a non-zero result.
- [x] 4.2 Add the reproduction command and the forest tolerance to the README; verify the documented command runs as written.

## 5. Remote training code

- [x] 5.1 Write `scripts/remote_train.py` and the `make train-remote` target (design Decision 10), with the launcher passing extra arguments on to the training command; verify without Colab that an unpushed commit stops `make train-remote` before any session command runs, and that the launcher, run on the Mac in a scratch directory against the local repository path with one epoch, clones, installs, fetches the data, trains and produces a zipped result that `make import` logs.
- [x] 5.2 Add the remote training command, its prerequisites (Colab client install and sign-in, a pushed commit) and the manual fallback to the README, and revise the "Training exchange" paragraph of Section 6.2 and the Colab row of Section 6.9; verify no active document mentions Google Drive or W&B as part of the course flow.

## 6. Documents that do not need results

- [x] 6.1 Revise Sections 5.3 and 5.4 and the Lab 2 milestone of Section 7.4 as in design Decision 12; verify every model input and every column of `features.tile_features` has a serving source or an explicit "none" with its reason, and that Section 5.3 no longer mentions `replay=true`.
- [x] 6.2 Update layers 4 and 5 of `docs/diagrams/data-flow.svg` and its alt text and caption in Section 6.1; render it and verify the labels are readable and unclipped, the MLflow server, its two stores, the model name and the alias appear, and layers 1 to 3 and 6 to 7 are unchanged.
- [x] 6.3 Add to the README the maturity scorecard with the two Lab 1 rows and the five Lab 2 rows, each pointing at its evidence, and the results section with its tables laid out and their cells empty; verify every link resolves.
- [x] 6.4 Clear the tracking server of check runs and check versions, then hand over to the author: the commands of group 7 in order, the measured seconds per epoch, and what was verified without Colab and what was not. Verify the server shows no run and no model version.

## 7. Recorded runs

- [x] 7.2 Record the three saved runs in MLflow and verify their parameters, scores and both tags. Per the author's decision to reuse the saved weights, the rule and forest use pushed commit `07c41af` and the Colab L4 U-Net uses pushed commit `c1f77a3`. The model and training code, lockfile and DVC data identifier match across both commits. The U-Net used the launcher in an allocated L4 session, then `colab download`, `colab stop` and `make import`. Verified that `colab sessions` lists no session.
- [x] 7.3 Register the forest and the U-Net and point `champion` at the version with the higher development score; verify two versions carry both tags and one carries the alias.
- [x] 7.4a Reproduce historical Random Forest version 1 on CPU. Original and reproduced mIoU were both 0.1478 to four decimals, with repeat run `77375bfa9d574a74884c68213713593c`.
- [x] 7.4b Reproduced historical U-Net version 2 twice on Colab L4 using its recorded encoder revision. Both repeats scored 0.3355 mIoU. The README records both run IDs.

## 8. Results into the documents

- [x] 8.1 Set the U-Net tolerance to the minimum of 0.02 after both L4 repeats matched the original. Verified the reproduction checks with the archive from the explicit Colab session.
- [x] 8.2 Recorded measured reproduction results in the README and Section 7.2 and captured the current Airflow quality-gate error in the orchestrator UI.
- [x] 8.3 If the local `docs/design.uk.md` exists, synchronise the passages changed in 1.3, 5.2, 6.1 and 6.2 and the Lab 2 results in Section 7.2; verify `git check-ignore docs/design.uk.md` still succeeds. Do not create the file if it is missing.

The documented scores, run IDs, class supports and registered versions were checked against MLflow.

## 9. Integration check

- [x] 9.1 Verified from a clean clone with fresh Compose volumes. A cold DVC pull restored 192 GeoTIFFs. The newly trained and registered forest reproduced at 0.1478 mIoU. Each 2019 run wrote 16 rows to both tables. The rejected batch left zero rows.
- [x] 9.2 Ran strict OpenSpec validation, lint, diff checks and all 35 tests with PostgreSQL 16.

## Workflow follow-up

- Archive `add-lab2-data-pipeline` if it is still open, then archive this change after review.
- The author creates the `lab-2` tag and pushes.

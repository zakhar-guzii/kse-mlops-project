# Spec Delta

## Purpose

Turns one batch of raw image–label files into checked warehouse rows and feature rows, in a way that can be rerun safely and that refuses a batch that fails its quality gate.

## ADDED Requirements

### Requirement: Batch selected by the run
A pipeline run SHALL process exactly one batch. The batch SHALL be the one named by the `batch_id` run parameter when it is given, and otherwise the batch registered for the year of the run's data interval start. The current time SHALL NOT influence which batch is processed.

#### Scenario: Run for a calendar year
- **WHEN** a run's data interval starts in 2019 and no `batch_id` is given
- **THEN** the run processes batch `D065-2019` and no other batch

#### Scenario: Run with a batch parameter
- **WHEN** a run is triggered with `batch_id` set to the demonstration batch
- **THEN** the run processes that batch regardless of the run's dates

#### Scenario: Year without a batch
- **WHEN** a run's data interval starts in a year with no registered batch and no `batch_id` is given
- **THEN** the run fails before reading any data file and the error names the year

#### Scenario: Unknown batch parameter
- **WHEN** a run is triggered with a `batch_id` that is not registered
- **THEN** the run fails before reading any data file and the error names the batch

### Requirement: Task graph
The pipeline SHALL run the tasks `extract`, `validate`, `transform`, `load`, `build_features` and `quality_check` in that order.

#### Scenario: Successful run
- **WHEN** a run processes a valid batch
- **THEN** all six tasks succeed in order and the run is marked successful

### Requirement: Structural validation
The pipeline SHALL reject the whole batch before loading when the batch has no files, or when any file is unreadable, any image is not 8-bit with at least three bands, any image lacks a label or any label lacks an image, an image and its label differ in grid size, or a label contains a class ID unknown to the source taxonomy. The error SHALL name the offending files.

#### Scenario: Grid mismatch
- **WHEN** one label's width or height differs from its image's
- **THEN** `validate` fails, names that pair, and no row of the batch is loaded

#### Scenario: Unknown class ID
- **WHEN** one label contains a class ID that the source taxonomy does not define
- **THEN** `validate` fails and names that label

#### Scenario: Empty batch
- **WHEN** the selected batch has no files
- **THEN** the run fails and loads nothing

### Requirement: Tile rows for a batch
After a successful `load`, the warehouse SHALL hold one row per image–label pair of the batch, with the batch ID, tile ID, acquisition year, grid size, pixel count per internal class after the label crosswalk, ignored-pixel count and mean value per colour channel.

#### Scenario: Row count matches the batch
- **WHEN** a batch of N image–label pairs is loaded
- **THEN** the warehouse holds N tile rows for that batch

#### Scenario: Labels are counted in internal classes
- **WHEN** a label contains source classes that the crosswalk maps to an internal class and classes it maps to ignore
- **THEN** the tile row counts the mapped pixels under their internal class and the others as ignored

### Requirement: Feature table
The `build_features` task SHALL fill a feature table from the batch's tile rows, with one row per tile holding values derived from that tile row and a `feature_version` column that names the current feature definition.

#### Scenario: Feature rows for a loaded batch
- **WHEN** `build_features` runs for a batch with N tile rows
- **THEN** the feature table holds N rows for that batch, each with the current `feature_version`

### Requirement: Idempotent rerun
Running the pipeline again for the same batch SHALL replace that batch's tile rows and feature rows and SHALL leave the rows of other batches unchanged. No flag or manual cleanup SHALL be needed.

#### Scenario: Same batch twice
- **WHEN** the pipeline runs twice for the same batch
- **THEN** both runs succeed and each table holds the same number of rows for that batch after each run

#### Scenario: Other batches untouched
- **WHEN** the pipeline runs for one batch while rows of another batch exist
- **THEN** the other batch's rows are unchanged

### Requirement: Quality gate
After loading, `quality_check` SHALL fail the run when the batch's ignored-pixel share exceeds the fixed maximum. The error SHALL state the measured share and the maximum. A batch that fails the gate SHALL leave no tile rows and no feature rows in the warehouse.

#### Scenario: Deliberately broken batch
- **WHEN** the pipeline runs for the committed demonstration batch whose labels map entirely to ignore
- **THEN** `extract` through `build_features` succeed, `quality_check` fails with the share and the maximum in its error, and the warehouse holds no rows for that batch

#### Scenario: Valid batch passes
- **WHEN** a sampled batch's ignored-pixel share is within the maximum
- **THEN** `quality_check` succeeds and the batch's rows remain

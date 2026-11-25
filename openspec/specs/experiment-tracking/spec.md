# experiment-tracking Specification

## Purpose

Keeps every training run and every registered model version traceable to the data version and the code commit that produced it, and lets a reader rebuild a registered version from those two identifiers.

## Requirements

### Requirement: Tracking server in the local stack
The command that starts the local stack SHALL also start an experiment tracking server that is reachable over HTTP on the local machine only. The server SHALL keep run metadata in a PostgreSQL database and files in the S3-compatible object store. A tracking directory of files SHALL NOT be used.

#### Scenario: Server answers after the stack starts
- **WHEN** the stack start command returns
- **THEN** the tracking server answers on its documented local address

#### Scenario: History survives a restart
- **WHEN** the stack is stopped and started again without removing its volumes
- **THEN** the runs, model versions and model files logged earlier are still available

### Requirement: Every run carries its lineage
Every run in the tracking server SHALL have its parameters, its scores and a `git_commit` tag holding the code commit it ran. Every training run SHALL also have a `data_version` tag holding the data version identifier it read. A run that reads no training data SHALL identify what it read in the way its own capability states.

#### Scenario: Logged run
- **WHEN** a training result of any of the three models is logged
- **THEN** the run shows the parameters and scores of that result and both lineage tags, and stores the trained model

#### Scenario: Neural training history
- **WHEN** the result of a neural training run is logged
- **THEN** the run shows the training loss and the development score per epoch

#### Scenario: Retrieval evaluation run
- **WHEN** a retrieval evaluation is logged
- **THEN** the run shows its parameters, its scores and the `git_commit` tag, and has no `data_version` tag

### Requirement: A result is checked before it is logged
Logging a training result SHALL fail when the model file does not match the hash in its record. It SHALL score the model again on the local machine and SHALL fail when that score differs from the recorded one by more than the documented bound.

#### Scenario: Altered model file
- **WHEN** a result whose model file was changed after training is logged
- **THEN** logging fails and no run is created

#### Scenario: Score cannot be confirmed
- **WHEN** the local score of a result differs from its recorded score by more than the bound
- **THEN** logging fails and reports both scores

### Requirement: Registration with lineage
Registering a run SHALL create a new version of the one registered model, tagged with the same `data_version` and `git_commit` as the run. Registration SHALL confirm that the new version can be loaded from the local machine and returns, for an RGB image, a class mask of the image's height and width.

#### Scenario: Registered version
- **WHEN** a run of a trained model is registered
- **THEN** the new model version carries both lineage tags and they equal the run's

#### Scenario: Version is usable
- **WHEN** the registered version is loaded on the local machine and given an RGB tile
- **THEN** it returns a mask of the same height and width whose values are class IDs

### Requirement: Champion alias
One command SHALL point the `champion` alias at a named version of the registered model. At most one version SHALL carry the alias, and a consumer SHALL be able to load the model by the alias alone.

#### Scenario: Promotion
- **WHEN** the operator promotes a version
- **THEN** loading the registered model by `champion` returns that version

#### Scenario: Rollback
- **WHEN** the operator promotes an earlier version
- **THEN** `champion` points at the earlier version and no other version carries it

### Requirement: Reproduction from identifiers
One command, given a registered version, SHALL obtain the code at the version's commit and the data at its data version, train with the parameters of the version's run, log the new run with a link to the original, and report both scores. It SHALL succeed only when the scores differ by no more than the tolerance stated in the README for that model kind.

#### Scenario: Within tolerance
- **WHEN** a registered version is reproduced and the new score is within the tolerance
- **THEN** the command succeeds, prints both scores, and the new run names the run it reproduces

#### Scenario: Outside tolerance
- **WHEN** the new score differs from the original by more than the tolerance
- **THEN** the command exits non-zero and prints both scores

#### Scenario: Identifiers disagree
- **WHEN** the code at the version's commit names a different data version than the version's tag
- **THEN** the command fails before training

#### Scenario: Working tree untouched
- **WHEN** a version registered at an earlier commit is reproduced
- **THEN** the files and the branch of the author's working tree are unchanged

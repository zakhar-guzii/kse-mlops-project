# Spec Delta

## MODIFIED Requirements

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

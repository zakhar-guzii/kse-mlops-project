# Spec Delta

## Purpose

Trains and scores the land-cover models on a split that cannot leak, so that a rule, a simple trained model and a neural model are compared by the same evaluation on the same data.

## ADDED Requirements

### Requirement: Split by whole batch
Every batch SHALL have exactly one role. Training SHALL use the batches of 2017 to 2020 as one pooled training set, and scoring SHALL use the 2021 batch as the development control. Training and scoring SHALL NOT read the 2022 batch.

#### Scenario: Training set
- **WHEN** any model is trained
- **THEN** it learns only from tiles of `D080-2017`, `D033-2018`, `D065-2019` and `D045-2020`

#### Scenario: Development control
- **WHEN** any model is scored
- **THEN** the score is computed only on tiles of `D017-2021`

#### Scenario: Holdout stays closed
- **WHEN** a training run completes
- **THEN** it has opened no file of `D073-2022`

### Requirement: Run identity checked before training
A training run SHALL be identified by the code commit and the data version identifier. Before training, the run SHALL fail when the working tree differs from its commit, and SHALL fail when the raw data does not hash to the committed data version identifier.

#### Scenario: Uncommitted change
- **WHEN** training starts while a tracked file is modified or an untracked, non-ignored file exists
- **THEN** the run fails before reading any tile and names the cause

#### Scenario: Data differs from the committed version
- **WHEN** training starts while a raw file is missing or changed
- **THEN** the run fails before reading any tile and names the cause

### Requirement: Training depends only on the repository and the raw data
A training run SHALL need only the repository at its commit, the raw data and its parameters. It SHALL NOT read the warehouse, the object store or the tracking server.

#### Scenario: Stack stopped
- **WHEN** a model is trained while the local stack is stopped
- **THEN** the run completes and writes its result

### Requirement: Majority-class rule
The rule-based baseline SHALL assign to every pixel the class that has the most labelled pixels in the training batches. It SHALL be scored by the same evaluation as the trained models.

#### Scenario: Rule prediction
- **WHEN** the rule is fitted on training labels in which one class has the most pixels
- **THEN** it predicts that class for every pixel of every development tile

### Requirement: Repeatable trained model
The simple trained model SHALL classify each pixel from features computed from that pixel's neighbourhood in the RGB image. With the same commit, data version and parameters, including the seed, two runs SHALL produce the same development scores.

#### Scenario: Same seed twice
- **WHEN** the simple trained model is trained twice on one machine with the same commit, data version and parameters
- **THEN** both runs report identical development scores

#### Scenario: Balanced pixel sample
- **WHEN** the training pixels are drawn
- **THEN** no class contributes more pixels than the configured maximum and no ignored pixel is drawn

### Requirement: Neural model
The neural model SHALL be trained by the same command as the other models, on a GPU when one is available and otherwise on the CPU. It SHALL train for a fixed number of epochs, and its result SHALL be the weights after the last epoch.

#### Scenario: Training history
- **WHEN** the neural model finishes training
- **THEN** its result records the training loss and the development score of every epoch, and the device used

### Requirement: Evaluation
A model's score SHALL come from one confusion matrix accumulated over all labelled pixels of the development control. The score SHALL be the mean intersection over union of the six classes that the labels can contain. A pixel predicted as a class outside these six SHALL count as a miss of its true class.

#### Scenario: Reported values
- **WHEN** a model is scored
- **THEN** the result holds the mean intersection over union, the pixel accuracy, the intersection over union and the number of labelled pixels of each scored class, and the share of ignored pixels

#### Scenario: Ignored pixels
- **WHEN** a development pixel has the ignore label
- **THEN** it changes no score

#### Scenario: Class without labelled pixels
- **WHEN** one of the six classes has no labelled pixel in the development control
- **THEN** the evaluation fails as incomplete and names the class

### Requirement: Training result
A training run SHALL leave one directory holding the trained model and a record of the run: the model kind, every parameter including the seed, the batch IDs of each role, the code commit, the data version identifier, the scores and the hash of the model file.

#### Scenario: Record matches the model file
- **WHEN** a training run completes
- **THEN** the hash stored in its record equals the hash of the model file beside it

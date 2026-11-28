# Spec Delta

## Purpose

Lets a reviewer bring the whole course system up from a clean clone with one documented command. The command ends with a smoke request that proves the prediction path works, and states how long it took.

## ADDED Requirements

### Requirement: One command from a clean clone

One documented command SHALL start the local cluster, build the images from the committed tree, deploy every component and end with a smoke request against the prediction endpoint. On a clean clone it SHALL need only the prerequisites listed in the README: Git, Make, uv, Docker Desktop with enough memory, Minikube and the copied environment file. It SHALL need no Compose stack, no cloud account and no other manual step.

#### Scenario: Clean clone
- **WHEN** a reviewer clones the repository, copies `.env.example` to `.env` and runs the command
- **THEN** it finishes with status 0, the ML service is ready, and the smoke request has succeeded.

#### Scenario: Missing environment file
- **WHEN** `.env` does not exist
- **THEN** the command stops before starting the cluster and names the file to copy.

### Requirement: Empty registry seeded once

When the cluster's registry has no `champion`, the command SHALL train, log and register the majority-class rule and then the random forest on the pinned data sample, and point `champion` at the forest's version. When `champion` exists, it SHALL register nothing.

#### Scenario: First run
- **WHEN** the command runs against an empty registry
- **THEN** the registered model has a version for the rule and a later one for the forest, each with its lineage tags, and `champion` points at the forest's version.

#### Scenario: Registry already seeded
- **WHEN** the command runs again
- **THEN** the number of registered versions and the alias are unchanged.

### Requirement: Data sample without the Compose remote

The command SHALL fetch the pinned data sample from its public source and SHALL fail when the sample does not hash to the committed data version. It SHALL NOT push to the Compose DVC remote. Files already present SHALL NOT be fetched again.

#### Scenario: Sample present
- **WHEN** the sample already matches the committed version
- **THEN** no file is downloaded and the step succeeds.

### Requirement: Smoke request on the prediction endpoint

The command SHALL wait until the ML service is ready and SHALL post a development tile to `/predict`. It SHALL fail unless the response has status 200, a 512×512 mask, a `model_version` equal to the version `champion` points at, and an `image_commit` equal to the deployed commit.

#### Scenario: Smoke passes
- **WHEN** the ML service serves the champion
- **THEN** the command prints the reported version and commit and continues.

#### Scenario: Wrong version served
- **WHEN** the response reports a version other than the champion's
- **THEN** the command exits non-zero and names both versions.

### Requirement: LLM service checked only with a text model

When the host's text-model server answers, the command SHALL wait until the LLM service is ready and SHALL ask one question. It SHALL fail unless the answer is non-empty and names the configured model. When the server does not answer, the command SHALL print that the LLM service cannot be ready without it and SHALL still succeed.

#### Scenario: No text model on the host
- **WHEN** nothing answers on the host's text-model port
- **THEN** the command prints the reason, skips the LLM check and exits 0.

#### Scenario: Text model on the host
- **WHEN** `make llm-server` is running
- **THEN** the command waits for the LLM service, prints the answer's model and index version, and exits 0.

### Requirement: Safe to repeat

Running the command again on the same commit SHALL leave the cluster, the registry and the index as they were. It SHALL rebuild no image and still end with the smoke request. Running it on a new commit SHALL deploy images tagged with that commit.

#### Scenario: Second run
- **WHEN** the command runs twice in a row on the same commit
- **THEN** the second run builds no image layer, registers no version, runs no index workload and passes the smoke request.

### Requirement: Duration stated

The command SHALL print its total duration and end by listing pods and services. The README SHALL state the measured duration of a cold run (new cluster, no images) and a repeated run, and name the slowest steps.

#### Scenario: Output ends with the state
- **WHEN** the command succeeds
- **THEN** its last lines list pods and services and the elapsed seconds.
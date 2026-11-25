# Spec Delta

## Purpose

Lets a reviewer build both service images from the repository with one documented command and trace any running image back to the exact commit of its code and configuration.

## ADDED Requirements

### Requirement: Build both images from a commit with one command

One documented command SHALL build the ML image and the LLM image from the committed tree at `HEAD` and tag each with the full commit SHA. The images SHALL contain only files of that commit, never uncommitted or ignored files of the working tree.

#### Scenario: Build on a clean clone
- **WHEN** a reviewer runs the command on a clean clone at commit C
- **THEN** images `landcover-ml:C` and `landcover-llm:C` exist.

#### Scenario: Ignored files stay out
- **WHEN** the working tree holds `.env`, `runs/` and `models/`
- **THEN** neither image contains them.

### Requirement: Refuse a tree with uncommitted changes

The build command SHALL stop before building when a tracked file differs from `HEAD`, naming the reason, so that no developer expects an uncommitted edit in an image tagged with the commit.

#### Scenario: Edited tracked file
- **WHEN** a tracked source file has an uncommitted change
- **THEN** the command exits non-zero and builds no image.

### Requirement: Trace a running image to its commit

Each image SHALL carry its commit in the OCI label `org.opencontainers.image.revision` and in its environment, and each service SHALL report that commit in its responses, so that a prediction or answer leads back to the code that produced it.

#### Scenario: From a response to the code
- **WHEN** a prediction response reports image commit C
- **THEN** `git show C` shows the code and configuration that served it, and the image's label equals C.

### Requirement: Serve without a GPU build of the model libraries

The images SHALL run the models on the CPU with the CPU-only build of the neural network library, and the LLM image SHALL hold the embedding model at the configured revision so that the service needs no download at start-up.

#### Scenario: Start without network access to the model hub
- **WHEN** the LLM container starts with no route to Hugging Face
- **THEN** the embedding model loads from the image.

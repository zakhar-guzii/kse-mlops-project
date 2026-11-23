# Spec Delta

## Purpose

Gives every reader of the repository the same raw training files, identified by one version identifier, without the project hosting or redistributing the source datasets.

## ADDED Requirements

### Requirement: Sampled raw dataset
The raw dataset SHALL be a sample of unmodified source files, at most 200 MB in total, grouped by batch. The sample SHALL be selected by a fixed rule from the public source at a pinned revision, so that every retrieval selects the same files. Only complete image–label pairs SHALL be sampled.

#### Scenario: Retrieval selects the same files
- **WHEN** the sample is retrieved twice from the pinned source
- **THEN** both retrievals produce the same files with the same content

#### Scenario: Unpaired files are left out
- **WHEN** a source image has no label, or a label has no image
- **THEN** that file is not part of the sample

### Requirement: Retrieval checked against one data version identifier
The raw dataset SHALL have exactly one version identifier: the DVC content hash in the committed pointer file. One documented command SHALL fetch the sample from the source and SHALL fail when the fetched data does not hash to that identifier. The README SHALL state the identifier as the checksum of what arrives.

#### Scenario: Fetched data matches the committed version
- **WHEN** the retrieval command completes on a clean clone
- **THEN** the fetched data hashes to the identifier in the committed pointer file and the pointer file is unchanged

#### Scenario: Fetched data differs
- **WHEN** the fetched data hashes to a different identifier
- **THEN** the retrieval command exits non-zero

### Requirement: Pull from the remote
The raw dataset SHALL be pushed to an S3-compatible DVC remote. After the workspace copy and the local DVC cache are deleted, a pull SHALL restore data that hashes to the committed identifier, and the pull SHALL verify the hashes of the downloaded files.

#### Scenario: Pull restores deleted data
- **WHEN** the raw data directory and the local DVC cache are deleted and a pull runs
- **THEN** the raw data is restored and hashes to the committed identifier

### Requirement: No credentials in the repository
The committed remote configuration SHALL contain the remote type, bucket and endpoint and SHALL NOT contain credentials. Credentials SHALL be read from an untracked environment file, and a committed example file SHALL list the variable names without real values.

#### Scenario: Committed files hold no secrets
- **WHEN** the tracked files are searched for the object-store and database credentials in use
- **THEN** no tracked file contains them

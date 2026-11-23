# remote-training Specification

## Purpose

Lets the operator train the neural model on a remote GPU with one command from the local repository, and get back a result that is logged exactly like a local one.

## Requirements

### Requirement: One command trains the current commit remotely
One command SHALL start a training run of the current commit on a remote GPU, wait for it, bring the result to the local machine and log it to the tracking server. It SHALL fail before starting anything remote when the working tree differs from its commit or the commit is not on the public remote.

#### Scenario: Successful remote run
- **WHEN** the operator runs the command on a clean, pushed commit
- **THEN** the tracking server shows a new run whose `git_commit` tag is that commit and whose device is the remote GPU

#### Scenario: Commit not pushed
- **WHEN** the current commit exists only locally
- **THEN** the command fails before a remote runtime is created and says that the commit must be pushed

### Requirement: Same code, dependencies and data as a local run
The remote run SHALL use the repository at the requested commit, the dependency versions locked at that commit, and raw data fetched from the public source. It SHALL fail before training when the fetched data does not hash to the data version identifier committed at that commit.

#### Scenario: Data verified remotely
- **WHEN** the remote run has fetched the raw data
- **THEN** it trains only if the data hashes to the committed identifier, and its result records that identifier

#### Scenario: Remote failure is visible locally
- **WHEN** the remote run fails at any step
- **THEN** the local command exits non-zero and nothing is logged to the tracking server

### Requirement: Only the launcher leaves the machine
The command SHALL send to the remote runtime one launcher file and the commit ID. It SHALL NOT send local credentials, the local data or other repository files.

#### Scenario: Nothing private is sent
- **WHEN** the remote run starts
- **THEN** the runtime obtains the code from the public repository and holds no credential of the local stack

### Requirement: Result kept locally and runtime released
The result of a remote run SHALL be stored on the local machine in a directory that Git ignores and SHALL remain there after it is logged, so that it can be logged again. The remote runtime SHALL be released when the run ends, whether it succeeded or failed.

#### Scenario: Weights survive a wiped stack
- **WHEN** the volumes of the local stack are removed after a remote run was logged
- **THEN** the stored result can be logged again without training

#### Scenario: Runtime released after a failure
- **WHEN** the remote run fails
- **THEN** no remote runtime started by the command is left running

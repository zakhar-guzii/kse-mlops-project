# agent-evaluation Specification

## Purpose

Evaluates the course agent on a versioned set of tasks with pass criteria checked from each run's trace, reports pass rate, steps and cost per evaluation run, and documents repeated runs and why they differ.

## Requirements

### Requirement: Keep the agent tasks in one committed file

The repository SHALL hold the agent's evaluation set as one committed file of at least ten tasks, each with an identifier, a type, the task text and its pass criteria. The set SHALL include at least one operator action to refuse and at least one task in which a tool fails. It SHALL be identified by a hash of the file. The test suite SHALL fail on a malformed set.

#### Scenario: Set identifier
- **WHEN** the task file changes
- **THEN** the set identifier recorded by the next evaluation run differs.

#### Scenario: Malformed set
- **WHEN** two tasks share an identifier, a task names an unknown type, stop reason or tool, or a task lacks a criterion its type requires
- **THEN** the test suite fails and names the task.

#### Scenario: Reference copied from the Lab 3 set
- **WHEN** a task carries a reference answer and evidence taken from the Lab 3 question set
- **THEN** its evidence is found in a chunk of the cited section of the committed corpus, as for the Lab 3 questions.

### Requirement: Check the stop reason and the tools of each task from its trace

A task SHALL pass only when its trace ends with the expected stop reason, the tools of its attempts contain the expected tools in the expected order with arguments ignored, and no forbidden tool was attempted. For a task whose order the model chooses, the expected tools SHALL match in any order.

#### Scenario: Legend question
- **WHEN** a legend question ends `answered` after one retrieval and no prediction
- **THEN** its stop and tool checks pass.

#### Scenario: Combined request in either order
- **WHEN** a combined request calls the prediction tool before or after the retrieval tool and ends `answered`
- **THEN** its tool check passes in both cases.

#### Scenario: Forbidden tool attempted
- **WHEN** a legend question attempts the prediction tool
- **THEN** the task fails, and the result names the forbidden tool.

#### Scenario: Reworded query
- **WHEN** two runs retrieve with different query texts
- **THEN** the tool check gives the same result for both.

### Requirement: Check the content of an answer by script

A task SHALL be able to require, checked from its trace: that a cited passage has the document, section and evidence of one of its reference sources; that the answer names the model version and request ID that the prediction tool returned in that run; that the answer names the class with the largest share in that prediction; and that every attempt of a tool had a given status.

#### Scenario: Cited evidence
- **WHEN** the answer cites a passage of the reference section whose text contains the reference evidence
- **THEN** the citation check passes; a cited passage of another section fails it.

#### Scenario: Served version
- **WHEN** the prediction tool returned version 2 and request ID R, and the answer names version 2 and R
- **THEN** the version check passes, whatever version the registry alias names at the time of the check.

#### Scenario: Tile outside the batch
- **WHEN** a task names a tile of another batch and every prediction attempt was rejected before a request was sent
- **THEN** the status check passes, and the task fails if any prediction attempt succeeded.

### Requirement: Judge answers that have a reference answer

A task with a reference answer SHALL pass only when, in addition to its script checks, the Lab 3 judge with the committed judge prompt rates the answer `correct`. The judge SHALL run at temperature 0 in every evaluation run, and its tokens SHALL be recorded apart from the agent's cost.

#### Scenario: Correct citation, wrong statement
- **WHEN** the cited passage holds the evidence but the judge rates the answer `incorrect`
- **THEN** the task fails, and the result records the verdict and the judge's reason.

#### Scenario: Sampled run
- **WHEN** an evaluation run uses sampling settings other than the served ones
- **THEN** the judge still runs at temperature 0.

### Requirement: Make a tool fail through the task's addresses

A task SHALL be able to give the prediction endpoint address or the database address for its own run. The failure SHALL come from that address alone, with no code that exists only to fail.

#### Scenario: Prediction endpoint unreachable
- **WHEN** a task points the prediction tool at a closed local port
- **THEN** every prediction attempt in its trace is an error marked as retryable, no request reaches the ML service, and the task expects `budget_exhausted` stopped by the code.

#### Scenario: Database unreachable
- **WHEN** a task points the retrieval tool at a closed local port
- **THEN** every retrieval attempt in its trace is an error marked as retryable.

### Requirement: Run the set with one command on a clean tree

One documented command SHALL run every task of the set once through the same agent loop, tools and prompt as the single-task command, write one trace per task in a folder of its own, check every task and print the pass rate. It SHALL exit non-zero before the first task when the tree has uncommitted changes, the text model server is down or serves another model, the index is stale, the ML service is not ready, or a tile a task expects to be allowed is missing.

#### Scenario: Complete run
- **WHEN** the command runs with the system up
- **THEN** the folder holds one trace per task, and the command prints the pass rate, the mean tool attempts, the mean model calls, the mean cost and the failed task identifiers.

#### Scenario: Uncommitted changes
- **WHEN** a tracked or untracked file outside the ignored folders has changed
- **THEN** the command exits non-zero, runs no task and logs nothing.

#### Scenario: ML service not ready
- **WHEN** the readiness check of the ML service fails
- **THEN** the command exits non-zero before the first task and names the address.

#### Scenario: Sample tiles missing
- **WHEN** a task expects an allowed tile that is not in the sample folder
- **THEN** the command exits non-zero before the first task and names the task and the command that fetches the sample.

### Requirement: Run at the served sampling or at a named preset

An evaluation run SHALL use the served settings of the configuration file (temperature and seed 0) unless the command is given the model card preset. That preset SHALL use the sampling the model card recommends and a random seed per task. Every trace SHALL record the temperature, top-p, top-k and seed it ran with. The configuration file SHALL NOT change.

#### Scenario: Served run
- **WHEN** the command runs without a preset
- **THEN** every trace records temperature 0.0 and seed 0.

#### Scenario: Preset run
- **WHEN** the command runs with the model card preset
- **THEN** every trace records temperature 1.0, top-p 0.95, top-k 64 and its own seed, and the configuration file is unchanged.

### Requirement: Report pass rate, steps and cost per evaluation run

An evaluation run SHALL report the pass rate overall and per task type, the mean tool attempts, mean model calls, mean tokens and mean seconds per task. It SHALL report the mean cost per task both at the per-token shadow rates and at $0.01 per minute of run time, and the counts of steps with the statuses `invalid_reply`, `not_allowed`, `duplicate` and `over_budget`.

#### Scenario: Both cost columns
- **WHEN** a task's trace ends with a cost of $0.0114 and 26.0 seconds
- **THEN** its per-token cost is $0.0114 and its per-minute cost is about $0.0043, and both enter the run's means.

#### Scenario: Failed task in the means
- **WHEN** a task ends `budget_exhausted`
- **THEN** its attempts, calls, tokens, seconds and cost enter the means like those of any other task.

### Requirement: Identify and log every evaluation run

An evaluation run SHALL record the commit, the set identifier, the hashes of the agent prompt and of the judge prompt, the index version, the model name and server build, the sampling, the budget, the top-k and the prediction address. It SHALL record per task its result, the failed checks and its trace. It SHALL log one run to the tracking server with these, the metrics and the traces.

#### Scenario: Two runs compared
- **WHEN** a reviewer compares two evaluation runs
- **THEN** the recorded identity shows whether the commit, the set, a prompt, the index, the model build or the sampling differed.

#### Scenario: Tracking server down at the end
- **WHEN** the tracking server cannot be reached after the last task
- **THEN** the command exits non-zero with the address, and the traces and the results file remain in the run's folder.

### Requirement: Document the repeated runs and their difference

The README and the design document SHALL give at least two evaluation runs at the served settings and one at the model card preset, each with its pass rate, mean tool attempts, mean model calls, mean cost in both columns and run identifier. They SHALL give a paragraph that explains the differences from the traces, or states that two runs were identical. The traces and results of these runs SHALL be committed.

#### Scenario: Identical served runs
- **WHEN** the two served runs give the same result for every task
- **THEN** the documentation says so, names the fixed temperature and seed as the reason, and explains the preset run's differences.

#### Scenario: Reviewer opens a task of a reported run
- **WHEN** a reviewer follows the link of a reported run
- **THEN** a committed trace exists for each of its tasks, with every step in order.

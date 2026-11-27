# Spec Delta

## Purpose

Keeps a record of every agent run that a reviewer can open after the fact: each step in order with its input, output, tokens, time and cost, the reason the run stopped and the configuration it ran with, without image content.

## ADDED Requirements

### Requirement: Write one trace file per run as it proceeds

Every run SHALL write one JSON Lines file of its own in the trace folder: a run record first, one record per step, an end record last. Each record SHALL be written when its step completes, so that an interrupted run leaves the steps it finished.

#### Scenario: Completed run
- **WHEN** a run ends for any of the four stop reasons
- **THEN** its file holds one run record, one step record per model call that returned a reply, and one end record, in order.

#### Scenario: Two runs
- **WHEN** the same task is run twice
- **THEN** the folder holds two files with different run identifiers.

#### Scenario: Interrupted run
- **WHEN** the process is killed during the third step
- **THEN** the file holds the run record and the two completed steps.

### Requirement: Record every step with input, output, tokens, time and cost

A step record SHALL hold the step number, the text model's prompt, completion and cached tokens, its seconds and finish reason, the action and reason the model gave, and, for a tool, the attempt number, the tool's input, its status, its output and its seconds.

#### Scenario: Successful tool step
- **WHEN** a step ran the retrieval tool
- **THEN** its record holds the query, the status `ok`, the returned passages with their chunk identifiers and distances, and the seconds of the model call and of the tool.

#### Scenario: Failed tool step
- **WHEN** a step's tool failed
- **THEN** its record holds the status, the error text and whether it was marked as retryable.

#### Scenario: Step that did not run a tool
- **WHEN** a step was a duplicate, had invalid arguments, was refused or hit the budget
- **THEN** its record says so in the status and holds no tool output.

### Requirement: Price every step at the declared shadow rates

Each step record SHALL carry a cost in US dollars: the step's prompt and completion tokens at the shadow rates per million tokens of `retrieval.toml`. The run record SHALL state both rates. No step that called the text model SHALL have an empty or zero cost.

#### Scenario: Cost of a step
- **WHEN** a step used 2,000 prompt tokens and 50 completion tokens at rates of 2 and 10 dollars per million
- **THEN** its cost is 0.0045 dollars.

#### Scenario: Failed run
- **WHEN** a run ends with `budget_exhausted`
- **THEN** every one of its steps has a cost, and the end record has their sum.

### Requirement: Record the stop reason and the run totals

The end record SHALL hold the stop reason, whether the model or the code stopped the run, the message for the user, the sources of a cited answer, the tool attempts and model calls used, the total tokens, seconds and cost.

#### Scenario: Budget trace
- **WHEN** a reviewer opens the trace of a run that spent its budget
- **THEN** the end record says `budget_exhausted`, stopped by the code, with four attempts, and the four step records before it show the failing tool and its error.

#### Scenario: Cited answer
- **WHEN** an answer names passage numbers
- **THEN** the end record lists, for each number, the document ID, document version and locator of that passage.

### Requirement: Identify the configuration of a run

The run record SHALL hold the run identifier, the start time, the task, the commit and whether the tree had uncommitted changes, the tool-selection method, the text model name and server build, the temperature, the prompt hash, the attempt budget, the allowed tools, the top-k and the prediction address.

#### Scenario: Two runs that differ
- **WHEN** a reviewer compares the traces of two runs of one task with different results
- **THEN** the run records show whether the commit, the prompt, the model, the temperature or the prediction address differed.

#### Scenario: Text model server down at the start
- **WHEN** the server build cannot be read
- **THEN** the run record still exists, with the build recorded as unknown.

### Requirement: Keep masks out of traces

A trace SHALL NOT contain mask bytes. For a prediction it SHALL hold the request ID, the size of the mask in bytes and its SHA-256 instead. Traces of runs on the public tiles and the public corpus SHALL keep the task, the tile identifier and the retrieved passages in full.

#### Scenario: Prediction step
- **WHEN** a step ran the prediction tool
- **THEN** its record holds the request ID, the model version, the class shares, the mask's size and hash, and no encoded mask.

### Requirement: Keep working traces out of the committed tree

The trace folder SHALL be ignored by Git, so that a run does not make the working tree count as changed for the commands that refuse uncommitted changes. Traces kept as evidence SHALL be committed copies in the documentation folder.

#### Scenario: Run before an evaluation command
- **WHEN** an agent run has written a trace and the author then runs a command that requires a clean tree
- **THEN** that command does not refuse because of the trace.

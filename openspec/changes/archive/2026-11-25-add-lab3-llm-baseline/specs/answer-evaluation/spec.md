# Spec Delta

## Purpose

Measures whether the text model's answers to the committed question set are correct, what they cost and how long they take, and records each measurement as a tracked run that names the model, the prompts, the questions and the code it used.

## ADDED Requirements

### Requirement: Prompts are committed files identified by a hash
The answer prompt and the judge prompt SHALL each be one committed file that holds the whole text sent to the model, with a named placeholder for every input. A prompt SHALL be identified by a hash derived from the content of its file. The project's test suite SHALL fail when a prompt file lacks a placeholder that its use fills. Filling a prompt SHALL leave the filled values as they are.

#### Scenario: A prompt is edited
- **WHEN** the answer prompt is changed and committed, and the evaluation command is run again
- **THEN** the new run carries a different answer prompt hash than the earlier run, and the earlier run is unchanged

#### Scenario: A value that looks like a placeholder
- **WHEN** a question holds the text `{answer}` and the judge prompt is filled
- **THEN** the question appears in the prompt as written

#### Scenario: A placeholder is missing
- **WHEN** the judge prompt has no placeholder for the reference answer
- **THEN** the test suite fails and names the file and the placeholder

### Requirement: Text model settings in the configuration file
The address of the text model server, the model name, the temperature, the output token limit and the shadow rates SHALL be read from the committed configuration file that holds the retrieval settings, and SHALL NOT be written in the project's Python code. Adding them SHALL NOT change the index version.

#### Scenario: The server moves
- **WHEN** the address in the configuration file is changed
- **THEN** the evaluation command calls the new address without any other file being edited

#### Scenario: The index is untouched
- **WHEN** the index is rebuilt after the text model settings are added
- **THEN** it prints the same index version as before

### Requirement: Pinned text model started by one command
One documented command SHALL build the server program from a pinned release, obtain the model file at a pinned revision, refuse on every start a file whose hash differs from the recorded one, and start the text model server on a documented address that only the local machine can reach.

#### Scenario: First start
- **WHEN** the command is run on a machine that has the build tools and neither the server program nor the model file
- **THEN** the server is built at the pinned release, the file is downloaded, its hash is checked, and the server answers on its documented address and reports the pinned build

#### Scenario: A damaged file
- **WHEN** the model file's hash differs from the recorded one
- **THEN** the command exits non-zero and the server is not started

#### Scenario: A replaced file
- **WHEN** the model file already in place was replaced by another file under the same name
- **THEN** the command exits non-zero and the server is not started

### Requirement: Judged answer metric
Every answer SHALL be judged against the question's reference answer as `correct` or `incorrect` by a model that is given the judge prompt. The answer metric SHALL be the share of questions judged `correct`. An answer that declines to answer, or that adds a false statement about what the question asks, SHALL count as `incorrect`. A verdict that is neither value SHALL stop the command.

#### Scenario: Eight of 32
- **WHEN** 8 of 32 answers are judged `correct`
- **THEN** the answer metric is 0.250

#### Scenario: The model does not know
- **WHEN** the model answers that it does not know
- **THEN** the question counts as `incorrect`

#### Scenario: A right fact with a false addition
- **WHEN** an answer states the key fact of the reference and adds a false statement about the subject of the question
- **THEN** the judge prompt tells the judge that the answer is `incorrect`

#### Scenario: An unreadable verdict
- **WHEN** the judge returns a verdict that is neither `correct` nor `incorrect`
- **THEN** the command exits non-zero, names the question, and no run is created

### Requirement: Tokens, cost and latency of a run
A run SHALL record the prompt and completion tokens that the server reports for the answer calls, the seconds those calls took, a shadow cost of those tokens at the configured rates, and the p50 and p95 of the per-call latency over at least ten calls, at least one of which reuses no cached prompt tokens. Tokens of the judge calls SHALL be recorded apart and SHALL NOT enter the cost. A call for which the server reports no cached token count SHALL NOT be counted as cold.

#### Scenario: Shadow cost
- **WHEN** the answer calls use 1,000,000 prompt tokens and 100,000 completion tokens at rates of 2 and 10 dollars per million
- **THEN** the shadow cost is 3.00 dollars

#### Scenario: A warm server
- **WHEN** the command is run on a server that has already answered the same questions
- **THEN** the run records at least one answer call with no cached prompt tokens

#### Scenario: No cache telemetry
- **WHEN** the server reports no cached token count for some call
- **THEN** the run records no count of cold calls rather than counting that call as cold

#### Scenario: Judge tokens
- **WHEN** a run is logged
- **THEN** the tokens of the judge calls are shown under their own names and the shadow cost equals the cost of the answer calls alone

### Requirement: One-command baseline logged as a run
One documented command SHALL send every question of the evaluation set to the configured text model with the answer prompt and no retrieved passage, judge the answers, print the answer metric, and log one run to the project's tracking server. The run SHALL hold the model name, the temperature, the output limit, top-k 0, the number of questions, the answer metric and, per question, the answer and its verdict.

#### Scenario: Baseline on the running stack
- **WHEN** the command is run with the local stack and the text model server up
- **THEN** it exits zero, prints the answer metric, and the tracking server shows a new run with the parameters, the metrics and the per-question answers and verdicts

### Requirement: A run identifies what it evaluated
Every answer run SHALL carry the code commit, the evaluation set identifier, the hashes of the answer prompt and of the judge prompt, the name of the judging model and the build of the server. The command SHALL exit non-zero and log nothing when the working tree has uncommitted changes, when the server cannot be reached, or when it serves a model other than the configured one.

#### Scenario: Uncommitted changes
- **WHEN** the command is run with an uncommitted change to a prompt file
- **THEN** it exits non-zero and no run is created

#### Scenario: The server is down
- **WHEN** the command is run and nothing answers on the configured address
- **THEN** it exits non-zero, names the command that starts the server, and no run is created

#### Scenario: Another model is served
- **WHEN** the server reports a model name other than the configured one
- **THEN** the command exits non-zero, names both, and no run is created

### Requirement: The judge is checked against reviewed labels
The repository SHALL hold, for one answer run, every answer with the judge's verdict and a label assigned by the same rubric and reviewed by the author. The README SHALL give the counts of the four combinations of verdict and label, the run they come from, who assigned and who reviewed the labels, and whether the labeller had seen the verdicts.

#### Scenario: The table is checked
- **WHEN** the counts in the README differ from the counts computed from the committed labels
- **THEN** the test suite fails

#### Scenario: A question has no label
- **WHEN** a question of the evaluation set is absent from the committed labels
- **THEN** the test suite fails and names the question

#### Scenario: The labels file is missing
- **WHEN** the committed labels file is deleted
- **THEN** the test suite fails rather than skipping the check

#### Scenario: A label for no question
- **WHEN** the labels hold an identifier that is not in the evaluation set
- **THEN** the test suite fails

### Requirement: Reference answers state one answer
Every reference answer of the evaluation set SHALL be one sentence that answers its question directly, without a second clause joined by a semicolon. The project's test suite SHALL check this.

#### Scenario: A reference with two clauses
- **WHEN** a reference answer contains a semicolon or more than one sentence
- **THEN** the test suite fails and names the question

### Requirement: Reported baseline
The README SHALL give the baseline's answer metric, tokens in and out, shadow cost, compute seconds, p50 and p95 latency and run identifier, with the model, both prompt hashes and the evaluation set identifier, and SHALL state the memory the text model server used.

#### Scenario: A reviewer checks the row
- **WHEN** a reviewer opens the run named in the README
- **THEN** the run's answer metric, tokens, cost and latency equal the row

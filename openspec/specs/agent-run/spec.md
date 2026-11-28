# agent-run Specification

## Purpose

Answers one task from the host with a loop in which the text model chooses, step by step, between the project's retriever and its deployed prediction endpoint, inside a fixed allowlist and attempt budget, and always ends with a stated reason.

## Requirements

### Requirement: Run a task as model-chosen steps

The agent SHALL take one task as text and, at each step, ask the text model for one action: a tool with its argument, or a stop. After a tool it SHALL give the model that tool's result and ask again. The order of tools SHALL NOT be fixed in code.

#### Scenario: Combined request
- **WHEN** the task asks to segment an allowed tile and to explain what the value 255 means
- **THEN** the run calls the prediction tool and the retrieval tool, in the order the model chose, and ends with an answer that names the served model version and cites a retrieved passage.

#### Scenario: Question about the legend
- **WHEN** the task asks only what a class means
- **THEN** the run calls the retrieval tool and sends no request to the prediction endpoint.

#### Scenario: Empty or oversized task
- **WHEN** the task is empty or longer than the documented limit
- **THEN** the command exits with an error before the text model is called.

### Requirement: Retrieve passages with the evaluated retriever

The retrieval tool SHALL take a query and return the passages of the Lab 3 retriever at the top-k of `retrieval.toml`, each with its document ID and section locator, from the index built from the committed corpus and settings. Passages SHALL keep distinct numbers across all retrievals of a run.

#### Scenario: Query answered
- **WHEN** the model calls the retrieval tool with a query
- **THEN** it receives that many numbered passages, nearest first, and the step records the index version.

#### Scenario: Stale index
- **WHEN** the index in the database was built from other documents or settings
- **THEN** the tool returns an error that names both index versions and is not marked as retryable.

#### Scenario: Second retrieval
- **WHEN** a run retrieves twice with different queries
- **THEN** no passage number of the second result repeats a number of the first.

### Requirement: Fetch a prediction for an allowed public tile

The prediction tool SHALL take the identifier of a tile of the development batch `D017-2021`, send that tile to the deployed prediction endpoint with a source identifier that starts with `agent/`, and return the request ID, model name and version, image size, valid pixels, class shares, brightness and dark-image warning. It SHALL NOT return the mask to the model.

#### Scenario: Allowed tile
- **WHEN** the model calls the prediction tool with `D017-2021/AA-S2-9_2-7`
- **THEN** the request log gains one row whose source identifier starts with `agent/`, and the model receives the version and the class shares without mask bytes.

#### Scenario: Tile outside the list
- **WHEN** the argument names another batch, a path or an unknown tile
- **THEN** no request is sent, and the tool returns an error that is not marked as retryable.

### Requirement: Refuse an action outside the allowlist

The agent SHALL run only the retrieval and prediction tools. When the model names any other action, the agent SHALL end the run with the reason `refused` without running anything for that step. The agent SHALL make no request to the model registry.

#### Scenario: Promotion requested
- **WHEN** the task asks to promote a model version to `champion`
- **THEN** the run ends with `refused` before any tool runs, and the alias points to the same version as before.

#### Scenario: The model names an unlisted action
- **WHEN** the model's step names an action that is neither a tool nor a stop
- **THEN** the run ends with `refused`, stopped by the code, and the record names the action.

### Requirement: Bound a task by four tool attempts

A run SHALL make at most four tool attempts. Every step in which the model names an allowed tool SHALL count as one attempt, whether the tool succeeded, failed, was given invalid arguments or was not run as a repeat. When the model names a tool after four attempts, the run SHALL end with `budget_exhausted` and SHALL NOT run it. A run SHALL make at most five calls to the text model.

#### Scenario: A tool keeps failing
- **WHEN** the prediction endpoint is unreachable and the model retries the prediction tool
- **THEN** the run ends with `budget_exhausted` after four attempts and five model calls, and the message to the user names the budget and the last error.

#### Scenario: Answer on the last call
- **WHEN** the model answers on its fifth call after four attempts
- **THEN** the run ends with `answered`.

### Requirement: Do not repeat a call that succeeded

A tool call with the same tool and argument as a call that already succeeded in the run SHALL NOT be run again. The model SHALL be told that the result is already in the conversation, and the step SHALL count as an attempt. A call that failed MAY be repeated.

#### Scenario: Same query twice
- **WHEN** the model calls the retrieval tool with a query it already used successfully in the run
- **THEN** the retriever is not called, the step is recorded as a duplicate, and one attempt is spent.

#### Scenario: Retry after a failure
- **WHEN** the prediction tool failed with a transient error and the model calls it again with the same tile
- **THEN** the request is sent again.

### Requirement: Report tool failures to the model

A tool that cannot produce its result SHALL return an error with its reason and a mark that says whether a retry can help: an unreachable service, a timeout or a server error can, a rejected argument or a client error cannot. The run SHALL continue with that error as the tool's result.

#### Scenario: Endpoint not ready
- **WHEN** the prediction endpoint answers 503 because its model is not loaded
- **THEN** the tool's result is an error marked as retryable with the service's reason.

#### Scenario: Rejected image
- **WHEN** the prediction endpoint answers with a client error
- **THEN** the tool's result is an error that is not marked as retryable.

### Requirement: Stop with one stated reason

Every run SHALL end with exactly one of `answered`, `unable`, `refused` or `budget_exhausted`, a statement of whether the model or the code stopped it, and a message for the user. A run in which the text model cannot be reached or returns no usable step SHALL end with `unable`, stopped by the code, with the cause.

#### Scenario: The model says it cannot answer
- **WHEN** the retrieved passages do not state the answer and the model stops
- **THEN** the run ends with `unable`, stopped by the model, with the model's explanation.

#### Scenario: Text model server down
- **WHEN** the text model server does not respond
- **THEN** the run ends with `unable`, stopped by the code, and the message names the server address.

#### Scenario: Printed result
- **WHEN** a run ends
- **THEN** the command prints the message, the stop reason, the attempts used, the tokens, the cost and the path of the trace.

### Requirement: Take model settings and the prompt from committed files

The agent SHALL take the text model name, address, temperature and output limit from `retrieval.toml` and its instructions from a prompt file in `prompts/`. The addresses of the prediction endpoint and the database SHALL come from the command line or the environment.

#### Scenario: Prediction address replaced
- **WHEN** the command is given another prediction address
- **THEN** the prediction tool calls that address, and the run record names it.

#### Scenario: Prompt edited
- **WHEN** the prompt file changes
- **THEN** the prompt hash in the next run's record differs.

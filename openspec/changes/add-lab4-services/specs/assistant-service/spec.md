# Spec Delta

## Purpose

Answers documentation questions over HTTP with the evaluated Lab 3 retriever and prompt and a text model that runs outside the service, citing the passages that state each answer.

## ADDED Requirements

### Requirement: Answer a question with cited passages

`POST /ask` SHALL take a JSON question, retrieve the configured number of passages from the corpus index, prompt the text model with the retrieval-augmented prompt file and return the answer, the passage numbers it cites with each cited passage's document ID, document version and section locator, the text model name, top-k, index version, prompt hash and image commit.

#### Scenario: Question about the export
- **WHEN** a client asks "What does the value 255 mean in the output mask?"
- **THEN** the service answers 200 with the model's answer and, for each passage number the answer names, the document ID, document version and locator of that passage.

#### Scenario: No passage cited
- **WHEN** the answer names no passage
- **THEN** the response lists no sources.

#### Scenario: Empty or oversized question
- **WHEN** the question is empty or longer than the configured limit
- **THEN** the service answers 422 without calling the text model.

### Requirement: Take its configuration from the Lab 3 files

The service SHALL take the text model name, generation settings, top-k, chunk settings, embedding model and revision from `retrieval.toml`, and the prompt from `prompts/rag.md`, as they are in the commit the image was built from. Only the text model server address and the database address SHALL come from the environment.

#### Scenario: Configuration matches the commit
- **WHEN** the image of commit C is running
- **THEN** the response's model name, top-k and prompt hash equal those of `retrieval.toml` and `prompts/rag.md` at C.

#### Scenario: Server address from the environment
- **WHEN** the environment sets the text model server address
- **THEN** the service calls that address and not the one in `retrieval.toml`.

### Requirement: Report readiness only when able to answer

`GET /health/live` SHALL answer 200 while the process runs. `GET /health/ready` SHALL answer 200 only while the text model server serves the configured model and the database holds the index built from the image's corpus and settings, and 503 with the reason otherwise.

#### Scenario: Text model server down
- **WHEN** the text model server does not respond
- **THEN** `/health/ready` answers 503 naming the server address, and `/health/live` answers 200.

#### Scenario: Stale index
- **WHEN** the index in the database was built from other documents or settings
- **THEN** `/health/ready` answers 503 with both index versions.

#### Scenario: Dependency fails during a request
- **WHEN** the text model server stops while a question is being answered
- **THEN** the service answers 503 with the reason and counts the request as an error.

### Requirement: Expose service metrics

`GET /metrics` SHALL expose, in the Prometheus text format, the count of `/ask` requests by outcome, their latency, the time spent in retrieval and in generation, and the prompt and completion tokens. Requests to the health and metrics endpoints SHALL NOT be counted.

#### Scenario: One answered question
- **WHEN** one question is answered
- **THEN** `/metrics` reports one request with outcome `ok`, one observation in each of the latency, retrieval and generation histograms, and token counters increased by the tokens the server reported.

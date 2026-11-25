# gis-assistant Specification

## Purpose

A GIS user can obtain a land-cover prediction and a sourced explanation of the resulting QGIS package through a single conversation.

## Requirements

### Requirement: Use the project retriever and prediction service

The assistant SHALL use the evaluated project retriever for documentation questions and the deployed prediction endpoint for segmentation requests. A completed combined request SHALL identify the actual model version, provide access to the caller's package and cite the retrieved source for its explanation. An answer that no retrieved passage supports SHALL say so and SHALL carry no source locator.

#### Scenario: Create a mask and explain its NoData value
- **WHEN** an authenticated user requests segmentation of their GeoTIFF and asks what 255 means
- **THEN** the assistant invokes prediction and retrieval and returns the completed package, its model version and a cited explanation distinguishing invalid pixels (255) from bareland (0).

#### Scenario: Answer a question about the legend
- **WHEN** a user asks only what a class means
- **THEN** the assistant answers from retrieved passages with a source locator and submits no prediction job.

#### Scenario: No retrieved passage states the answer
- **WHEN** a user asks a documentation question and none of the retrieved passages states the answer
- **THEN** the assistant says that the project documentation it retrieved does not support the answer, gives no source locator, and presents any answer it adds as general knowledge.

### Requirement: Respect asynchronous job state and ownership

The assistant SHALL track pending work under its original job ID, honor the caller's permissions and source expiry on resume, and report an unsuccessful outcome when the job fails or expires.

#### Scenario: Prediction is queued
- **WHEN** the prediction endpoint accepts a request and returns a queued job ID
- **THEN** the assistant exposes that pending state and follows the same job through completion without duplicate submission or repeated LLM calls for polling.

#### Scenario: Access is unavailable
- **WHEN** the requested job belongs to another user or has expired
- **THEN** the assistant denies access to its artifacts, including previously issued result references.

### Requirement: Bound agent actions and explain termination

The assistant SHALL allow only retrieval and prediction tools, refuse operator actions and stop with a reason on exhaustion of its declared step budget. A refused operation SHALL have no side effect.

#### Scenario: A user requests promotion
- **WHEN** a user asks the assistant to promote a model to champion
- **THEN** it refuses the operation and the registry alias stays on the approved version.

#### Scenario: A tool repeatedly fails
- **WHEN** retryable failures consume the tool-step budget
- **THEN** the assistant stops issuing calls and records budget exhaustion as the reason instead of reporting task success.

### Requirement: Preserve reviewable traces without extending image retention

Each run SHALL record ordered tool calls, redacted inputs and outputs, timing or tokens, cost and the final outcome. References to private imagery SHALL respect the source job's expiry.

#### Scenario: Review a local evaluation run
- **WHEN** a reviewer opens a completed run on public fixtures
- **THEN** they can inspect each tool's input and result, the stop reason and a cost calculated using the declared local shadow rate.

#### Scenario: Review a production trace after image expiry
- **WHEN** the source upload has expired
- **THEN** the retained trace provides redacted execution evidence without recoverable image content, coordinates, access tokens or usable artifact links.

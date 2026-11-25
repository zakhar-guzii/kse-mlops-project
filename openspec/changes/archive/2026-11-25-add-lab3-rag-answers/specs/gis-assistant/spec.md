# Spec Delta

## MODIFIED Requirements

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

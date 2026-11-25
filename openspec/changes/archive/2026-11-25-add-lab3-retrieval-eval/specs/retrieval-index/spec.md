# Spec Delta

## ADDED Requirements

### Requirement: Ranked retrieval
Given a question and a number k, the retriever SHALL return the k chunks of the index nearest to the question, nearest first, each with its `doc_id`, `doc_version`, locator, text and distance. The same question against the same index SHALL give the same chunks in the same order. The self-check of the index build SHALL use the same search.

#### Scenario: Passages for a question
- **WHEN** a question is retrieved with k = 5 from an index of more than five chunks
- **THEN** five chunks are returned in order of increasing distance, each with its `doc_id`, `doc_version`, locator, text and distance

#### Scenario: The same question twice
- **WHEN** the same question is retrieved twice from the same index
- **THEN** both results hold the same chunks in the same order

#### Scenario: A larger k
- **WHEN** a question is retrieved with k = 3 and again with k = 10
- **THEN** the three chunks of the first result are the first three of the second

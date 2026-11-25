# Spec Delta

## ADDED Requirements

### Requirement: Retrieval-augmented prompt file
The prompt for answers from retrieved passages SHALL be one committed file that holds the whole text sent to the model, with a named placeholder for the passages and one for the question, and SHALL be identified by a hash of its content like the other prompts. Each passage SHALL be given to the model with a number, its document identifier and its section locator.

#### Scenario: A placeholder is missing
- **WHEN** the retrieval-augmented prompt has no placeholder for the passages
- **THEN** the test suite fails and names the file and the placeholder

#### Scenario: Passages in the prompt
- **WHEN** a question is answered with three retrieved passages
- **THEN** the text sent to the model holds the three passages numbered 1 to 3 in order of increasing distance, each with its document identifier and locator, followed by the question

### Requirement: Retrieval-augmented answer run
One documented command given a value of top-k SHALL retrieve that many passages for every question of the evaluation set through the project's retriever, answer with the retrieval-augmented prompt, judge with the judge prompt of the baseline, and log one run to the experiment of the baseline. The run SHALL hold top-k, the retrieval settings, hit rate at k, MRR at k, the answer metric and, per question, the rank of the first relevant passage, the retrieved chunks, the answer and its verdict.

#### Scenario: A run at top-k 5
- **WHEN** the command is run with top-k 5, the stack and the text model server up and a current index
- **THEN** it exits zero, prints the hit rate, the MRR and the answer metric, and the tracking server shows a new run with top-k 5, both retrieval metrics, the answer metric and the per-question records

#### Scenario: The same retrieval as the retrieval evaluation
- **WHEN** an answer run and a retrieval evaluation run use the same index, question set and top-k
- **THEN** both runs show the same hit rate and the same MRR

#### Scenario: No top-k given
- **WHEN** the command is run without a value of top-k
- **THEN** it answers with the plain prompt and no passage and logs a run with top-k 0, as before

### Requirement: A retrieval-augmented run identifies its index
Every retrieval-augmented answer run SHALL carry the index version it read, beside the lineage every answer run carries, and its answer prompt hash SHALL be that of the retrieval-augmented prompt. The command SHALL exit non-zero and log nothing when the index in the database was not built from the committed corpus and configuration.

#### Scenario: A stale index
- **WHEN** the chunk size in the configuration differs from the one the index was built with
- **THEN** the command exits non-zero, names the command that rebuilds the index, and no run is created

#### Scenario: Lineage of a run
- **WHEN** a retrieval-augmented run is logged
- **THEN** it shows the index version, the code commit, the evaluation set identifier and the hashes of the retrieval-augmented prompt and of the judge prompt

### Requirement: Answers disclose their support
The retrieval-augmented prompt SHALL tell the model to name the numbers of the passages that state its answer, and to say that no passage supports the answer when it answers from its own knowledge. A run SHALL record, per question, the passage numbers the answer names, and SHALL record how many answers name at least one retrieved passage.

#### Scenario: An answer from a passage
- **WHEN** an answer names passage 2 of five retrieved passages
- **THEN** the record of that question holds the number 2 and the answer counts as naming a passage

#### Scenario: An answer from the model's own knowledge
- **WHEN** an answer names no passage
- **THEN** the record of that question holds no number and the answer does not count as naming a passage

#### Scenario: A number that was not retrieved
- **WHEN** an answer names passage 7 of five retrieved passages
- **THEN** the record holds the number 7, and the answer does not count as naming a passage

### Requirement: Latency of a retrieval-augmented answer includes retrieval
The latency of a question in a retrieval-augmented run SHALL be the seconds its retrieval took plus the seconds of its answer call, and the p50 and p95 of the run SHALL be taken over these sums. The run SHALL also record the retrieval seconds apart.

#### Scenario: Retrieval is part of the latency
- **WHEN** every question takes 0.5 seconds to retrieve and 2.0 seconds to answer
- **THEN** the run records a p50 latency of 2.5 seconds and 0.5 seconds of retrieval per question

### Requirement: Top-k compared at three values and chosen by a stated rule
The README and Section 7.2 of the design document SHALL table three retrieval-augmented runs that differ only in top-k beside the baseline, with top-k, hit rate, MRR, the answer metric, tokens, shadow cost, latency and run identifier. The top-k of the configuration file SHALL be the smallest of the three values whose answer metric is no more than two questions below the best of the three, and the README SHALL state this rule and the chosen value.

#### Scenario: A larger k gains one question
- **WHEN** the answer metric is 20, 24 and 25 of 32 at top-k 3, 5 and 10
- **THEN** the chosen top-k is 5

#### Scenario: The configuration holds the choice
- **WHEN** a reviewer reads the configuration file after the choice
- **THEN** its top-k equals the value the README names as chosen

#### Scenario: A reviewer checks a row
- **WHEN** a reviewer opens a run named in the table
- **THEN** the run's top-k, hit rate, MRR, answer metric, tokens, cost and latency equal the row

### Requirement: The judge is checked on a retrieval-augmented run
The repository SHALL hold, for one retrieval-augmented run, every answer with the judge's verdict and a label assigned by the same rubric without sight of that run's verdicts and reviewed by the author. The README SHALL give the counts of the four combinations of verdict and label for that run, the run they come from, and who assigned and who reviewed the labels.

#### Scenario: The second table is checked
- **WHEN** the counts in the README for the retrieval-augmented run differ from the counts computed from its committed labels
- **THEN** the test suite fails

#### Scenario: A question has no label
- **WHEN** a question of the evaluation set is absent from the labels of the retrieval-augmented run
- **THEN** the test suite fails and names the question

#### Scenario: The second labels file is missing
- **WHEN** the labels file of the retrieval-augmented run is deleted
- **THEN** the test suite fails rather than skipping the check

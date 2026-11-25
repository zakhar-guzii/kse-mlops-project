# Spec Delta

## Purpose

Measures whether the retrieval index returns the passage that answers a question, on a committed question set that can be rerun after every change, and records each measurement as a tracked run that names the index, the questions and the code it used.

## ADDED Requirements

### Requirement: Committed evaluation set
The repository SHALL hold one evaluation set of at least 30 questions in English. Every question SHALL have an identifier unique in the set, one or more sources and a reference answer in English. A source SHALL name a document of the corpus, a section of that document and an evidence quote from that section. Every document of the corpus SHALL be a source of at least three questions.

#### Scenario: Clean clone holds the set
- **WHEN** the repository is cloned
- **THEN** the evaluation set is available with at least 30 questions, each with a source and a reference answer

#### Scenario: A document has too few questions
- **WHEN** fewer than three questions name a document of the corpus as a source
- **THEN** the project's test suite fails and names the document

### Requirement: Sources resolve against the corpus
Every source SHALL name a section that exists in the corpus when it is chunked with the committed configuration, and its evidence quote SHALL be contained whole in at least one chunk of that section. The project's test suite SHALL check this without an embedding model and without a database.

#### Scenario: A cited section no longer exists
- **WHEN** a source names a section that the chunked corpus does not contain
- **THEN** the test suite fails and names the question

#### Scenario: An evidence quote is not in its section
- **WHEN** no chunk of the named section contains the evidence quote
- **THEN** the test suite fails and names the question

### Requirement: Questions do not quote their sources
A question SHALL NOT contain a name of a document it points at and SHALL NOT share four consecutive words with a chunk that is relevant to it. The project's test suite SHALL check both.

#### Scenario: A question names its document
- **WHEN** a question whose source is the QGIS document contains the word QGIS
- **THEN** the test suite fails and names the question

#### Scenario: A question repeats the passage
- **WHEN** a question shares four consecutive words with a chunk that holds its evidence quote
- **THEN** the test suite fails and names the question

### Requirement: Relevant chunk
A retrieved chunk SHALL count as relevant to a question only when it belongs to the document and section of one of the question's sources and contains that source's evidence quote.

#### Scenario: Right section, wrong passage
- **WHEN** a retrieved chunk lies in a cited section and does not contain the evidence quote
- **THEN** it is not relevant

#### Scenario: Right passage
- **WHEN** a retrieved chunk lies in a cited section and contains that source's evidence quote
- **THEN** it is relevant

#### Scenario: Another document on the same topic
- **WHEN** a retrieved chunk of a document that no source names discusses the same topic
- **THEN** it is not relevant

### Requirement: Hit rate and mean reciprocal rank at k
For a value k, the hit rate SHALL be the share of questions with at least one relevant chunk among the first k retrieved chunks. The mean reciprocal rank SHALL be the mean over all questions of one divided by the rank of the first relevant chunk among the first k, and zero for a question that has none there.

#### Scenario: Three questions at k = 5
- **WHEN** the first relevant chunks of three questions are at rank 1, at rank 3 and absent from the first 5
- **THEN** the hit rate is 0.667 and the mean reciprocal rank is 0.444

#### Scenario: A relevant chunk beyond k
- **WHEN** the first relevant chunk of a question is at rank 4 and k is 3
- **THEN** the question is a miss and adds zero to the mean reciprocal rank

### Requirement: One-command evaluation logged as a run
One documented command SHALL send every question of the set through the project's retriever at the configured top-k, print the hit rate and the mean reciprocal rank, and log one run to the project's tracking server. The run SHALL hold top-k, the index settings, the number of questions, both metrics and, per question, the rank of the first relevant chunk and the retrieved chunks. The command SHALL accept another top-k for one run without a change to the configuration file.

#### Scenario: Evaluation on the running stack
- **WHEN** the command is run with the local stack up and a current index
- **THEN** it exits zero, prints both metrics, and the tracking server shows a new run with the parameters, both metrics and the per-question results

#### Scenario: Another top-k for one run
- **WHEN** the command is run with a top-k other than the configured one
- **THEN** the run records that top-k and the configuration file is unchanged

### Requirement: top-k of a run is at least 1
The evaluation command SHALL refuse a top-k below 1, whether it comes from the command line or from the configuration file.

#### Scenario: A top-k of zero
- **WHEN** the command is run with top-k 0
- **THEN** it exits non-zero and no run is created

### Requirement: Seconds of a retrieval run
Every evaluation run SHALL record the seconds its searches took in total, each including the embedding of the question, and the p50 and p95 of the seconds per question.

#### Scenario: Seconds of a run
- **WHEN** a run is logged
- **THEN** it shows the total seconds of its searches and the p50 and p95 seconds per question

### Requirement: A run identifies what it evaluated
Every evaluation run SHALL carry the code commit, read when the working tree was found clean before any question was sent, the index version and an identifier of the evaluation set derived from its content. The command SHALL exit non-zero and log nothing when the working tree has uncommitted changes, or when the index in the database was not built from the committed corpus and configuration.

#### Scenario: Uncommitted changes
- **WHEN** the command is run with an uncommitted change to the evaluation set
- **THEN** it exits non-zero and no run is created

#### Scenario: Stale index
- **WHEN** the chunk size in the configuration file differs from the one the index was built with
- **THEN** the command exits non-zero, says that the index has to be rebuilt, and no run is created

#### Scenario: No index yet
- **WHEN** the command is run against a database that has never held the index
- **THEN** it exits non-zero, names the command that builds the index, and no run is created

#### Scenario: A commit during the run
- **WHEN** a commit is made while the command is running
- **THEN** the run carries the commit that was checked out when the command started

#### Scenario: The set is edited
- **WHEN** a question is changed and committed, and the command is run again
- **THEN** the new run carries a different evaluation set identifier than the earlier run

### Requirement: Reported comparison of top-k
The README SHALL give, for at least three values of top-k, the hit rate, the mean reciprocal rank and the identifier of the run that measured them, with the index version and the evaluation set identifier. It SHALL state how the questions were produced and that the author read them.

#### Scenario: A reviewer checks a row
- **WHEN** a reviewer opens the run named in a row of the table
- **THEN** the run's top-k and both metrics equal the row

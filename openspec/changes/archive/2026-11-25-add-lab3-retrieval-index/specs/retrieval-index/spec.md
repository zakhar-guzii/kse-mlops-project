# Spec Delta

## Purpose

Gives the GIS assistant a searchable index of the project's documentation that any reader of the repository can rebuild with one command, and that states which documents, settings and versions it was built from.

## ADDED Requirements

### Requirement: Committed corpus with a manifest
The corpus SHALL consist of five documents with the identifiers `oem-paper`, `flair-hub`, `naip-dictionary`, `qgis-raster` and `export-contract`. The four external documents SHALL be saved copies committed to the repository, and a committed manifest SHALL record for each copy its source URLs, access date and SHA-256. Building the index SHALL need no access to the sources.

#### Scenario: Clean clone holds the corpus
- **WHEN** the repository is cloned and the sources are unreachable
- **THEN** every document of the corpus is available to the index build

#### Scenario: A saved copy was edited
- **WHEN** a saved copy no longer hashes to the SHA-256 in the manifest
- **THEN** the index build exits non-zero, names the document and leaves the existing index unchanged

### Requirement: Export contract read from the design document
The document `export-contract` SHALL be the text of Sections 5.1 and 6.8 of the design document as committed when the index is built. It SHALL have no saved copy.

#### Scenario: The design section changes
- **WHEN** Section 5.1 of the design document is edited and the index is rebuilt
- **THEN** the chunks of `export-contract` contain the edited text and the other documents' chunks are the same as before

#### Scenario: A section is missing
- **WHEN** the design document has no Section 5.1 or no Section 6.8
- **THEN** the index build exits non-zero and names the missing section

### Requirement: Document version derived from content
Every document SHALL have a `doc_version` derived from the content that is indexed, so that the same content always has the same version and changed content always has a different one.

#### Scenario: Unchanged document
- **WHEN** the index is built twice from the same commit
- **THEN** every document has the same `doc_version` in both builds

#### Scenario: Changed document
- **WHEN** the content of one document changes between two builds
- **THEN** only that document's `doc_version` changes

### Requirement: Section-bounded chunks
Every document SHALL be split into chunks that each lie within one section of the document. No chunk SHALL be longer than the configured chunk size, consecutive chunks of one section SHALL share the configured overlap, and every part of the section's text SHALL appear in at least one chunk. Every chunk SHALL carry its `doc_id`, `doc_version` and a locator naming its section.

#### Scenario: A section longer than the chunk size
- **WHEN** a section is longer than the configured chunk size
- **THEN** it yields several chunks with the same locator, none longer than the chunk size, each sharing the overlap with the previous one

#### Scenario: Two short neighbouring sections
- **WHEN** two neighbouring sections together fit within the chunk size
- **THEN** they yield separate chunks with different locators

#### Scenario: Locator of a contract chunk
- **WHEN** a chunk holds text from the class table of the design document
- **THEN** its `doc_id` is `export-contract` and its locator names Section 5.1

### Requirement: Single retrieval configuration
The chunk size, the overlap, the embedding model with its pinned revision, and top-k SHALL be read from one committed configuration file. No other file SHALL hold a second copy of any of these values. A configuration whose overlap is negative or not shorter than the chunk size, or whose top-k is below 1, SHALL be refused before any chunk is made.

#### Scenario: Chunk size is changed
- **WHEN** the chunk size in the configuration file is changed and the index is rebuilt
- **THEN** the chunks follow the new size without any other file being edited

#### Scenario: Overlap as long as the chunk
- **WHEN** the overlap in the configuration file equals the chunk size
- **THEN** the index build exits non-zero, names both settings and leaves the existing index unchanged

### Requirement: One-command rebuild that prints the counts
One documented command SHALL replace the whole index from the corpus and print the number of documents and the number of chunks. The README SHALL state the number of documents. The command SHALL work against a database that has never held the index, including one created before vector support was installed.

#### Scenario: Rebuild on the running stack
- **WHEN** the command is run with the local stack up
- **THEN** it exits zero and prints 5 documents and the chunk count, and the README states the same number of documents

#### Scenario: Rebuild twice
- **WHEN** the command is run twice from the same commit
- **THEN** both runs print the same counts and the index holds one set of chunks

#### Scenario: A build fails part-way
- **WHEN** the command fails after an index already exists
- **THEN** the earlier index is still complete and still reports its own version

### Requirement: Index states its version
The index SHALL record an index version derived from the documents' versions, from the settings that determine its content: the chunk size, the overlap and the embedding model with its revision, and from a version of the build format: the chunking and the text given to the embedding model. The index SHALL also record those settings and its counts, and the rebuild command SHALL print the index version.

#### Scenario: A setting that shapes the index changes
- **WHEN** the chunk size, the overlap, the embedding model or its revision changes and the index is rebuilt
- **THEN** the index version changes

#### Scenario: The build format changes
- **WHEN** the code changes how documents are chunked or what text is embedded, and its build format version is raised
- **THEN** the index version changes and an index built by the earlier code is reported as stale

#### Scenario: Only top-k changes
- **WHEN** top-k changes and the index is rebuilt
- **THEN** the index version is the same as before

### Requirement: Self-check of the built index
The rebuild command SHALL query the new index with one fixed question about the meaning of the value 255 and SHALL exit non-zero unless a chunk of `export-contract` from Section 5.1 is among the configured top-k results. It SHALL print the best result's document, locator and distance.

#### Scenario: The index answers the fixed question
- **WHEN** the index is built from the committed corpus with the committed configuration
- **THEN** the command prints a best result and exits zero

#### Scenario: The index cannot answer it
- **WHEN** no chunk of Section 5.1 is among the top-k results for the fixed question
- **THEN** the command exits non-zero and reports which results it found

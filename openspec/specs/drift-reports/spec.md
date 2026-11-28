# drift-reports Specification

## Purpose

Lets the operator see, every few minutes, how the images the ML service served in the last window differ from what its model was trained on: per input feature, per predicted class and, where labels exist, in measured quality.

## Requirements

### Requirement: Training reference produced by the serving path

The reference of a model version SHALL be the request-log rows produced when the ML service serving that version predicted the 256×256 quadrants of the training batches. Each reference row SHALL carry a source ID that marks it as reference and names the data version, batch, tile and quadrant. Reference rows SHALL NOT count toward any current window.

#### Scenario: Reference for the served version
- **WHEN** the reference command runs against a service serving a version without a reference
- **THEN** the request log gains one `ok` row per training quadrant for that version, each with a reference source ID.

#### Scenario: Reference already present
- **WHEN** the reference command runs again for a version that already has its reference
- **THEN** it sends no request and reports that the reference exists.

### Requirement: Labels only for development quadrants

The labels command SHALL store the crosswalked reference mask of each development-batch quadrant, keyed by the source ID the replay sends for it. It SHALL NOT read the final batch's masks. Loading the labels again SHALL leave one label per quadrant.

#### Scenario: Labels loaded twice
- **WHEN** the labels command runs twice
- **THEN** the label table holds 64 rows, one per development quadrant, and no final-batch quadrant has a label.

### Requirement: Replay held-out quadrants through the service

The replay command SHALL send each 256×256 quadrant of the development and final batches to the prediction endpoint with a source ID naming batch, tile and quadrant. It SHALL wait for the next window boundary before the first request, so that one replay falls within one window, and SHALL report the number of requests that succeeded.

#### Scenario: One replay, one window
- **WHEN** the replay finishes
- **THEN** 128 `ok` rows with replay source IDs carry `received_at` values within a single report window.

### Requirement: Scheduled report over fixed windows

A scheduled job SHALL report every 5 minutes on the window of the 5 minutes that end at its start time, rounded down to a multiple of 5 minutes. Windows SHALL NOT overlap. A run SHALL NOT start while the previous one is still running. The window length SHALL be configuration.

#### Scenario: Requests at the window edges
- **WHEN** a request is received at 12:04:59 and another at 12:05:00, and the job starts at 12:10:20
- **THEN** that run's window holds only the second request, and the first belongs to the run that started at 12:05.

### Requirement: Input and prediction drift per column

For each model version, the report SHALL compare the window's `ok` non-reference rows with that version's reference rows over ten columns: the red, green and blue means, brightness, and the shares of the six classes the labels can score. Per column it SHALL give a normed Wasserstein distance; it SHALL also give how many columns exceed the threshold and what share of columns that is.

#### Scenario: Unchanged held-out replay
- **WHEN** the window holds one unchanged replay served by a version with a reference
- **THEN** the report gives a distance for each of the ten columns, the drifted-column count and share, the threshold, and the sample sizes of both sides.

#### Scenario: Same population twice
- **WHEN** two windows each hold the same unchanged replay served by the same version
- **THEN** both reports give the same distances.

### Requirement: One report per model version

The report SHALL evaluate each model version seen in the window, and the version of the latest served non-reference request, separately against that version's own reference.

#### Scenario: Two versions in one window
- **WHEN** a window holds requests served by versions 2 and 3
- **THEN** the report has separate results for version 2 and version 3, each against its own reference.

### Requirement: Insufficient data instead of a score

When either side of a comparison has fewer than 50 observations, or a version has no reference, the report SHALL give `insufficient_data` with the reason (`few_observations` or `no_reference`) and the sample sizes, and SHALL give no distance for that version.

#### Scenario: Empty window
- **WHEN** no request was served in the window
- **THEN** the report gives `insufficient_data` with reason `few_observations` and a current sample size of 0 for the version of the latest served request.

#### Scenario: Version without a reference
- **WHEN** a version was promoted and served but the reference command has not run for it
- **THEN** its report gives `insufficient_data` with reason `no_reference`.

### Requirement: Quality on labelled rows

For each version, the report SHALL compute per-class IoU and their mean over the window's `ok` rows that have a label, using the Lab 2 definition (ignored pixels excluded, six scored classes). With fewer than 50 labelled rows, or a scored class absent from the labels, it SHALL give `insufficient_data` for quality with the reason.

#### Scenario: Replay with development labels loaded
- **WHEN** the window holds one replay and the development labels are loaded
- **THEN** the report gives mean IoU over the 64 labelled rows; the final-batch rows count as unlabelled.

#### Scenario: Labels not loaded
- **WHEN** no label matches a row of the window
- **THEN** quality gives `insufficient_data` with reason `few_observations` and 0 labelled rows.

### Requirement: Freshness separate from job success

Every report SHALL include the receive time of the latest served non-reference request and the end of its window, so that the age of the data can be checked independently of whether the job ran.

#### Scenario: Job runs, service writes nothing
- **WHEN** the job succeeds for several windows while no request is served
- **THEN** each report's job time advances while the latest-request time stays where it was.

### Requirement: Report published to the metrics store

Each run SHALL publish its report to the Pushgateway, replacing everything the previous run published. A version or column absent from the current report SHALL no longer be published. A failed publication SHALL make the run fail.

#### Scenario: Version leaves the traffic
- **WHEN** version 2 appeared in one report and the next report covers only version 3
- **THEN** after the second run the Pushgateway holds no series for version 2.

#### Scenario: Pushgateway unreachable
- **WHEN** the Pushgateway does not answer
- **THEN** the job exits non-zero and its Kubernetes Job is marked failed.

### Requirement: Shifted replay through the service

The replay command SHALL be able to darken a recorded fraction of the held-out quadrants by a recorded factor on the red, green and blue bands before sending them to the prediction endpoint, leaving each pixel's validity unchanged. A fixed seed SHALL choose the same quadrants on every run. Darkened quadrants SHALL carry a source ID that marks them as shifted.

#### Scenario: Documented shift
- **WHEN** the replay runs with factor 0.5, fraction 0.5 and seed 0
- **THEN** 64 of the 128 held-out quadrants are sent darkened with `shift/…` source IDs, the other 64 with `replay/…` IDs, all 128 are `ok` within one window, and the command prints the factor, fraction, seed and window.

#### Scenario: Same seed twice
- **WHEN** the shifted replay runs twice with the same factor, fraction and seed
- **THEN** both runs darken the same quadrants and their windows' reports give the same distances.

#### Scenario: Validity preserved
- **WHEN** a quadrant is darkened
- **THEN** the service counts the same valid pixels for it as for the unchanged quadrant.

### Requirement: Baseline window before the shifted window

One documented command SHALL send an unchanged replay into one window and the shifted replay into the next window, so that consecutive reports show the baseline and the shift.

#### Scenario: Drift demonstration
- **WHEN** the demonstration command finishes
- **THEN** two consecutive windows hold 128 `ok` rows each; the first has only `replay/…` IDs and the second has the shifted mix, and their reports give a brightness distance below and at or above the threshold respectively.

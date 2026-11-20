# segmentation-monitoring Specification

## Purpose

Operators and GIS users can distinguish unusable uploads, unusual individual images and population shifts from measured changes in model quality.

## Requirements

### Requirement: Distinguish invalid input from a valid image anomaly

The service SHALL reject unusable imagery with a reason and SHALL attach a QA warning to valid imagery that crosses the per-image anomaly threshold. Invalid images SHALL be counted separately from the input drift population.

#### Scenario: No usable pixels
- **WHEN** the worker cannot decode the upload or finds no valid pixels
- **THEN** the job fails with its reason and produces neither a mask nor an image observation for drift.

#### Scenario: One unusually dark image
- **WHEN** a decodable RGB image with valid pixels falls below the configured training-reference brightness percentile
- **THEN** the service processes the image, exposes the warning with the result and includes its observation in the current input window.

### Requirement: Compare serving traffic with a versioned training reference

Scheduled reports SHALL compare statistics from actual prediction traffic against frozen training-reference statistics using the same features and observation unit. Prediction drift SHALL compare class fractions produced by the same model and taxonomy. A window with insufficient eligible observations SHALL report insufficient data.

#### Scenario: Serving distribution shifts
- **WHEN** an eligible current window crosses a configured input-feature or predicted-class threshold
- **THEN** the report identifies the signal, value, threshold, sample sizes, window, model version and reference version.

#### Scenario: Model rollout or low traffic
- **WHEN** two model versions serve during one window and one version lacks enough observations
- **THEN** the report evaluates each against its matching reference and reports insufficient data for the undersampled version.

### Requirement: Route statistical alerts to the operator

A detected population drift SHALL notify the operator through the designated human channel. Only evaluation with reference masks SHALL substantiate a claim of accuracy loss. Model promotion and rollback SHALL remain operator decisions.

#### Scenario: Inject an input shift through the prediction endpoint
- **WHEN** the service processes original held-out fixtures and then a documented shifted population that crosses the detector threshold
- **THEN** the scheduled reports and dashboard show both windows, the operator receives an email identifying the shift, and the active model continues serving pending review.

#### Scenario: No labels for a shifted population
- **WHEN** the operator reviews a drift report for unlabelled user uploads
- **THEN** the report describes the distribution change and the operator can request labelled evaluation before drawing a conclusion about IoU.

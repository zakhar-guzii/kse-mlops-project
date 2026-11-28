# drift-alerting Specification

## Purpose

Turns the scheduled drift report and the service signals into alerts that reach the operator's mailbox, so that a shift in served images, stale data or a broken service is noticed by a person without anyone watching the dashboard.

## Requirements

### Requirement: Brightness drift alert

An alert SHALL fire for a model version when its report's brightness distance is at or above the drift threshold the report publishes. The alert SHALL NOT depend on the class-share columns or on the share of drifted columns. A version with `insufficient_data` SHALL NOT fire it.

#### Scenario: Shifted window
- **WHEN** a window holds the documented shifted replay and its report gives a brightness distance of at least the threshold
- **THEN** the brightness drift alert fires for that model version, naming the column, the distance, the threshold and the window end.

#### Scenario: Unchanged held-out window
- **WHEN** a window holds the unchanged held-out replay
- **THEN** the brightness drift alert does not fire, even though class-share columns exceed the threshold.

#### Scenario: Next window without the shift
- **WHEN** the report after the shifted window no longer gives a brightness distance at or above the threshold
- **THEN** the alert stops firing without manual action.

### Requirement: One threshold value

The threshold the alert compares with SHALL be the value the drift report publishes, set in one place of the cluster configuration. Changing that value SHALL change the drifted-column count, the dashboard line and the alert together.

#### Scenario: Threshold changed
- **WHEN** the configured threshold is changed and the next report runs
- **THEN** the published threshold, the dashboard's threshold line and the alert's comparison all use the new value.

### Requirement: Freshness alerts on data and on the job

An alert SHALL fire when no non-reference request has been served for 1 hour while the report job keeps publishing. A separate alert SHALL fire when no report has been published for 15 minutes, including when the metrics of the report are absent.

#### Scenario: Job succeeds, nothing served
- **WHEN** the report job publishes every 5 minutes and the latest served request is more than 1 hour old
- **THEN** the data freshness alert fires and the job alert does not.

#### Scenario: Report job stops
- **WHEN** no report has been published for 15 minutes
- **THEN** the job alert fires.

### Requirement: Service health alerts

An alert SHALL fire when the ML service has had no instance able to serve, for example because its model is not loaded, for 5 minutes. An alert SHALL fire when the prediction endpoint has answered with an error 3 or more times within 1 hour. Invalid inputs SHALL NOT count as errors.

#### Scenario: Alias missing
- **WHEN** the ML service cannot load the model its alias names for 5 minutes
- **THEN** the service alert fires.

#### Scenario: Restart after a promotion
- **WHEN** the ML Deployment is restarted and the old instance serves until the new one is ready
- **THEN** the service alert does not fire.

#### Scenario: Invalid uploads
- **WHEN** the prediction endpoint rejects several invalid images within an hour and serves no error
- **THEN** the error alert does not fire.

### Requirement: Alerts delivered to the operator's mailbox

Every firing alert SHALL be sent as an email to the operator's mailbox inside the cluster. Delivery SHALL need no secret, external account or manual step beyond the bring-up command. The email SHALL name the alert, the model version where it has one, and the value that triggered it. A firing alert SHALL be sent once and repeated no more often than every 4 hours.

#### Scenario: Shift reaches the operator
- **WHEN** the brightness drift alert fires after the shifted replay
- **THEN** within 10 minutes of the start of the shifted window the mailbox holds an email naming the alert, the model version, the distance and the threshold, and the ML service keeps serving the same model version.

#### Scenario: Clean clone
- **WHEN** a reviewer runs the bring-up command on a clean clone without any mail credentials
- **THEN** the alert path and the mailbox are deployed and ready.

### Requirement: Alerts never change the served model

No alert SHALL start training, change a registry alias or restart a service. Promotion and rollback SHALL remain the operator's commands.

#### Scenario: Drift alert fires
- **WHEN** the brightness drift alert fires
- **THEN** the registry aliases and the ML service's model version are the same as before the alert.

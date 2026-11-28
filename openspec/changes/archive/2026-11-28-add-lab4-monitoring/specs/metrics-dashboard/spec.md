# Spec Delta

## Purpose

Collects the service metrics and the drift reports of the course cluster in one metrics store and shows them on one dashboard. The dashboard is defined in the repository, so a reviewer gets the same panels from a clean clone.

## ADDED Requirements

### Requirement: Metrics store in the cluster

The cluster SHALL run a metrics store and a push gateway. The store SHALL scrape the `/metrics` endpoints of the ML and LLM services and the push gateway. Labels pushed by the job SHALL be kept as pushed, not replaced by the gateway's own target labels.

#### Scenario: Targets up
- **WHEN** the cluster is up and the ML service is ready
- **THEN** the store lists the ML service and the push gateway as healthy targets, and the job's metrics carry the model version the job pushed.

#### Scenario: LLM service not ready
- **WHEN** no text-model server runs on the host
- **THEN** the LLM target is reported down while the other targets stay healthy.

### Requirement: Dashboard provisioned from the repository

The dashboard tool SHALL start with its data source and the course dashboard loaded from files in the repository, without manual set-up. Viewing it SHALL need no login. A change to the dashboard SHALL be made in the repository file, not only in the browser.

#### Scenario: Fresh cluster
- **WHEN** the dashboard tool starts in a new cluster
- **THEN** the course dashboard is listed and its panels query the metrics store without an edit.

### Requirement: Dashboard shows service and drift signals

The dashboard SHALL show for the ML service the request rate by outcome, p95 latency and errors. It SHALL also show:

- the drift distance per column with the threshold;
- the drifted-column share;
- observations per side and `insufficient_data` per version;
- mean IoU with the labelled count;
- the age of the latest served request.

#### Scenario: Two windows
- **WHEN** two windows of the same unchanged replay are separated by one empty window
- **THEN** the drift panel shows two equal segments with a gap between them, the `insufficient_data` panel marks the empty window, and the request panels show two bursts.

### Requirement: Monitoring fits next to the services

The monitoring components SHALL declare memory requests and limits. With them, the services, the tracking server and the database SHALL all be ready within the cluster's default memory. The README SHALL record the measured peak memory of each monitoring pod.

#### Scenario: Everything ready
- **WHEN** the cluster runs with its default memory and the ML service has served a 1024×1024 image
- **THEN** no pod has been killed for memory, and pods and services, including the monitoring components, are listed as ready.

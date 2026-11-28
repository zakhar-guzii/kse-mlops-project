# cluster-deployment Specification

## Purpose

Runs the course system on a local Kubernetes cluster: both services, the tracking server and the database. Configuration and secrets come from cluster objects, health contracts gate traffic, and promotion is a registry operation followed by a restart.

## Requirements

### Requirement: Services, tracking server and database in the cluster

The ML service, the LLM service, the tracking server and the PostgreSQL database SHALL each run in the cluster as a Deployment with a Service. They SHALL reach one another by cluster DNS names. The cluster SHALL NOT depend on the Compose stack. The text model SHALL stay outside the cluster.

#### Scenario: Components listed
- **WHEN** the operator lists pods and services after bring-up
- **THEN** each of the four components shows a running pod and a Service, and the Compose stack need not be running.

#### Scenario: Registry by cluster DNS
- **WHEN** the ML service resolves its alias
- **THEN** it calls the tracking server through the Service's cluster DNS name, not a host address.

### Requirement: Tracking server storage and access

The tracking server SHALL keep run metadata in the cluster's PostgreSQL. It SHALL proxy model files to a persistent volume, so that clients need only its address. It SHALL accept requests addressed to its Service name and to the documented local port-forward, and SHALL refuse other host names. It SHALL NOT be exposed outside the cluster except through a port-forward bound to `127.0.0.1`.

#### Scenario: Registry survives a restart
- **WHEN** the tracking server's pod is deleted and recreated
- **THEN** the registered versions, the alias and the model files registered earlier are still available.

#### Scenario: Unknown host name
- **WHEN** a request reaches the tracking server with a host name outside its allowed list
- **THEN** the server refuses it.

### Requirement: Configuration from a ConfigMap and secrets from a Secret

The tracking address, the registered model name, the alias and the text-model address SHALL come from a ConfigMap. The database credentials and every connection string that contains them SHALL come from a Secret built from the untracked environment file. No credential SHALL appear in a committed manifest, a ConfigMap or an image.

#### Scenario: Alias from the ConfigMap
- **WHEN** the operator inspects the ML service's environment sources
- **THEN** the alias and the tracking address come from the ConfigMap, and the database connection string comes from the Secret.

#### Scenario: No credential in the repository
- **WHEN** a reviewer searches the committed manifests for the database password from `.env`
- **THEN** it is not found.

### Requirement: Probes on the health contract

Each service's readiness probe SHALL call `/health/ready`, and its liveness probe SHALL call `/health/live`. A service whose start-up blocks before it answers HTTP SHALL have a startup probe whose budget covers the measured start-up. The tracking server and the database SHALL have readiness probes.

#### Scenario: Slow start is not killed
- **WHEN** the LLM service takes longer to load its embedding model than one liveness period
- **THEN** the container is not restarted, and liveness and readiness begin after the startup probe succeeds.

#### Scenario: Failing dependency does not restart
- **WHEN** a service's readiness fails because a dependency is down
- **THEN** the pod stays running, is removed from its Service's endpoints and is not restarted.

### Requirement: Missing model keeps the ML pod out of service

An ML pod whose alias cannot be loaded SHALL stay running and not ready. It SHALL receive no traffic through its Service until the model loads. The README SHALL contain the saved output that shows this in the cluster.

#### Scenario: Alias absent
- **WHEN** the ML Deployment is started with an alias the registry does not have
- **THEN** its new pod shows 0/1 ready, its events name the 503 readiness failure, its address is absent from the Service's Endpoints and marked not ready in its EndpointSlice, and the previous pod keeps serving.

#### Scenario: Model appears
- **WHEN** the alias is then created in the registry
- **THEN** the same pod becomes ready without a restart.

### Requirement: Promotion is the alias and a restart

The ML Deployment SHALL name its image by the commit tag. A promotion SHALL consist of moving `champion` in the registry and restarting the Deployment. After the restart, the prediction endpoint SHALL report the newly promoted version while the Deployment still names the same image.

#### Scenario: New version after restart
- **WHEN** the operator points `champion` at another version and restarts the ML Deployment
- **THEN** the next prediction reports that version, and the Deployment's image tag is unchanged.

### Requirement: Retrieval index built in the cluster

The cluster's database SHALL hold the retrieval index that the LLM image's corpus, settings and embedding model produce. It SHALL be built by a workload in the cluster that uses that image, without a host-side embedding model or network download.

#### Scenario: Index matches the image
- **WHEN** the index workload has completed
- **THEN** the LLM service's readiness check finds the index version it expects.

#### Scenario: Same commit, no rebuild
- **WHEN** bring-up runs again at the same commit
- **THEN** the index workload is not run again.

### Requirement: Text model reached on the host

The LLM service SHALL call the host's text-model server through the cluster's host alias at the port of `make llm-server`, without the server listening beyond `127.0.0.1`.

#### Scenario: Host server up
- **WHEN** `make llm-server` is running on the host and the index is built
- **THEN** the LLM service becomes ready and answers a question with cited sources.

#### Scenario: Host server down
- **WHEN** the host server is not running
- **THEN** the LLM service stays not ready and its readiness reason names the text-model address.

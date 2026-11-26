# Spec Delta

## ADDED Requirements

### Requirement: Alerting deployed with the system

The bring-up command SHALL deploy the alert router and the operator's mailbox together with the monitoring components, load the alert rules into the metrics store, and wait until the router and the mailbox are ready. At the end it SHALL print the local address of the mailbox with the command that opens it.

#### Scenario: Clean clone with alerting
- **WHEN** a reviewer runs the bring-up command on a clean clone
- **THEN** it exits 0, the metrics store lists the alert rules and the alert router as its target, and the mailbox opens at the printed address.

#### Scenario: Repeated bring-up with alerting
- **WHEN** the command runs a second time on the same commit
- **THEN** it changes nothing in the alerting components and the mailbox keeps the emails it already holds.

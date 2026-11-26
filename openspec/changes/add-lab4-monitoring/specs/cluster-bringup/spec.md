# Spec Delta

## ADDED Requirements

### Requirement: Monitoring deployed with the system

The bring-up command SHALL deploy the metrics store, the push gateway, the dashboard tool and the scheduled report job together with the services. It SHALL wait until the metrics store and the dashboard tool are ready. At the end it SHALL print the local addresses of the dashboard and the metrics store with the commands that open them.

#### Scenario: Clean clone with monitoring
- **WHEN** a reviewer runs the bring-up command on a clean clone
- **THEN** it exits 0, the report job is scheduled, and the dashboard opens at the printed address.

### Requirement: Reference and labels on bring-up

After the smoke request, the bring-up command SHALL build the reference for the version the ML service serves and load the development labels. Both steps SHALL be skipped or leave the same rows when repeated.

#### Scenario: Repeated bring-up
- **WHEN** the command runs a second time on the same commit with the same champion
- **THEN** no reference request is sent, and the label table still holds 64 rows.

#### Scenario: New champion
- **WHEN** the command runs after a promotion and a restart of the ML service
- **THEN** it builds the reference for the new version and leaves the old version's reference rows in place.

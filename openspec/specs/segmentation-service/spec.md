# segmentation-service Specification

## Purpose

Serves land-cover masks over HTTP from the registry's approved model, reports which model version produced each mask and records every served request for monitoring.

## Requirements

### Requirement: Predict one image per request

The service SHALL accept one 8-bit image with at least three bands (GeoTIFF, PNG or JPEG) as the raw body of `POST /predict` and SHALL answer in the same response with the class mask of its first three bands as a single-band GeoTIFF of internal class IDs 0–7, 255 where the input pixel is invalid. A georeferenced input SHALL yield a mask on the same grid, CRS and transform.

#### Scenario: Valid tile
- **WHEN** a client posts a 512×512 RGB GeoTIFF tile
- **THEN** the service returns status 200 with a 512×512 mask of values 0–7 on the tile's grid, the mask's class fractions and the input features.

#### Scenario: Image without georeferencing
- **WHEN** a client posts a PNG image
- **THEN** the mask has the image's pixel grid and no CRS.

### Requirement: Identify the model and code of each prediction

Each prediction response SHALL name the registered model, the version number that produced the mask and the commit of the running image. The version SHALL be the immutable number the alias pointed to when the service loaded the model, not the alias.

#### Scenario: Version behind the alias
- **WHEN** `champion` points to version 2 at start-up
- **THEN** every response reports `model_version` 2 until the service restarts, even if the alias moves meanwhile.

#### Scenario: Promotion without rebuild
- **WHEN** the operator points `champion` at version 1 and restarts the service with the same image
- **THEN** the next response reports version 1.

### Requirement: Reject unusable input with a reason

The service SHALL refuse with a 4xx status and a reason, and without a mask, an upload that cannot be decoded, is not 8-bit, has fewer than three bands, has no valid pixel, or exceeds the configured byte or pixel limit. A refusal SHALL be logged and counted as `invalid` and SHALL produce no drift observation.

#### Scenario: Not an image
- **WHEN** a client posts bytes that do not decode as a raster
- **THEN** the service answers 400 with a reason naming the decode failure, and the log row has outcome `invalid` and no features.

#### Scenario: Image above the limit
- **WHEN** a client posts an image whose pixel count exceeds the configured limit
- **THEN** the service answers 413 with the limit and the image size, before running the model.

### Requirement: Report input features and a dark-image warning

For each valid image the response and the log SHALL carry the mean of each of the three channels over valid pixels on a 0–255 scale, brightness as the mean of those three, and each class's share of valid pixels. When a dark-image threshold is configured, an image whose brightness is below it SHALL be served with a warning.

#### Scenario: Dark image
- **WHEN** the threshold is 63 and a valid image has brightness 40
- **THEN** the service returns the mask with status 200 and `dark_warning` true.

#### Scenario: No threshold configured
- **WHEN** no dark-image threshold is configured
- **THEN** responses and log rows carry no warning value.

### Requirement: Log every served request

The service SHALL write one row per served `/predict` request to the request log before responding, with time received, model name and version, image commit, outcome, reason, optional client source ID, grid size, valid pixel count, the features, the class fractions, the warning and the mask. When the row cannot be written, the request SHALL fail with status 500.

#### Scenario: Served request
- **WHEN** a valid image is served
- **THEN** exactly one row with outcome `ok` and the same request ID as the response exists in the log.

#### Scenario: Client source ID
- **WHEN** a client sends header `X-Source-Id: D017-2021/AA-S2-9_2-7/q0`
- **THEN** the row stores that value, so labels can later be joined to the prediction.

#### Scenario: Log unavailable
- **WHEN** the database rejects the write
- **THEN** the client receives 500 and no mask.

### Requirement: Report readiness only when able to serve

`GET /health/live` SHALL answer 200 while the process runs. `GET /health/ready` SHALL answer 200 only while the model is loaded and the request log is reachable, and 503 with the reason otherwise. Until the model is loaded, `/predict` SHALL answer 503. The service SHALL retry loading in the background until it succeeds.

#### Scenario: Alias absent from the registry
- **WHEN** the service starts with an alias that the registry does not have
- **THEN** `/health/live` answers 200, `/health/ready` answers 503 naming the missing alias, and `/predict` answers 503.

#### Scenario: Model appears later
- **WHEN** the alias is created while the service is running and not ready
- **THEN** the service becomes ready without a restart and serves the version the alias names.

### Requirement: Expose service metrics

`GET /metrics` SHALL expose, in the Prometheus text format, the count of `/predict` requests by outcome and model version, their latency, and whether a model is loaded. Requests to the health and metrics endpoints SHALL NOT be counted.

#### Scenario: Requests counted by outcome
- **WHEN** the service has served two valid images and refused one invalid upload
- **THEN** `/metrics` reports 2 requests with outcome `ok` and 1 with outcome `invalid`, and the latency histogram has 3 observations.

# Spec Delta

## ADDED Requirements

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

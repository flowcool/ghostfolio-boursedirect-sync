# connector-runtime delta

## ADDED Requirements

### Requirement: Startup identity and banner

The container SHALL print five static ASCII art lines for `BD SYNC`, then
`Bourse Direct -> Ghostfolio`, then
`ghostfolio-boursedirect-sync version X.Y.Z — commit <12hex>`.
The art and subtitle SHALL contain no ANSI escapes. They SHALL appear once
per container start, before schedule validation. Each run SHALL log the same
identity once. An absent version SHALL display `dev`. A revision SHALL be
exactly 40 lowercase hexadecimal characters; otherwise display `unknown`.

#### Scenario: Scheduled startup and run

- **WHEN** a scheduled container starts and a run begins
- **THEN** the container prints the banner once and each run logs its identity
- **AND** schedule errors retain the startup identity

### Requirement: Safe operational logs

Logs SHALL use a timestamp and `[LEVEL]`. `LOG_LEVEL` SHALL control their
threshold. INFO and lower levels SHALL use stdout. WARNING and higher levels
SHALL use stderr. HTTP library DEBUG request logs SHALL remain disabled.
Failure logs and notifications SHALL use fixed redacted failure classes.
They SHALL exclude arbitrary exception text and credentials.
Each run SHALL log its effective comparison timezone. Compose and its ENV
example SHALL default `TZ` to `Europe/Paris`. This does not change source dates.
When `DRY_RUN` is absent, each run SHALL warn
`DRY_RUN not set: simulation, nothing written`.
Existing mode validation and financial rules SHALL remain applicable.

#### Scenario: DEBUG run and private transport failure

- **WHEN** `LOG_LEVEL=DEBUG` and a request fails with credentials in its diagnostic
- **THEN** logs show the fixed failure class without private diagnostic text
- **AND** the notification excludes credentials
- **AND** severity selects the correct stream

#### Scenario: Default simulation

- **WHEN** `DRY_RUN` is absent
- **THEN** each run emits the simulation warning once
- **AND** configured timezone and identity appear in its INFO logs

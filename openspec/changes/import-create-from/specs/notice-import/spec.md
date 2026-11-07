## ADDED Requirements

### Requirement: Creation cut-off

Optional ENV `IMPORT_CREATE_FROM` SHALL accept only a valid `YYYY-MM-DD` date.
Absent or empty SHALL disable the cut-off. Other values SHALL give
`invalid_configuration IMPORT_CREATE_FROM` before service access.
The importer SHALL never create a supported row whose printed trade or payment
date is before the cut-off. The boundary day SHALL remain eligible.
Historical rows SHALL remain parsed for existing review and `NOTICE_COVERAGE`.
The cut-off SHALL grant no correction authority. Historical rows SHALL NOT add
simulated holdings. Historical selection failures and unsupported operations
SHALL NOT block recent creations. Current unsupported operations SHALL retain
their existing security holds. Historical unsupported operations SHALL retain
historical review holds. Coverage SHALL retain absent, unreadable, unsupported
and unresolved findings for the complete source. Normal logs SHALL count excluded
supported source rows and documents with only historical rows, including exempt
unreadable documents. Repeated source copies SHALL count as source rows.

#### Scenario: Boundary and default
- **WHEN** a supported row is before, on or after the configured date
- **THEN** only the latter two can be created; absent or empty retains current selection.

#### Scenario: Invalid date
- **WHEN** the date is malformed or impossible
- **THEN** `invalid_configuration IMPORT_CREATE_FROM`, no service access, exit 1.

#### Scenario: Historical false creations
- **WHEN** historical notices differ from existing manual activities
- **THEN** no historical creation; recent absent rows remain subject to normal guards.

#### Scenario: Historical review and coverage
- **WHEN** historical rows need correction or have no proved match
- **THEN** existing review authority applies; full coverage retains each finding.

#### Scenario: Historical stop
- **WHEN** an old DIVISION concerns a security with a recent BUY
- **THEN** coverage reports DIVISION; the old stop does not hold the recent BUY.

## MODIFIED Requirements

### Requirement: Unreadable documents block writes

Unreadable notices/accounts or unknown field labels SHALL stop all writes with
`notice_unreadable`. Simulation SHALL list readable activities. With a cut-off,
an unreadable original SHALL be exempt from this normal write block only when
its Paperless document `created` date is valid and before the cut-off. The date
SHALL be a `YYYY-MM-DD` calendar date. Missing, invalid or current date SHALL
retain the block. Filename and ingestion date SHALL NOT exempt a notice.
Acquisition or authorization failure SHALL remain a failure. Log the exempt
document ID and unreadable finding. Full coverage SHALL still report it as
unreadable and incomplete. Never infer its security or financial content.

#### Scenario: Unreadable document
- **WHEN** PDF unreadable without an exempt document date
- **THEN** `notice_unreadable`, no writes.

#### Scenario: Historical unreadable notice
- **WHEN** unreadable original has Paperless `created` before the cut-off
- **THEN** normal writes can continue; logs and coverage retain the unreadable finding.

#### Scenario: Missing or current date
- **WHEN** unreadable original has missing, invalid or boundary-day document date
- **THEN** `notice_unreadable`, no writes, exit 1.

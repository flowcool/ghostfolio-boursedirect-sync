# Spec Delta

## Purpose

Provide bounded preparation and preservation around existing financial commands with exact bindings and single-use authority.

## ADDED Requirements

### Requirement: Exact phase contracts

`python3 scripts/operation_run.py --config PATH --phase PHASE` SHALL enforce the design schema and fixed contracts without progression/retry. Each phase SHALL check target/config/image equality and approved authority; consume its grant durably before dispatch. Consumed grants SHALL refuse reuse, including after crash. Failure SHALL retain phase/exit/safe-code evidence and stop `HORS_CHEMIN`.

| PHASE | Prerequisite | Action; required proof |
| --- | --- | --- |
| preflight | Validated plan | Verify target/capabilities/interpreter/stopped consumers; verified complete backups/restore access |
| install | Preflight | Build pinned source/create stopped connector; actual digest/preservation |
| at1-preview | Install | Auth/product preview; exact selected intent/journal unchanged |
| at1-confirm | Preview/separate grant | Auth/product confirmation; only selected marker confirmed |
| simulate | Confirmation/broker grant | Compose DRY_RUN=1; complete window/pending-set digest/zero writes |
| import | Simulation/financial grant/a3ri | Compose DRY_RUN=0; exact approved creation/response/readback |
| readback | Import/destination-read grant | Complete account/activity GETs; exact preservation |
| repeat | Readback/new broker grant | Compose DRY_RUN=1; duplicates only/zero proposals/writes |
| rollback-install | Install/rollback grant | Restore authorized deployment only; journals/evidence intact |

#### Scenario: Offline phase and crash acceptance
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` exercises all phases with synthetic roots/mocked SSH/Docker/HTTP
- **THEN** missing grants/proofs and crash/reuse refuse without live/shared-state access.

### Requirement: Recoverable deployment

Backup/restore SHALL verify complete inventories, hashes, ownership, modes and aliases. Before authentication, verify Compose capabilities, `/opt/venv/bin/python` and rollback access. Pin actual built digest before creation; never overwrite unknown images. Preserve original artifacts and post-import journals.

#### Scenario: Unsafe preparation
- **WHEN** the offline command injects drift, missing prerequisites or backup corruption
- **THEN** refusal precedes authentication/mutation.

### Requirement: Ephemeral bearer transport

Receive permanent Security Token via `GHOST_ACCESS_TOKEN`; provisioning remains external. Exchange at most once per recovery/readback invocation. Recovery SHALL send one complete activities GET; readback one account GET/one activities GET; no broker/financial POST. Bearer SHALL travel through pipe/stdin into child ENV only, never Docker configuration, argv/files/logs. Compose SHALL retain pinned image, empty CRON, `APPRISE_URLS=[]`, no TTY and guards.

#### Scenario: Secret and persistence faults
- **WHEN** the offline command injects auth/transport/confirmation uncertainty
- **THEN** Docker-config excludes bearer; argv/log/output-files exclude credentials; uncertainty stays fenced.

### Requirement: Strict cash and derived aggregates

Retain complete all-account/cash and count-checked activities, originals, output/journal deltas and hashed receipts. Account `activitiesCount`/`dividendInBaseCurrency` and root `activitiesCount`/`totalDividendInBaseCurrency` SHALL equal baseline plus exact authorized-activity-derived deltas. All other account fields/cash, including `balance`/`balanceInBaseCurrency`, SHALL remain exact. Preserve activity fields except existing nested-profile exceptions. Missing/redacted/incomplete evidence or unproved derivation SHALL refuse.

#### Scenario: Preservation fault
- **WHEN** the offline command injects cash/account/activity changes or wrong aggregates
- **THEN** it refuses with changed paths only, without values.

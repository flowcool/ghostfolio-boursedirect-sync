# Spec Delta

## Purpose

Bound existing financial commands with exact target bindings, preservation and single-use authority.

## ADDED Requirements

### Requirement: Exact phase contracts

`python3 scripts/operation_run.py --config PATH --phase PHASE` SHALL enforce schema/contracts without progression/retry; verify target/config/phase-specific image/authority; durably consume grants before dispatch. Consumed grants SHALL refuse reuse after crash. Failure SHALL retain phase/exit/safe-code evidence and stop `HORS_CHEMIN`.

| PHASE | Prerequisite | Action; required proof |
| --- | --- | --- |
| preflight | Validated plan | Verify target/capabilities/interpreter/stopped consumers; verified complete backups/restore access |
| install | Preflight | Build pinned source/create stopped connector; actual digest/preservation |
| at1-preview | Install | Auth/product preview; exact selected intent/journal unchanged |
| at1-confirm | Preview/separate grant | Auth/product confirmation; only selected marker confirmed |
| simulate | Confirmation/broker grant | Compose DRY_RUN=1; complete window/pending-set digest/zero writes |
| import | Simulation/financial grant/a3ri/proven deltas | Compose DRY_RUN=0; exact approved creation/response/readback |
| readback | Import/destination-read grant | Complete account/activity GETs; exact preservation |
| repeat | Readback/new broker grant | Compose DRY_RUN=1; duplicates only/zero proposals/writes |
| rollback-install | Install/rollback grant | Restore authorized deployment only; journals/evidence intact |

#### Scenario: Offline phase and crash acceptance
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` exercises all phases with synthetic roots/mocked SSH/Docker/HTTP
- **THEN** missing grants/proofs and crash/reuse refuse without live/shared-state access.

### Requirement: Recoverable deployment

Backup/restore SHALL verify inventories/hashes/ownership/modes/aliases. Before auth, verify Compose capabilities, `/opt/venv/bin/python`, rollback access. Enforce original/built/rollback digests as defined in design; never overwrite unknown images. Preserve originals/post-import journals.

#### Scenario: Unsafe preparation
- **WHEN** the offline command injects drift, missing prerequisites or backup corruption
- **THEN** refusal precedes authentication/mutation.

### Requirement: Ephemeral bearer transport

Receive external permanent Security Token via `GHOST_ACCESS_TOKEN`. HTTPS SHALL be default; only `http://ghostfolio:3333` on verified trusted Docker network is permitted. HTTP remains unencrypted. Verify exact target/network before token transmission. Exchange once maximum per recovery/readback. Recovery: one activities GET; readback: one account/one activities GET; no broker/financial POST. Bearer SHALL use pipe/stdin-to-child-ENV only, never Docker configuration/argv/files/logs. Compose retains pinned image/empty CRON/`APPRISE_URLS=[]`/no TTY/guards.

#### Scenario: Secret and persistence faults
- **WHEN** the offline command injects target/network drift or auth/transport/confirmation uncertainty
- **THEN** Docker-config excludes bearer; argv/log/output-files exclude credentials; uncertainty stays fenced.

### Requirement: Strict cash and derived aggregates

Before any import POST, SHALL prove/retain calculation and expected results for account `activitiesCount`/`dividendInBaseCurrency` and root `activitiesCount`/`totalDividendInBaseCurrency` from complete baseline plus authorized activities. Unproved calculation SHALL block import; no numerical tolerance. Afterwards compare exact results. Retain complete all-account/cash/count-checked activities/originals/output/journal-deltas/hashed receipts. Other account fields/cash, including `balance`/`balanceInBaseCurrency`, remain exact. Preserve activity fields except existing nested-profile exceptions. Missing/redacted/incomplete evidence SHALL refuse.

#### Scenario: Preservation fault
- **WHEN** the offline command injects cash/account/activity changes or wrong aggregates
- **THEN** it refuses with changed paths only, without values.

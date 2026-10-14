# Spec Delta

## Purpose

Provide tested preparation and evidence commands around existing financial commands, with exact target binding and separately approved operation phases.

## ADDED Requirements

### Requirement: Explicit bounded phases

`python3 scripts/operation_run.py --config PATH --phase PHASE` SHALL accept only `preflight`, `install`, `at1-preview`, `at1-confirm`, `simulate`, `import`, `readback`, `repeat`, `rollback-install`. Each invocation SHALL enforce its separately approved envelope and prerequisites without progressing or retrying. Missing, failed or uncertain proof SHALL stop with `HORS_CHEMIN`, phase, exit status and safe product codes.

#### Scenario: Offline phase acceptance
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` runs with synthetic roots and mocked SSH/Docker/HTTP
- **THEN** all phases and authority failures are checked without live/shared-state access.

### Requirement: Target and recoverable deployment

Private keyed YAML SHALL bind exact host/daemon/project/service/runtime/network/volume/account, mount aliases, configuration hashes, source revision and image identities. Before authentication, commands SHALL verify stopped consumers, Compose capabilities, `/opt/venv/bin/python` and rollback access. Backup/restore SHALL verify full runtime/shared-state inventories, hashes, ownership, modes and aliases. Installation SHALL pin source and actual built digest before container creation; unknown tags SHALL never be overwritten. Rollback SHALL restore only authorized deployment changes, retaining post-import journals and original evidence.

#### Scenario: Drift or unsafe restoration
- **WHEN** the offline command injects target drift, missing capabilities/interpreter, damaged backup or unknown image
- **THEN** it refuses before authentication or mutation and preserves protected bytes.

### Requirement: Existing financial commands and secret delivery

Recovery SHALL call the unchanged product with selected run/ordinal, at most one auth and one complete activities GET; no broker/financial POST. Bearer SHALL remain in process memory/child ENV, never argv/files/logs. Compose SHALL perform simulation/import/repeat with pinned image, empty CRON, `APPRISE_URLS=[]`, no TTY and existing financial guards; `infra-a3ri` SHALL own dispatch-scope enforcement.

#### Scenario: Bounded recovery and persistence
- **WHEN** the offline command injects auth/GET failures or uncertain confirmation
- **THEN** it proves request bounds, secret exclusion and preserved uncertainty without retry.

### Requirement: Complete preservation evidence

Readback SHALL retain complete all-account/cash and count-checked activity snapshots, originals, product output and journal deltas. Comparisons SHALL allow only approved new activity/local-confirmation/deployment deltas and existing nested-profile exceptions. Receipts SHALL trace phase, pins, artifact hashes, comparison and safe diagnostics; missing/redacted/incomplete evidence SHALL refuse.

#### Scenario: Unexpected preservation delta
- **WHEN** the offline command injects unrelated account/cash/activity/filesystem changes or incomplete readback
- **THEN** it identifies bounded changed paths without values and refuses success.

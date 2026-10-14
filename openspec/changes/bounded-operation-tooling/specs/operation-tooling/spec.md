# Spec Delta

## ADDED Requirements

### Requirement: Bounded phases

`python3 scripts/operation_run.py --config PATH --phase PHASE` SHALL verify target/config/image/prerequisites, execute only PHASE, retain safe exit/code evidence and stop HORS_CHEMIN on failure/uncertainty. No progression/retry.

| PHASE | Prerequisite; permitted action/proof |
| --- | --- |
| preflight | Validated plan; target/Compose/`/opt/venv/bin/python`/stopped-consumer verification |
| install | Preflight/mutation grant; pinned build/stopped creation/actual digest |
| at1-preview | Verified existing installation; selected recovery preview/journal unchanged |
| at1-confirm | Preview/mutation grant; only selected marker confirmed |
| simulate | Verified installation/no unresolved AT1; DRY_RUN=1, complete window/pending-set digest/zero writes |
| import | Simulation/mutation grant/infra-a3ri; Compose DRY_RUN=0/exact additive creations/readback |
| readback | Verified installation; standalone or post-import complete account/activity GETs |
| repeat | Readback; DRY_RUN=1, duplicates only/zero proposals/writes |

Mutating phases SHALL consume grants before dispatch; crash/failed/uncertain grants SHALL refuse reuse. GETs/analysis SHALL need no consumable receipt. New installation requires separate authorization. Before broker connection, SHALL check capture date/last acquisition, enforce one acquisition/day maximum and otherwise reuse private captures.

#### Scenario: Phase acceptance
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` runs isolated mocked phases
- **THEN** drift/reused grants/second daily acquisition/uncertain dispatch refuse; repeated reads remain permitted.

### Requirement: Dedicated secure recovery transport

Permanent credential SHALL enter via GHOST_ACCESS_TOKEN. HTTPS SHALL be default; only `http://ghostfolio:3333` on verified trusted Docker network is permitted, with explicit unencrypted-HTTP risk. Verify destination container/image/network/IP and connected peer before each credential-bearing request; no redirects/retries. AT1 SHALL use dedicated callback: maximum one auth/one activities GET, no account GET/broker/import. Readback permits one auth/one account/one activities GET. Bearer SHALL travel pipe/stdin-to-child GHOST_SESSION_BEARER only, never Docker configuration/argv/files/logs. Compose retains empty CRON/APPRISE_URLS=[]/no TTY.

#### Scenario: Transport acceptance
- **WHEN** the offline command injects target/peer drift or secret leakage
- **THEN** transport refuses before disclosure and preserves uncertainty fencing.

### Requirement: Exact persisted financial proof

Before any intent, SHALL enforce `infra-a3ri` manifest/account/window/pending-set binding. Before import POST, SHALL prove complete original-token Decimal baseline, unique IDs/count, approved payloads/expected creations. Afterwards SHALL compare every old persisted activity/exact authorized creation, all native accounts[].balance/currency and other protected fields; zero tolerance/no repair. Preserve private originals/journals/receipts. Missing/redacted/incomplete proof SHALL refuse.

Only these account-response paths SHALL be diagnostic:

```text
$.accounts[].activitiesCount
$.accounts[].dividendInBaseCurrency
$.accounts[].interestInBaseCurrency
$.accounts[].valueInBaseCurrency
$.accounts[].allocationInPercentage
$.accounts[].balanceInBaseCurrency
$.accounts[].quantity
$.accounts[].value
$.activitiesCount
$.totalBalanceInBaseCurrency
$.totalDividendInBaseCurrency
$.totalInterestInBaseCurrency
$.totalValueInBaseCurrency
```

Retain/report changes without blocking/predicting. Activity-list count validation remains blocking. Existing nested assetProfile/SymbolProfile activitiesCount/updatedAt exceptions remain; unknown paths stay protected.

#### Scenario: Preservation acceptance
- **WHEN** the offline command changes native cash/old activities/approved creations or diagnostic paths
- **THEN** protected changes refuse with paths only; diagnostic changes are reported separately.

# Spec Delta

## Purpose

Import supported Bourse Direct operation notices into an explicit Ghostfolio account through unattended Docker Compose operation.

## ADDED Requirements

### Requirement: Explicit operating mode

ENV SHALL configure operation: `DRY_RUN` `0`/`false`/`no`/`off` imports; `1`/`true`/`yes`/`on` or absent simulates; other values refuse. Simulation SHALL never write financial data or mark proposals imported. `GHOST_HOST`, `GHOST_ACCESS_TOKEN`, `GHOST_ACCOUNT_ID`, `MAPPING_FILE` SHALL configure destination and readable YAML, possibly empty. Discovery SHALL need neither Ghostfolio nor mapping.

#### Scenario: Real BUY simulation
- **WHEN** `docker compose up --abort-on-container-exit --exit-code-from boursedirect-sync` runs without TTY, with `DRY_RUN=1` and a real BUY
- **THEN** logs show its date, ISIN, symbol, quantity, price, fee and `financial_writes=0`.

### Requirement: Notice acquisition and login safety

Notices SHALL be the sole source for the selected PEA/PEA-PME over today and the previous 89 days in Europe/Zurich. Bitwarden `BW_*` SHALL supply credentials/TOTP. Login SHALL occur at most once per run. Failed/uncertain login SHALL block restarts until operator resolution. Unexpected pages, incomplete coverage or account mismatch SHALL refuse import.

#### Scenario: Login already unresolved
- **WHEN** the Compose command above runs with a retained unresolved login attempt
- **THEN** logs report the refusal, zero broker attempts and zero financial writes.

### Requirement: Account discovery without TTY

Absent `BD_SOURCE_ACCOUNT_REF` SHALL trigger one discovery, log copyable references/wrappers without holders/balances, then exit nonzero without import. Persistent state SHALL prevent CRON/restart repetition until configuration. Source and destination SHALL match exactly; missing/ambiguous accounts SHALL refuse substitutes.

#### Scenario: Missing source account
- **WHEN** the Compose command above runs without source reference or discovery receipt
- **THEN** logs list `BD_SOURCE_ACCOUNT_REF` options and configuration-required status, with one login and zero imports.

### Requirement: Supported financial semantics

BUY/SELL, including foreign operations, SHALL retain Decimal quantities, established EUR prices and brokerage. COUPONS SHALL become DIVIDEND: quantity one, credited EUR amount, zero fee, no inferred withholding. Dates SHALL use the row date, not the notice header date, at midnight UTC. Unknown operations, unproved currency or nonzero TVA SHALL skip and fail the run, even without ISIN. Other known out-of-scope rows and rows without ISIN SHALL log an error line without failing the run. Valid operations continue.

#### Scenario: Mixed notices
- **WHEN** the Compose command above simulates observed BUY/SELL/coupon forms, a DROITS DE GARDE row and a DIVISION row
- **THEN** logs show supported proposals, net dividends, row dates, one error line per skipped row, zero writes and exit zero.

### Requirement: Instrument resolution

Resolution SHALL prioritize YAML, unique existing Ghostfolio ISIN/profile matches, then ISIN lookup. Automatic selection SHALL require one distinct eligible EUR symbol. Ambiguity, absence or failure SHALL skip, log candidate tickers and fail the run until YAML resolves it. Venue text SHALL not determine tickers.

#### Scenario: Ambiguous lookup
- **WHEN** the Compose command above runs with empty YAML and several eligible lookup candidates
- **THEN** logs list candidate tickers, skip the ISIN, continue resolved operations and exit nonzero.

### Requirement: Additive import with readback

Deduplication SHALL read all destination account activities. Existing activities and cash SHALL never change. A rejected symbol SHALL not block other imports. Success SHALL require readback of the same account, identity comment, date, symbol and amounts. An unconfirmed write SHALL block writes, across restarts, until operator resolution.

#### Scenario: Previously imported notices
- **WHEN** the Compose command above runs in simulation against matching owned activities
- **THEN** logs report duplicates and zero new proposals; uncertain retained imports instead refuse writing.

### Requirement: Holdings reconciliation before import

After deduplication, all pending trades SHALL reconcile against net Ghostfolio quantities per symbol, including preceding pending BUYs. Pre-window holdings and corporate actions must already exist in Ghostfolio. Negative projected holdings or ambiguous manual overlap SHALL stop the entire run before financial writes, including simulation. Errors SHALL identify ISIN/symbol, availability and requested sale. Only confirmed accepted BUYs SHALL fund dispatched SELLs.

#### Scenario: Insufficient shares
- **WHEN** the Compose command above proposes selling 50 shares while Ghostfolio holds 10, without preceding new BUYs
- **THEN** logs show an insufficient-holdings error, available 10, sale 50, nonzero exit and zero financial writes.

### Requirement: Scheduled operation and reporting

Empty `CRON` SHALL run once; valid five-field `CRON` SHALL schedule nonoverlapping runs. Logs SHALL report proposed/imported/duplicate/skipped counts without secrets/pages. Optional `APPRISE_URLS` SHALL send one bounded alert per failed non-simulated run. Confirmed empty windows SHALL succeed.

#### Scenario: Invalid schedule
- **WHEN** the Compose command above runs with malformed `CRON`
- **THEN** it exits nonzero before broker access and logs a fixed configuration error.

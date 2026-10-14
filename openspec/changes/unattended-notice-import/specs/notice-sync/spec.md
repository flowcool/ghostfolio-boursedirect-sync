# Spec Delta

## Purpose

Import supported Bourse Direct operation notices into an explicit Ghostfolio account through unattended Docker Compose operation.

## ADDED Requirements

### Requirement: Explicit operating mode

ENV SHALL configure operation: `DRY_RUN` `0`/`false`/`no`/`off` imports; `1`/`true`/`yes`/`on` or absent simulates; other values refuse. Runs SHALL never request interactive confirmation. Simulation SHALL never write financial data or mark proposals imported. `GHOST_HOST`, `GHOST_ACCESS_TOKEN`, `GHOST_ACCOUNT_ID`, `MAPPING_FILE` SHALL configure destination and readable YAML, possibly empty. Discovery SHALL need neither Ghostfolio nor mapping.

#### Scenario: Real BUY simulation
- **WHEN** `docker compose up --abort-on-container-exit --exit-code-from boursedirect-sync` runs without TTY, with `DRY_RUN=1` and a real BUY
- **THEN** logs show its date, ISIN, symbol, quantity, price, fee and `financial_writes=0`.

### Requirement: Notice acquisition and login safety

Notices SHALL be the sole broker source for the selected PEA/PEA-PME over today and the previous 89 days in Europe/Zurich. This 90-day acquisition limit SHALL NOT limit the Ghostfolio history used for reconciliation. Bitwarden `BW_*` SHALL supply credentials/TOTP. Login SHALL occur at most once per run. Failed/uncertain login SHALL block restarts until operator resolution. Unexpected pages, incomplete coverage or account mismatch SHALL refuse import.

#### Scenario: Login already unresolved
- **WHEN** the Compose command above runs with a retained unresolved login attempt
- **THEN** logs report the refusal, zero broker attempts and zero financial writes.

### Requirement: Account discovery without TTY

Absent `BD_SOURCE_ACCOUNT_REF` SHALL trigger one discovery, log copyable references/wrappers without holders/balances, then exit nonzero without import. Persistent state SHALL prevent CRON/restart repetition until configuration. Source and destination SHALL match exactly; missing/ambiguous accounts SHALL refuse substitutes.

#### Scenario: Missing source account
- **WHEN** the Compose command above runs without source reference or discovery receipt
- **THEN** logs list `BD_SOURCE_ACCOUNT_REF` options and configuration-required status, with one login and zero imports.

### Requirement: Supported financial semantics

BUY/SELL, including foreign operations, SHALL retain Decimal quantities, established EUR prices and brokerage. COUPONS SHALL become DIVIDEND: quantity one, credited EUR amount, zero fee, no inferred withholding. New activity dates SHALL use the row date, not the notice header date, at midnight UTC; this serialization SHALL NOT require existing manual activities to have midnight UTC timestamps. Unknown operations, unproved currency or nonzero TVA SHALL skip and fail the run, even without ISIN. Other known out-of-scope rows and rows without ISIN SHALL log an error line without failing the run. Valid operations continue.

#### Scenario: Mixed notices
- **WHEN** the Compose command above simulates observed BUY/SELL/coupon forms, a DROITS DE GARDE row and a DIVISION row
- **THEN** logs show supported proposals, net dividends, row dates, one error line per skipped row, zero writes and exit zero.

### Requirement: Instrument resolution

Resolution SHALL prioritize YAML, unique existing Ghostfolio ISIN/profile matches, then ISIN lookup. Automatic selection SHALL require one distinct eligible EUR symbol. Ambiguity, absence or failure SHALL skip, log candidate tickers and fail the run until YAML resolves it. Venue text SHALL not determine tickers.

#### Scenario: Ambiguous lookup
- **WHEN** the Compose command above runs with empty YAML and several eligible lookup candidates
- **THEN** logs list candidate tickers, skip the ISIN, continue resolved operations and exit nonzero.

### Requirement: Additive import with readback

Deduplication and holdings reconciliation SHALL read all destination account activities, without a 90-day cutoff. Existing activities and cash SHALL never change. A rejected symbol SHALL not block other imports. Success SHALL require readback of the same account, identity comment, date, symbol and amounts. An unconfirmed write SHALL block writes, across restarts, until operator resolution.

Operator resolution of an import intent SHALL be an explicit command selecting
the exact retained run identifier and ordinal. It SHALL bind the pending body,
saved HTTP 201 response remote ID, saved pre-write baseline and saved complete
post-write readback before obtaining one fresh complete Ghostfolio activities
GET with a pre-obtained session bearer. It SHALL send no authentication or
financial POST and make no broker request. Positive proof SHALL require one
exact active owned activity with the saved remote ID, every saved activity still
present, and every persisted field unchanged except Ghostfolio's derived
`assetProfile.activitiesCount` or `SymbolProfile.activitiesCount`. A preview
SHALL retain the intent. Explicit confirmation SHALL atomically move only the
proved identity and remote ID from `pending` to `confirmed`. Missing, incomplete,
changed, ambiguous or contradictory evidence SHALL refuse and leave the journal
bytes unchanged. Normal synchronization SHALL never recover or replay an intent
automatically.

#### Scenario: Previously imported notices
- **WHEN** the Compose command above runs in simulation against matching owned activities
- **THEN** logs report duplicates and zero new proposals; uncertain retained imports instead refuse writing.

#### Scenario: Explicit positive-readback recovery
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_import.py` replays an anonymized retained pending dividend with its saved response, baseline and readback, then supplies a fresh complete GET containing the same unique remote activity
- **THEN** preview sends one GET and leaves the journal unchanged; explicit confirmation sends one GET, records the exact marker and remote ID atomically, sends no POST or broker request, and a normal reconciliation reports that notice as a duplicate while retaining the next notice as pending.

#### Scenario: Recovery evidence is insufficient
- **WHEN** the same offline recovery lacks an artifact or exact activity, has an incomplete snapshot, changed persisted field or remote ID, or contains more than one matching activity
- **THEN** it reports a fixed recovery refusal, sends no POST or broker request, and preserves the journal bytes exactly.

### Requirement: Manual trade recognition on an established calendar day

Manual BUY/SELL recognition SHALL require the same destination account, established instrument, operation type and established calendar day, with exact quantity, unit price, currency, data source and fees. Days SHALL come from retained entry-context provenance or the explicitly approved existing-history convention below. Stored time SHALL NOT require midnight UTC. Current server timezone SHALL NOT establish historical entry context. Matching SHALL preserve one-to-one multiplicity; unaccepted day uncertainty or ambiguous multiplicity SHALL remain unresolved. Source execution time SHALL remain part of notice identity and ordering. Owned-import recognition and readback SHALL retain exact stored-date and financial comparison.

The commands in the new reconciliation scenarios describe future implementation acceptance. Their offline cases SHALL use anonymized retained notice/destination evidence; constructed boundary and multiplicity variants SHALL be identified as such, not as observed broker behavior. This planning revision does not claim those cases already pass.

#### Scenario: Same established day with a non-midnight timestamp
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k manual_calendar_day` replays an anonymized retained BUY/SELL with established same-day context, equal financial fields and one matching non-midnight manual activity
- **THEN** output confirms one manual duplicate, zero new proposals for it, unchanged existing fields and zero financial writes.

#### Scenario: Historical day provenance is unknown
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k manual_calendar_day` replays the same candidate with its entry-day provenance unverified and no approved legacy reference, even if current server TZ suggests the notice day
- **THEN** output identifies unverified day provenance and confirms whole-run refusal with nonzero run status and zero financial writes.

#### Scenario: Fees or multiplicity conflict
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k manual_calendar_day` replays retained conflicting-fee evidence and a labelled constructed unequal-multiplicity variant
- **THEN** output identifies the fee difference or multiplicity conflict, confirms no arbitrary adoption or correction, and confirms whole-run refusal with nonzero run status and zero financial writes.

### Requirement: Explicitly approved existing-history reference

An operator MAY explicitly accept existing history without original entry receipts. Optional `approved_legacy_baseline` in private `manual-day-context.yaml` SHALL bind a complete count-checked snapshot using `snapshot_path`, `snapshot_sha256`, `account_id`, `display_timezone` and `approval_reference`. Paths SHALL remain under the evidence root without symlinks. No run SHALL create approval implicitly. Approved displayed days SHALL use the declared IANA timezone as a convention with `approved_legacy_display_convention` provenance. This acceptance SHALL NOT claim historical proof, establish execution order or correct any activity. Genuine entry receipts SHALL take precedence.

All manual history in the approved account SHALL remain exactly bound by identity, stored timestamp, financial fields, instrument/profile identity, comments, account and activity inclusion context. Changed, missing or additional manual rows, incomplete snapshots, changed bytes or invalid configuration SHALL refuse. New connector-owned activities remain subject to exact ownership and financial checks. Existing exact financial comparisons, multiplicity and nearby-conflict refusal SHALL remain enforced. A conflict that can duplicate an operation or change sale availability SHALL refuse before writes. All retained notices, window rows and complete destination history SHALL participate in offline simulation before any distinct real-import authorization.

#### Scenario: Approved history completes reconciliation without inventing evidence
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k approved_legacy` replays complete approved snapshots without original entry receipts
- **THEN** declared display days supply the bounded convention; provenance stays uncertain; exact comparisons and multiplicity remain enforced; changed snapshots/history and remaining ambiguity refuse; financial writes remain zero.

### Requirement: Automatic manual dividend recognition

An active manual DIVIDEND SHALL be recognized automatically as already represented when destination account, established instrument, established civil day, currency, data source, total and fees match exactly. Total SHALL mean Decimal quantity × unit price and equal the notice's credited net EUR amount. Different quantity/unit-price representations SHALL NOT block this match. No gross amount or withholding SHALL be inferred. Matching SHALL consume activities one-to-one and require exact multiplicity; unaccepted day uncertainty or ambiguous matches SHALL remain unresolved. Recognition SHALL create no activity and change no existing field. Connector-owned recognition and readback SHALL remain exact, including stored date, quantity and unit price.

#### Scenario: Equal manual dividend is recognized automatically
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k manual_dividend_equivalence` replays a labelled constructed same-day manual dividend with equal credited total and fees, including an equivalent quantity/unit-price representation
- **THEN** output confirms one automatic manual duplicate, zero new proposals for it, no confirmation request, unchanged existing fields and zero financial writes; exact connector-owned duplicates remain recognized.

#### Scenario: Dividend date, financial context or multiplicity differs
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k manual_dividend_equivalence` replays retained different-day/different-total dividend evidence and labelled constructed fee, currency, data-source, unknown-provenance and unequal-multiplicity variants
- **THEN** output identifies the unresolved comparison, performs no arbitrary adoption or correction, and confirms whole-run refusal before writes without requesting confirmation.

### Requirement: Similar activity reporting before overlap refusal

Dry-run SHALL display all same-account, established-instrument and same-type candidates within ±3 civil days for BUY/SELL and ±4 for DIVIDEND, inclusive. Amount and fee differences SHALL NOT exclude candidates. The report SHALL show source and destination days, day provenance, signed day gap, quantities, unit prices, totals, fees and differences.

Total SHALL mean quantity × unit price, using Decimal. Dividend total SHALL be compared with the notice's credited net EUR amount, without inferring gross amounts or withholding. Candidates SHALL be ordered by absolute total difference and show signed EUR and percentage differences relative to the source total; differences SHALL mean destination minus source. Unavailable comparisons, including a percentage with zero source total, SHALL be marked unverified.

Exact automatic matches SHALL be reported as duplicates; other overlapping manual dividend candidates SHALL require manual reconciliation through the dry-run diagnostic. Proximity alone SHALL NOT establish a duplicate, select a mapping, correct an existing activity or authorize creation of an uncertain operation. Unaccepted day uncertainty SHALL be reported and SHALL NOT prove absence of overlap. Dry-run SHALL finish reporting all applicable candidates and missing evidence before unresolved overlap stops the entire run with a nonzero exit and zero financial writes. The same whole-run refusal SHALL precede any financial write in import mode, without prompting. After manual reconciliation outside the run, a later dry-run SHALL reevaluate the evidence under the same automatic rules; it SHALL NOT bypass remaining conflicts. Already identified, exactly matching connector-owned activities SHALL remain duplicates.

#### Scenario: Dividend crosses the UTC and civil-day boundary
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k similar_activity_report` replays anonymized retained dividend evidence with established civil-day context, four UTC days but three civil days of separation and a different total
- **THEN** output includes the candidate, source net credit, destination quantity × unit price, signed civil-day/total/fee differences and review-required status, followed by nonzero run status and zero financial writes.

#### Scenario: Manual reconciliation followed by another dry-run
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k similar_activity_report` replays retained conflicting dividend evidence, then a labelled constructed reconciled same-day/equal-total snapshot with equivalent quantity/unit-price representation, and a variant with a remaining conflict
- **THEN** the first run reports the conflict and refuses; the reconciled snapshot reports automatic-duplicate status without requiring review or proposing a new activity; the remaining-conflict variant still refuses, with zero financial writes and no confirmation request throughout.

#### Scenario: Inclusive windows without an amount filter
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k similar_activity_report` replays labelled constructed candidates at ±3/±4 civil days for trades and ±4/±5 for dividends, including differing totals and fees
- **THEN** output includes trade candidates through ±3 and dividend candidates through ±4, excludes established days beyond those windows, orders included candidates by absolute total difference without an amount cutoff, and reports signed EUR/percentage differences; included unresolved candidates refuse the whole run.

#### Scenario: Report all candidates despite an early uncertainty
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k similar_activity_report` replays several notice rows with an early ambiguous candidate and a later candidate whose day or amount context is unverified
- **THEN** output reports both before the terminal refusal, marks unavailable comparisons unverified without discarding possible overlap, and confirms zero financial writes and no uncertain operation created or corrected in simulation or import mode.

### Requirement: Holdings reconciliation before import

Historical stock-day proof SHALL be required only for destination-account/instrument keys with a pending SELL. Purchase-only and dividend-only instruments SHALL NOT require historical stock-day proof. With no pending SELL, the holdings function SHALL return all proposals in source order. Independent overlap, identity, financial-context and import-acceptance guards SHALL remain enforced.

After deduplication, stock at each pending SELL SHALL be calculated per destination account and established instrument from all relevant active Ghostfolio history before that sale, including history older than 90 days, and preceding pending trades. Existing and pending representations of the same notice SHALL be counted once. Later BUYs SHALL never fund an earlier SELL. Pre-window holdings and corporate actions must already be represented in Ghostfolio; no broker-history reconstruction SHALL occur.

Within a civil day, source-proven execution order SHALL be used when available, including for already represented notices. Stored manual timestamps SHALL NOT establish execution order by themselves. If preceding-day stock covers the same-day sales, an unknown same-day BUY order SHALL NOT cause refusal. If a sale depends on a same-day BUY and their order cannot be established, the whole run SHALL refuse before writes, without asking for confirmation. Dry-run SHALL report the sale, dated availability, dependent purchase and missing order evidence.

Negative dated holdings or unresolved overlap SHALL stop the entire run before financial writes, including simulation; dry-run candidate reporting SHALL finish before this refusal. Errors SHALL identify ISIN/symbol, sale day, availability and requested sale. Pending BUYs SHALL support simulation only when they precede the sale. Only exact readback-confirmed BUYs SHALL fund dispatched SELLs, still respecting source chronology; skipped, rejected or merely submitted BUYs SHALL never fund them.

#### Scenario: Historical stock proof applies only to pending sales
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k holdings_without_pending_sale` replays anonymized retained dividend-only inputs, labelled purchase-only inputs and a mixed instrument case with a pending SELL
- **THEN** dividend-only and purchase-only instruments require no historical stock-day proof; every instrument with a pending SELL still requires its complete relevant history and proved availability/order; all proposals retain source order and independent overlap refusal remains enforced.

#### Scenario: Insufficient shares
- **WHEN** the Compose command above proposes selling 50 shares while Ghostfolio holds 10, without preceding new BUYs
- **THEN** logs show an insufficient-holdings error, available 10, sale 50, nonzero exit and zero financial writes.

#### Scenario: A later existing purchase cannot fund an earlier sale
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k chronological_holdings` replays the labelled constructed sale of 20 on September 1 with no prior stock and an existing purchase of 50 on September 10
- **THEN** output shows September 1 availability zero and sale 20, followed by whole-run refusal and zero financial writes despite positive current stock.

#### Scenario: Old stock and preceding purchases remain available
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k chronological_holdings` replays labelled constructed purchases older than 90 days, existing prior sales and preceding pending purchases with proved order
- **THEN** output shows exact dated availability and accepts covered sales in simulation, counts each represented notice once, and confirms that only readback-confirmed preceding purchases fund dispatch.

#### Scenario: Same-day order is unknown or proved
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_reconciliation.py -k chronological_holdings` replays labelled constructed same-day purchases/sales with sufficient preceding-day stock, insufficient preceding-day stock and unknown order, and proved preceding/following execution order
- **THEN** sufficient prior stock and a proved preceding purchase pass; an unknown required order reports missing evidence and refuses, and a proved later purchase cannot fund the sale; every refusal precedes financial writes and requests no confirmation.

### Requirement: Scheduled operation and reporting

Empty `CRON` SHALL run once; valid five-field `CRON` SHALL schedule nonoverlapping runs. Logs SHALL report proposed/imported/duplicate/skipped counts without secrets/pages. Optional `APPRISE_URLS` SHALL send one bounded alert per failed non-simulated run. Confirmed empty windows SHALL succeed.

#### Scenario: Invalid schedule
- **WHEN** the Compose command above runs with malformed `CRON`
- **THEN** it exits nonzero before broker access and logs a fixed configuration error.

### Requirement: Development acceptance and final persistence validation

Development acceptance for import and scheduling SHALL use offline evidence without requiring historical financial corrections or an actual import. Task 4.2 SHALL prove the import safeguards with mocked acquisition/destination; task 5.1 SHALL follow development acceptance, independently of real persistence. Runtime refusal rules SHALL remain unchanged.

Final task 6.1 SHALL exclusively own actual creation, exact response/readback and repeat-with-zero-new-activities acceptance, after development completion and separate operator reconciliation. It SHALL require scoped broker-login and financial-write authorization. Offline or simulated acceptance SHALL NOT establish persistence or production readiness. The change and epic SHALL remain open until final validation succeeds.

#### Scenario: Import implementation accepted offline
- **WHEN** `.venv/bin/python -m pytest -q -s tests/test_notice_import.py tests/test_notice_reconciliation.py tests/test_wire.py tests/test_community_connect.py` replays anonymized and labelled constructed import cases with mocked destination/acquisition
- **THEN** checks prove explicit/default simulation, unresolved-intent refusal, exact response/readback, inactive-row rejection, confirmed-only holdings and duplicate-only repeat without a real financial write; scheduled-operation development can follow, while final persistence remains unproven.

#### Scenario: First authorized real creation after development
- **WHEN** `docker compose up --build --abort-on-container-exit --exit-code-from boursedirect-sync` runs without TTY after development completion and operator reconciliation, with private configured accounts/state, `DRY_RUN=0`, empty `CRON` and scoped authorization
- **THEN** accepted response fields match the expected import projection and complete readback matches the source-derived account, identity, date, symbol and exact amounts with the same remote ID; unrelated activities and cash remain unchanged, and logs record actual confirmed creations.

#### Scenario: Authorized real repeat creates nothing
- **WHEN** the same Compose command runs again against the retained state and destination under a scoped broker-login authorization
- **THEN** logs and complete readback confirm zero new activities; unresolved receipts or remaining conflicts still refuse without a guard bypass.

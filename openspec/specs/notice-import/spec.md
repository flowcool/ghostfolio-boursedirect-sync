# notice-import Specification

## Purpose

Read Bourse Direct PDF notices from Paperless into one Ghostfolio account.
Add BUY, SELL and DIVIDEND activities. One container serves one account.

"Run" means `docker compose run --rm -T <service>; echo "exit=$?"`.
Notices have Paperless `Source = Bourse Direct`, with/without `PAPERLESS_DONE_TAG`.

## Requirements

### Requirement: Settings from ENV only

Settings SHALL come from ENV. Required: `GHOST_HOST`,
`GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`,
`PAPERLESS_URL`, `PAPERLESS_TOKEN`. Optional: `PAPERLESS_DONE_TAG` (default
`ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`,
`APPRISE_TIMEOUT`, `LOG_LEVEL`. Invalid/missing settings SHALL give `invalid_configuration`.
Logs SHALL omit secrets. `GHOST_ACCOUNT_NAME` SHALL match exactly one
active account. Excluded targets SHALL give `invalid_configuration`.

#### Scenario: Missing Paperless token
- **WHEN** Run omits `PAPERLESS_TOKEN`
- **THEN** output: `invalid_configuration`, `PAPERLESS_TOKEN` and
  `exit=1`.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** Run finds two exact target names
- **THEN** output: `invalid_configuration` and `exit=1`.

### Requirement: Usable Ghostfolio evidence

Incomplete/masked activities or invalid values, eligibility or profiles SHALL
give `activities_unavailable` before selection, without writes.
Current assetProfile SHALL take precedence over legacy SymbolProfile.
Draft, excluded and non-YAHOO activities SHALL not support holdings or manual
matches. Their BD identities SHALL remain occupied.
Future source activities SHALL be deferred with `future_activity`.

#### Scenario: Unsafe activity evidence
- **WHEN** Run receives incomplete, masked or invalid activity evidence
- **THEN** output: `activities_unavailable`, 0 creations and `exit=1`.

#### Scenario: Excluded target
- **WHEN** Run selects an excluded account
- **THEN** output: `invalid_configuration` and `exit=1`.

#### Scenario: Future activity
- **WHEN** Run reads a future BUY beside a current BUY
- **THEN** only the current BUY is proposed; output: `future_activity` and `exit=1`.

### Requirement: Simulation by default

`DRY_RUN=0` SHALL send activities to Ghostfolio. `DRY_RUN=1`, or no value,
SHALL simulate. Another value SHALL give `invalid_configuration`. Simulation SHALL log every proposed field, without writes or notifications.

#### Scenario: Real BUY in simulation
- **WHEN** Run omits `DRY_RUN` on one real BUY notice
- **THEN** output: `DRY RUN`, a BUY line, `exit=0`.

### Requirement: Paperless source

Each run SHALL read all original notice PDFs. Paperless SHALL remain read-only.
Rejected tokens SHALL stop with `paperless_auth_failed`. Unexpected
answers SHALL stop with `paperless_unreachable`. Logs SHALL omit holder names
and addresses. Account numbers appear only in comments and their log lines.
Errors show HTTP status, code and document ID only.

`BourseDirect_` filenames without `Source = Bourse Direct` SHALL give
`source_field_missing` and stop writes.

#### Scenario: Wrong Paperless token
- **WHEN** Run uses an invalid `PAPERLESS_TOKEN`
- **THEN** output: `paperless_auth_failed` and `exit=1`.

#### Scenario: Paperless down
- **WHEN** Run executes while Paperless is unavailable
- **THEN** output: `paperless_unreachable` and `exit=1`.

#### Scenario: Source field missing
- **WHEN** Run finds a `BourseDirect_` file without the Source field
- **THEN** output: `source_field_missing`, 0 creations and
  `exit=1`.

### Requirement: Account selection

Before target selection, require one labelled account per notice. Remove spaces
once; require equality with `BD_ACCOUNT_REF`. Only count other accounts.
Missing/multiple accounts SHALL give `notice_unreadable`.

#### Scenario: Notice of another account
- **WHEN** Run reads BUY notices from two accounts
- **THEN** output: one BUY line, 1 other-account notice and `exit=0`.

### Requirement: Unreadable documents block writes

An unreadable notice/account or unknown field label SHALL give
`notice_unreadable` and stop all Ghostfolio writes. Simulation SHALL still
list readable activities.

#### Scenario: Unreadable document
- **WHEN** Run uses `DRY_RUN=0` with a BUY and a non-notice PDF
- **THEN** output: `notice_unreadable`, 0 creations and
  `exit=1`.

### Requirement: Amount checks

For BUY/SELL, abs(QUANTITE) × COURS rounded HALF_UP to EUR cents SHALL equal
printed BRUT. Preserve source quantity/price. BUY debit SHALL equal BRUT +
COURTAGE + TVA; SELL credit SHALL equal BRUT − COURTAGE − TVA. TVA SHALL be zero.
Missing COURTAGE SHALL mean zero only for BUY with explicit TVA=0 and Debit=BRUT;
report `brokerage_zero_inferred`. Otherwise reject with `amount_check_failed`.
COUPONS SHALL be a positive EUR credit. All amounts SHALL be EUR.
Failed rows SHALL get `amount_check_failed`, without import.

#### Scenario: Altered amount
- **WHEN** Run reads a BUY with altered BRUT
- **THEN** output: `amount_check_failed`, 0 creations and
  `exit=1`.

#### Scenario: Rounded gross
- **WHEN** Run reads a real trade with a fractional-cent product
- **THEN** its HALF_UP cent value equals printed BRUT; source quantity/price stay exact.

#### Scenario: Omitted brokerage
- **WHEN** Run reads a real BUY without COURTAGE, with TVA=0 and Debit=BRUT
- **THEN** output: zero brokerage and `brokerage_zero_inferred`, exit=0.

### Requirement: Activity content

BUY/SELL SHALL use absolute QUANTITE, source COURS and EUR. SELL fee SHALL be
COURTAGE; BUY fee SHALL add attributed charged TTF to COURTAGE.
COUPONS SHALL give DIVIDEND, quantity 1, net credit as unit price and fee 0.
Use the row date at midnight UTC. Comment SHALL be
`BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`. KIND is type. Row key SHALL use the broker notice reference when present; otherwise, normalized
notice rows. File metadata SHALL not affect identity. Identical rows SHALL use
their occurrence rank. Copies of the same notice SHALL not add activities.

#### Scenario: Real coupon in simulation
- **WHEN** Run uses a real coupon notice
- **THEN** output: DIVIDEND, quantity 1, net price, fee 0, exit=0.

### Requirement: Charged TTF attribution

A TAXE TRANSACT FINANCIERES row SHALL add its charged amount to exactly one BUY
in the same source account, notice, date and ISIN. Never estimate or allocate
tax. Ambiguity SHALL log `ttf_attribution_failed` and suspend affected BUYs;
independent operations SHALL continue.

#### Scenario: Attributed TTF
- **WHEN** Run reads a real notice with uniquely attributed TTF
- **THEN** BUY fee equals brokerage plus TTF; quantity/price stay unchanged.

#### Scenario: Ambiguous TTF
- **WHEN** Run cannot uniquely attribute a TTF row
- **THEN** it reports `ttf_attribution_failed`, skips affected BUYs and exits 1.

### Requirement: Security resolution

Resolve each ISIN through `MAPPING_FILE`'s `symbol_mapping`, then Ghostfolio
lookup. Accept exactly one EUR lookup result. Otherwise, skip that ISIN with
`unresolved_security` and log its mapping line. A missing or invalid mapping
file SHALL stop with `invalid_mapping`, unless `MAPPING_FILE` is empty.

#### Scenario: No EUR lookup result
- **WHEN** Run finds no unique EUR lookup without a mapping
- **THEN** output: `unresolved_security`, a mapping line and `exit=1`.

### Requirement: No duplicate activity

Exact account, `BD#v3#` comment, date, type, security, currency, quantity, price
and fee SHALL mean duplicate. Other values or another account SHALL give
`owned_activity_conflict`, except for the fee correction below.
Legacy v1/v2 and unowned rows SHALL match when:

- for a BUY or SELL, it has the same side, security (or ISIN), quantity and
  unit price, and a date within 2 days. Maximize exact one-to-one matches, then minimize date distance;
- for a DIVIDEND, it is a dividend of the same security with identical net
  amount, at most 3 days away.

Nearby trades with different quantity/price, or dividends with different net
amounts, SHALL get `possible_duplicate`, without import.

Malformed/unsupported reserved `BD#v` identities SHALL stop writes with
`invalid_identity`. Read valid legacy v1/v2.

#### Scenario: Regenerated notice
- **WHEN** two PDFs have the same notice rows and different file metadata
- **THEN** they propose each activity once, with identical identity.

#### Scenario: Moved identity
- **WHEN** a source identity exists in another Ghostfolio account
- **THEN** output: `owned_activity_conflict`, without recreating that activity.

#### Scenario: Invalid identity
- **WHEN** Run reads an invalid reserved BD identity
- **THEN** output: `invalid_identity`, 0 creations and `exit=1`.

#### Scenario: Second run
- **WHEN** Run repeats identical notices with `DRY_RUN=0`
- **THEN** output: only duplicates, 0 creations, exit=0.

#### Scenario: Coupon already in Ghostfolio
- **WHEN** Run reads a legacy-imported coupon
- **THEN** output: that coupon as a duplicate and no DIVIDEND line.

### Requirement: Sell guard

Use current net holdings plus chronological new rows; SELL first on equal
dates. No historical replay. A negative position SHALL block that SELL with
`sell_exceeds_holding`.

#### Scenario: Sell without a position
- **WHEN** Run uses a real SELL notice of a security not held
- **THEN** output: `sell_exceeds_holding` and `exit=1`.

### Requirement: Custody fees ignored

A DROITS DE GARDE row SHALL get code `custody_fee_ignored`, without import or exit-code change.

#### Scenario: Sell notice with a custody fee
- **WHEN** Run uses the real SELL notice with custody fees
- **THEN** output: the SELL line, `custody_fee_ignored` and `exit=0`.

### Requirement: Stop on a share-count change

DIVISION SHALL log `share_count_change`; unknown operations SHALL log
`unknown_operation`. Either with ISIN SHALL block that security across all
notices. Other securities SHALL continue. `PAPERLESS_DONE_TAG` SHALL clear
these codes for that document only; other rows stay importable.

#### Scenario: Division and coupon in one notice
- **WHEN** Run reads a coupon and DIVISION for one security
- **THEN** output: `share_count_change`, no DIVIDEND line and
  `exit=1`.

#### Scenario: Stop cleared
- **WHEN** Run reads that DIVISION document with `PAPERLESS_DONE_TAG`
- **THEN** output: coupon or duplicate, without `share_count_change`.

### Requirement: Additive writes with readback

Only the fee correction below permits an update. Never delete. Each sent comment SHALL read back
exactly once, with identical account, comment, symbol, data source, date, type,
quantity, unit price, fee and currency.
After uncertainty, wait briefly and read Ghostfolio again.
Complete exact confirmation SHALL allow continuation.
Failed, missing, changed, repeated or extra matching evidence SHALL give
`import_unconfirmed` and stop writes. Never resend while confirming.
Other comments do not count. Only confirmed activities advance real holdings.

#### Scenario: Unexpected import response
- **WHEN** an import response is empty and the delayed read still lacks a sent row
- **THEN** output: `import_unconfirmed`, no resend and `exit=1`.

#### Scenario: Delayed confirmation
- **WHEN** an import times out but the delayed complete read confirms every sent row
- **THEN** it confirms those activities once and continues without resending.

### Requirement: Exact BUY fee correction

Exactly one existing BUY matching account, date, security, quantity and unit
price SHALL qualify only when its fee equals brokerage alone and charged TTF
is uniquely attributed. Simulation SHALL show the proposed correction.
With writes enabled, change only fee to brokerage plus TTF. Preserve every
other field and logical identity. Confirm exact readback. An already-correct
fee SHALL be a no-op. Other differences SHALL be reported without correction.
An uncertain correction SHALL give `import_unconfirmed` and stop writes
without resend. A rerun SHALL neither create another BUY nor count TTF twice.

#### Scenario: Existing brokerage-only BUY
- **WHEN** Run processes that BUY with DRY_RUN=0
- **THEN** only its fee changes, exact readback confirms it, and rerun changes nothing.

### Requirement: Exit code, summary and notification

End with one summary line of counts. The exit code SHALL be 0
when each row is imported, corrected, simulated, a duplicate, a custody fee or
of another account; `brokerage_zero_inferred` is informational. Else it SHALL be 1. With `DRY_RUN=0` and `APPRISE_URLS`
set, exit code 1 SHALL send one notification with the codes.

#### Scenario: Failure notification
- **WHEN** Run uses `DRY_RUN=0`, `APPRISE_URLS` and an
  `unresolved_security` row
- **THEN** output: `Failure notification sent` and `exit=1`.

### Requirement: Schedule

Valid `CRON` SHALL schedule imports. Without it, run once.
Invalid `CRON` SHALL exit 1.

#### Scenario: Invalid schedule
- **WHEN** Run uses `CRON=bad`
- **THEN** output: `Invalid CRON` and `exit=1`.

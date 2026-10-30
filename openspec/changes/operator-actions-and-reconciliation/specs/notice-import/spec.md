# Notice import delta

`Run` means `docker compose run -T --no-deps importer` with stated inputs.

## MODIFIED Requirements

### Requirement: Settings from ENV only

Settings SHALL use ENV: required `GHOST_HOST`, `GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`, `PAPERLESS_URL`, `PAPERLESS_TOKEN`; optional `PAPERLESS_DONE_TAG` (default `ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`, `LOG_LEVEL`, `ACTIVITY_REVIEW_FILE`, `ACTIVITY_RECONCILIATION`. Invalid settings or nonunique/inactive/excluded targets SHALL give `invalid_configuration`. Omit secrets.

#### Scenario: Missing Paperless token
- **WHEN** token missing
- **THEN** output: `invalid_configuration`, exit 1.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** names collide
- **THEN** output: `invalid_configuration`, exit 1.

### Requirement: Usable Ghostfolio evidence

Incomplete/masked/invalid evidence SHALL give `activities_unavailable` before writes. assetProfile SHALL precede SymbolProfile. Draft/excluded/non-YAHOO rows SHALL occupy identities without supporting holdings/matches. Future events SHALL defer with `future_activity`.

#### Scenario: Unsafe activity evidence
- **WHEN** evidence masked
- **THEN** output: `activities_unavailable`, no writes.

#### Scenario: Excluded target
- **WHEN** target excluded
- **THEN** output: `invalid_configuration`, exit 1.

#### Scenario: Future activity
- **WHEN** date future
- **THEN** output: `future_activity`, no import.

### Requirement: Simulation by default

`DRY_RUN=0` SHALL enable financial writes; absent/1 SHALL simulate exact proposals. Other values SHALL give `invalid_configuration`. Review refresh/action notifications SHALL remain available.

#### Scenario: Real BUY in simulation
- **WHEN** BUY simulated
- **THEN** output: `DRY RUN`, exact fields.

### Requirement: Paperless source

Read all original source notices; Paperless SHALL remain read-only. Rejected tokens SHALL give `paperless_auth_failed`; unexpected answers, `paperless_unreachable`. Errors SHALL show only HTTP status/code/document ID. Omit holder/address; account references appear only in identity comments/logs. `BourseDirect_` files without `Source = Bourse Direct` SHALL stop writes with `source_field_missing`.

#### Scenario: Wrong Paperless token
- **WHEN** token rejected
- **THEN** output: `paperless_auth_failed`, exit 1.

#### Scenario: Paperless down
- **WHEN** service unavailable
- **THEN** output: `paperless_unreachable`, exit 1.

#### Scenario: Source field missing
- **WHEN** Source missing
- **THEN** output: `source_field_missing`, no writes.

### Requirement: Account selection

Require one labelled account per notice. Remove spaces once; match `BD_ACCOUNT_REF`. Only count other accounts. Missing/multiple accounts SHALL give `notice_unreadable`.

#### Scenario: Notice of another account
- **WHEN** accounts differ
- **THEN** output: selected rows; others counted.

### Requirement: Unreadable documents block writes

Unreadable notices/accounts or unknown field labels SHALL stop all writes with `notice_unreadable`. Simulation SHALL list readable activities.

#### Scenario: Unreadable document
- **WHEN** PDF unreadable
- **THEN** output: `notice_unreadable`, no writes.

### Requirement: Amount checks

For EUR BUY/SELL, abs(QUANTITE) × COURS rounded HALF_UP to cents SHALL equal BRUT. Preserve quantity/price. BUY debit SHALL equal BRUT+COURTAGE+TVA; SELL credit, BRUT−COURTAGE−TVA; TVA SHALL equal zero. Missing BUY brokerage SHALL mean zero only with explicit TVA=0 and Debit=BRUT: `brokerage_zero_inferred`. Coupons SHALL be positive EUR credits. Otherwise report `amount_check_failed`, without importing affected rows.

#### Scenario: Altered amount
- **WHEN** BRUT inconsistent
- **THEN** output: `amount_check_failed`, exit 1.

#### Scenario: Rounded gross
- **WHEN** fractional-cent gross
- **THEN** output: HALF_UP matches; values preserved.

#### Scenario: Omitted brokerage
- **WHEN** qualifying COURTAGE omitted
- **THEN** output: `brokerage_zero_inferred`, zero fee.

### Requirement: Activity content

BUY/SELL SHALL use absolute quantity, source price, EUR, printed date at midnight UTC. Fee SHALL equal brokerage plus attributed BUY TTF. DIVIDEND SHALL use quantity 1, net credit, fee 0. Identity SHALL be `BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`; KIND equals type; key uses broker reference, otherwise normalized rows with occurrence rank. File metadata SHALL NOT affect identity. Identity first lines SHALL permit notes after a blank separator.

#### Scenario: Real coupon in simulation
- **WHEN** coupon simulated
- **THEN** output: DIVIDEND, quantity 1, net.

### Requirement: Charged TTF attribution

Charged TTF SHALL attach to exactly one BUY in the same source account/notice/date/ISIN. Never estimate/allocate. Ambiguity SHALL give `ttf_attribution_failed`, holding affected BUYs while independent events continue.

#### Scenario: Attributed TTF
- **WHEN** TTF unique
- **THEN** output: brokerage+TTF; quantity/price preserved.

#### Scenario: Ambiguous TTF
- **WHEN** TTF ambiguous
- **THEN** output: `ttf_attribution_failed`, BUYs held.

### Requirement: Security resolution

Resolve ISIN through `MAPPING_FILE.symbol_mapping`, then unique EUR lookup. Otherwise hold ISIN with `unresolved_security` and mapping hint. Nonempty missing/invalid mapping SHALL give `invalid_mapping`.

#### Scenario: No EUR lookup result
- **WHEN** lookup nonunique
- **THEN** output: `unresolved_security`, mapping hint.

### Requirement: No duplicate activity

Identical account/identity/date/type/security/currency/quantity/price/fee SHALL mean duplicate. Compare identity first lines; preserve notes. Moved/conflicting identities SHALL give `owned_activity_conflict`, except eligible corrections. Without review, legacy/unowned trades SHALL match same side/security (or ISIN)/quantity/price within two days: maximize one-to-one matches, then minimize distance. Dividends SHALL match same security/net within three days. Other nearby values SHALL give `possible_duplicate`. Review-held events SHALL NOT become imports. Malformed/unsupported reserved identities SHALL stop writes with `invalid_identity`; valid v1/v2 SHALL remain readable without proving ownership alone.

#### Scenario: Regenerated notice
- **WHEN** copies regenerated
- **THEN** output: same identities, no duplicates.

#### Scenario: Moved identity
- **WHEN** identity moved
- **THEN** output: `owned_activity_conflict`, no recreation.

#### Scenario: Invalid identity
- **WHEN** identity malformed
- **THEN** output: `invalid_identity`, no writes.

#### Scenario: Second run
- **WHEN** inputs repeated
- **THEN** output: only duplicates, zero creations.

#### Scenario: Coupon already in Ghostfolio
- **WHEN** legacy coupon matches
- **THEN** output: duplicate, no DIVIDEND creation.

### Requirement: Sell guard

Use current holdings plus chronological new rows, SELL first on equal dates. No historical replay. Negative positions SHALL hold SELL with `sell_exceeds_holding`.

#### Scenario: Sell without a position
- **WHEN** holdings insufficient
- **THEN** output: `sell_exceeds_holding`, exit 1.

### Requirement: Custody fees ignored

Custody fees SHALL produce `custody_fee_ignored`, without activity or exit change.

#### Scenario: Sell notice with a custody fee
- **WHEN** custody fee present
- **THEN** output: `custody_fee_ignored`, SELL unaffected.

### Requirement: Stop on a share-count change

DIVISION SHALL give `share_count_change`; unknown operations, `unknown_operation`. With ISIN, hold that security across notices; independent securities continue. `PAPERLESS_DONE_TAG` SHALL waive these codes for that document only; other rows remain eligible.

#### Scenario: Division and coupon in one notice
- **WHEN** DIVISION unwaived
- **THEN** output: `share_count_change`, coupon held.

#### Scenario: Stop cleared
- **WHEN** document waived
- **THEN** output: coupon eligible, hold cleared.

### Requirement: Additive writes with readback

Never delete. Only corrections below SHALL permit updates. Every import SHALL read back exactly once with identical account/comment/symbol/data-source/date/type/quantity/price/fee/currency. Uncertainty SHALL permit delayed readback, never resend. Incomplete/conflicting/extra evidence SHALL stop writes with `import_unconfirmed`; only confirmed rows advance holdings.

#### Scenario: Unexpected import response
- **WHEN** confirmation absent
- **THEN** output: `import_unconfirmed`, no resend.

#### Scenario: Delayed confirmation
- **WHEN** delayed evidence exact
- **THEN** output: confirmed once; execution continues.

### Requirement: Exact BUY fee correction

One BUY matching account/date/security/quantity/price with brokerage-only fee and unique charged TTF SHALL qualify for fee-only correction. Preserve other fields/identity; correct fees SHALL do nothing. A usable persistent review file SHALL be required, even with profile `off`. An unset file SHALL hold that BUY with `review_evidence`; independent imports continue. Share correction budget/recovery below. Confirm exact readback; uncertainty SHALL give `import_unconfirmed`, without resend or double-counted TTF.

#### Scenario: Existing brokerage-only BUY
- **WHEN** file usable, TTF proved
- **THEN** output: fee-only update; repeat unchanged.

#### Scenario: Missing correction file
- **WHEN** review file unset
- **THEN** output: `review_evidence`, independent imports continue.

### Requirement: Exit code, summary and notification

Report `success`, `success with user action required`, or `failure` at INFO/WARNING/ERROR. Action-only holds SHALL permit exit 0; processing failures retain exit 1. Custody/inferred brokerage remain informational. Count imports/simulations/duplicates/conforming/corrections/migrations/holds/deferred work/delivery; mark unavailable/overlapping counts. Each action SHALL state reason/scope/impact/safe next step/resolution evidence, including imported events. Apprise SHALL send at most one redacted failure/action summary per run, including simulation; repeat unresolved actions; clean runs stay silent. Omit identifiers/securities/amounts/paths/secrets. Report sent/failed/unconfirmed; never retry timeout or change financial selection/exit for delivery failure.

#### Scenario: Failure notification
- **WHEN** failure/action persists
- **THEN** output: one redacted notification outcome.

### Requirement: Schedule

Valid `CRON` SHALL schedule imports; absence runs once; invalid values exit 1.

#### Scenario: Invalid schedule
- **WHEN** `CRON=bad`
- **THEN** output: `Invalid CRON`, exit 1.

## ADDED Requirements

### Requirement: Persistent operator review

`ACTIVITY_REVIEW_FILE` SHALL enable YAML reference/financial proposals, groups and conforming rows with exact before/after, changed fields, source/target, evidence, authority/status/block. Initialize only after valid acquisition. Unsafe paths/permissions/links/input overlap/concurrency/unavailable evidence SHALL give `review_unavailable` before financial writes. Preserve recovery evidence. Only `decision: yes` SHALL approve unchanged eligible proposals already present; `reject` rejects that pair without activity changes. Preserve unchanged choices; invalidate changed evidence. Invalidated rejections/rebuilt evidence SHALL NOT grant immediate automatic authority. Blocked `yes` SHALL remain blocked. Hold related imports only.

#### Scenario: Persistent operator review
- **WHEN** Run reads `yes` with changed evidence
- **THEN** it clears consent without executing that proposal.

### Requirement: Source-proven correction fields

Pair one validated event/activity in the same active account/type/YAHOO security/EUR. Conflicting ISINs/competing candidates SHALL block pairs; exact references take priority. Fees/order/aggregates SHALL NOT prove identity. Change only proved date/price/fee/reference; preserve ID/owner/account/security/type/currency/tags/notes and BUY/SELL quantity. DIVIDEND SHALL retain validated net, quantity 1. Show quantity differences/groups; never merge/split/delete. Legacy migration SHALL require reproducible event/account proof; otherwise `review_evidence`. Migrate comments alone; assess financial corrections later.

#### Scenario: Source-proven correction fields
- **WHEN** Run finds proved legacy ownership plus a fee discrepancy
- **THEN** it changes only the comment; another run evaluates fee.

### Requirement: Explicit reconciliation profiles

`ACTIVITY_RECONCILIATION` SHALL accept `off` (default), `conservative`, `balanced`, `permissive`. Non-off SHALL require review file and explicit IANA `TZ`, otherwise `invalid_configuration`. Off SHALL retain manual/TTF/recovery authority. Profiles SHALL NOT create `yes`. Pairs SHALL be mutually unique; conservative requires recognized unique reference; others permit unreferenced pairs.

| Profile | Absolute gross | Relative | Date distance |
| --- | --- | --- | --- |
| conservative | 0 EUR | 0 | 0 days |
| balanced | 0.01 EUR | 0.1% | 0 days |
| permissive | 1 EUR | 1% | BUY/SELL 2; DIVIDEND 3 days |

Both limits SHALL pass on exact positive quantity×price gross, excluding fees, relative to source gross. Fees SHALL require independent validation without matching limit. No FX/residue exception. Compare source midnight UTC/destination instant in `TZ`; show printed date/both instants; write source midnight UTC. Eligible outside-limit pairs SHALL remain manually reviewable.

#### Scenario: Explicit reconciliation profiles
- **WHEN** Run compares pairs at/beyond either limit
- **THEN** it only selects pairs passing both limits automatically.

### Requirement: Bounded corrections and durable uncertainty

Manual/profile/migration/TTF updates SHALL share one correction per run; new imports remain uncapped. Choose oldest eligible work, stable ties. Preserve deferred choices without reapproval. Simulation SHALL show `would correct`. Durably retain before/after/authority before updating; require exact changed/preserved-field readback. Uncertainty SHALL hold all account writes across restarts without resend. Only exact result confirmation SHALL settle pending work; old/missing/changed/unavailable evidence, simulation, profile changes or file removal SHALL NOT settle it.

#### Scenario: Bounded corrections and durable uncertainty
- **WHEN** Run resumes an uncertain correction
- **THEN** it retains the hold until exact confirmation without retry or double counting.

# notice-import delta

Run means `docker compose run --rm -T --no-deps importer` with real anonymized
inputs and an isolated destination. Check output/exit. Retained scenario values are not fixed runtime counts. Preserve archive failures.

## MODIFIED Requirements

### Requirement: Settings from ENV only

ENV SHALL supply `GHOST_HOST`, `GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`, `PAPERLESS_URL`, `PAPERLESS_TOKEN`; optional `PAPERLESS_DONE_TAG` (default `ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`, `LOG_LEVEL`, `ACTIVITY_REVIEW_FILE`, `ACTIVITY_RECONCILIATION`, `NOTICE_COVERAGE`. Invalid settings/nonunique/inactive/excluded targets SHALL give `invalid_configuration`. Omit secrets. `NOTICE_COVERAGE` SHALL accept only 0 (default) or 1. Value 1 SHALL select report-only execution regardless of `DRY_RUN`.

#### Scenario: Missing Paperless token
- **WHEN** token missing
- **THEN** `invalid_configuration`, `PAPERLESS_TOKEN`, exit 1.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** names collide
- **THEN** `invalid_configuration`, exit 1.

### Requirement: Source-proven correction fields

Pair validated event/activity within the same active account/type/YAHOO security/EUR, except the manually approved coupon currency replacement below. ISIN conflicts/competing candidates SHALL block pairs; exact references win. Fees/order/aggregates never prove identity. Change only proved date/price/fee/reference, plus the manual coupon quantity/currency fields below; preserve ID/owner/account/security/type/tags/notes and BUY/SELL quantity. Preserve currency except for the manual coupon replacement below. DIVIDEND SHALL retain validated net, quantity 1. Report quantity differences/groups; never merge/split/delete. Legacy migration SHALL require reproducible event/account proof; otherwise `review_evidence`. Migrate comments alone; assess financial corrections later.

#### Scenario: Separate migration
- **WHEN** finds proved legacy ownership plus a fee discrepancy
- **THEN** it changes only the comment; another run evaluates fee.

### Requirement: Exit code, summary and notification

Report `success`, `success with user action required`, or `failure` at INFO/WARNING/ERROR. Classify codes:

| Exit | Codes |
| --- | --- |
| 0, action | `review_approval`, `review_evidence`, `coverage_gap`, `position_mismatch`, `coverage_unverifiable` |
| 0, information | `custody_fee_ignored`, `brokerage_zero_inferred` |
| 1, failure | `invalid_configuration`, `invalid_mapping`, `paperless_auth_failed`, `paperless_unreachable`, `source_field_missing`, `notice_unreadable`, `amount_check_failed`, `activities_unavailable`, `unresolved_security`, `owned_activity_conflict`, `possible_duplicate`, `invalid_identity`, `sell_exceeds_holding`, `share_count_change`, `unknown_operation`, `future_activity`, `import_unconfirmed`, `ghostfolio_auth_failed`, `ttf_attribution_failed`, `ghostfolio_unreachable`, `unhandled_error`, `review_unavailable` |

Count imports/simulations/duplicates/conforming/corrections/migrations/holds/deferred work/delivery; mark unavailable/overlapping counts. Actions SHALL state reason/scope/impact/next-step/resolution, including imported events. Apprise SHALL send at most one redacted failure/action summary/run, including simulation; group by sorted reason/count pairs. Notify on first, changed or cleared groups,
including a cleared reason with count zero. Remind unchanged groups only after
168 hours since confirmed delivery. Same-count event replacements stay grouped.
Failures notify each run. Clean runs without previous groups stay silent.
Keep only private context-bound grouped delivery state beside review state.
Missing, corrupt, unsafe or unwritable state and clock rollback leave actions
eligible. Only confirmed delivery advances state. Failed runs cannot certify
resolution. Preserve full private findings each run. Omit identifiers/securities/amounts/paths/secrets. Report sent/failed/unconfirmed; never retry timeout or change financial selection/exit for delivery failure.

#### Scenario: Failure notification
- **WHEN** failure/action persists
- **THEN** `Failure notification sent` on delivery; otherwise failed/unconfirmed.

### Requirement: Bounded corrections and durable uncertainty

Apply every eligible manual/profile/migration/TTF correction, oldest first; stable ties; imports stay uncapped. Simulation SHALL show `would correct`. Persist before/after/authority before PUT. Next PUTs require exact changed/preserved-field readback and D=150 seconds after confirmation. Qualify D in labs. A new release raises D when the lab margin no longer passes. Uncertainty SHALL retain approvals and hold account writes across restarts without resend. Only exact confirmation settles pending; other evidence/settings/simulation/file changes SHALL NOT settle it.

#### Scenario: Restart
- **WHEN** an uncertain correction resumes
- **THEN** retain the hold until exact confirmation; never retry or double count.

## ADDED Requirements

### Requirement: Reviewed manual history corrections

New manual fee/coupon kinds SHALL use existing `ACTIVITY_REVIEW_FILE`, review,
journal and exact readback. Only unchanged `decision: yes` authorizes them,
including with non-off profiles. Profiles SHALL NOT approve these kinds.
Existing TTF/profile authority stays unchanged. Manual means an activity without a recognized BD identity. Show exact changes, notice,
target and association reason. Label proximity as a hypothesis until the
operator confirms payment identity.

Keep existing semantics for pending, blocked or rejected pairs. Hold pending
or ambiguous source events against import without a review file; report
`review_evidence`. Conflicting references/ISINs, source holds, unavailable
evidence or nonunique pairs SHALL prevent correction. Preserve ID, owner,
account, security, type, tags and the complete comment. Never merge, split,
delete or create replacements. Apply every eligible manual/profile/comment
correction in stable order without a count cap, under the shared correction
delay and recovery requirement above. Changed evidence SHALL clear approval. First uncertainty SHALL stop financial writes.

#### Scenario: Approval, restart and repeat
- **WHEN** Run applies several approved real fee and coupon proposals, then repeats or restarts after an uncertain response
- **THEN** exact completion requires no further update; uncertainty reports `import_unconfirmed` and retains all account writes on hold without resend.

### Requirement: Manual trade fee correction from the notice

Require mutually unique BUY/SELL pairs in the same account/security/EUR, with
exact side, quantity and price, within two calendar days in configured `TZ`. Fees SHALL NOT
choose or rank matches. The validated notice fee SHALL be truth: brokerage
plus uniquely attributed charged TTF for BUY; brokerage for SELL. Compare exact
decimal values without tolerance. Change only fee. Already correct fees SHALL
require no correction, including equal decimal spellings. Missing/ambiguous
TTF proof SHALL retain the existing hold.

#### Scenario: Twenty-four fee differences
- **WHEN** Run reviews the retained pre-correction notice comparison
- **THEN** it reports all 24 fee differences from the private qualification record, subject to source holds. Approval changes only fee; repeat proposes no further fee correction.

### Requirement: Manual coupon net and date alignment

Discover manual DIVIDEND candidates for the same account and resolved YAHOO
security within 31 calendar days in configured `TZ`, inclusively, in either direction.
Require one source per target and one target per source across all available
notices and destination rows. Recognized identities take precedence. A fee or
amount similarity SHALL NOT select a pair. Several candidates SHALL stay
blocked with `review_evidence`; no nearest-date selection.

Only reviewed payment identity SHALL permit replacing date with the printed
notice date at midnight UTC only when the configured `TZ` calendar day differs,
quantity with 1, unit price with exact net EUR
credit, and fee with 0. A wrong stored coupon currency SHALL be replaceable
with EUR only in this displayed manual proposal. Show old currency and amount;
do not calculate FX. Preserve the security profile and its market currency.
Set activity currency to EUR explicitly, including with a SEK market profile.
If the API cannot preserve the profile and exact activity values, hold the
proposal. The 31-day window SHALL NOT expand automatic profiles or normal
duplicate matching. A stored instant on the same local day SHALL stay unchanged without a date
proposal. Correct notice-net coupons SHALL remain conforming.

#### Scenario: Four probable payments
- **WHEN** Run reviews the four retained payments in the private qualification record
- **THEN** it proposes each exact net EUR credit on its printed date, with quantity 1 and fee 0; a foreign-currency target shows its old currency explicitly. No correction or duplicate creation occurs before approval.

#### Scenario: Window and ambiguity
- **WHEN** Run uses those coupons with explicitly derived target dates at 31 and 32 days or an extra competing dividend
- **THEN** 31 days can qualify, 32 days cannot, and competing pairs stay blocked even with `yes`.

### Requirement: Full available-notice coverage report

`NOTICE_COVERAGE=1` SHALL read every selected original across all Paperless
pages, including done-tagged notices, and complete usable Ghostfolio inventory.
Compare only configured source/destination accounts. Deduplicate by logical
identity. Report date range, document/row counts and counts for conforming,
correction candidate, unresolved association, absent supported, unsupported and
unreadable rows. Local output SHALL include each row's reason, notice identity,
date, type, resolved security and exact values.

A creation selected by normal import SHALL NOT alone prove absence. Examine
manual, legacy, alias, date, price and normalized-quantity candidates. Ambiguous
or unsupported representations SHALL be unresolved, never confirmed absent.
Fee differences and probable existing coupons SHALL NOT count as absent.
An absent row SHALL remain listed even when the sell guard blocks import.

This mode SHALL send no financial POST/PUT/DELETE, settle no pending correction,
and change no review decision or source document, even with `DRY_RUN=0` and `yes`.
Historical creation SHALL retain normal import and all guards.
Incomplete acquisition or unreadable evidence SHALL retain its failure code,
mark coverage incomplete, and prevent a clean-coverage claim. Notices
SHALL NOT prove broker-history completeness; empty periods stay unknown.

#### Scenario: Eleven absent rows and corrected history
- **WHEN** Run compares the retained 86-notice pre-correction set, then the retained post-correction destination
- **THEN** the first report distinguishes 11 absent supported rows from the 24 fee differences and 4 probable coupons. The retained BUY and SELL examples are absent initially and conforming afterward. The ten restored rows leave only the unresolved SELL absent. No writes occur.

#### Scenario: False creations and unreadable evidence
- **WHEN** Run reads the retained split-normalized rows, foreign-price rows, and the coupon without an ISIN
- **THEN** uncertain representations are not absence; unsupported events and `notice_unreadable` stay visible. It never reports complete coverage or invents an ISIN.

### Requirement: Notice-backed position comparison and alerts

For each resolved security, compare exact net BUY-minus-SELL quantities from
available notices with Ghostfolio net movements over the same observed date
interval. State UTC interval boundaries and both totals. Count each logical row
once. A difference SHALL give `position_mismatch`, labelled as an unexplained
position change, not an absolute holding error. Corporate actions, unsupported
quantity transformations, unresolved security or incomplete source SHALL make
the affected comparison unverifiable. A done tag SHALL NOT prove the missing
quantity transformation. Do not infer zero opening holdings.

Account/position statements SHALL NOT be parsed in this increment. Absolute
statement holdings, missing acquisition evidence and
periods outside available notices SHALL remain unverified. Never invent opening BUYs. Report this limitation with `coverage_unverifiable`.
Absent supported rows SHALL give `coverage_gap`. These three codes SHALL use
the existing action path: exit 0 unless a failure also occurs, one redacted
Apprise summary per run, including simulation, under the grouped notification and seven-day reminder
rules above. Informational limits without a concrete resolution action SHALL
remain local information and SHALL NOT create repeated required actions.
Alerts SHALL contain counts and next steps, without personal or financial
details. Existing failure precedence, silent clean runs and delivery rules remain.

#### Scenario: Position changes before and after backfill
- **WHEN** Run compares the retained BUY and SELL intervals before and after their restored trades
- **THEN** the exact initial source-minus-destination differences in the private qualification record become zero. Split evidence stays unverifiable; no absolute opening acquisition is inferred.

#### Scenario: Repeated redacted alert
- **WHEN** Run with `NOTICE_COVERAGE=1` finds a gap or unverifiable comparison twice
- **THEN** the first run sends one redacted grouped action summary; the unchanged next
  run stays silent until seven days. Group changes or cleared reasons notify; a simultaneous unreadable-notice failure keeps exit 1. Delivery uncertainty never causes a resend or financial write.

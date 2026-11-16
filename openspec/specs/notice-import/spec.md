# notice-import Specification

## Purpose

Import Bourse Direct PDF notices and optional monthly cash statements into one Ghostfolio account.
Run: `docker compose run --rm -T --no-deps -e CRON= importer` against an isolated destination. Read output and exit status.

## Requirements

### Requirement: Settings from ENV only

ENV SHALL supply `GHOST_HOST`, exactly one of `GHOST_ACCESS_TOKEN` or
`GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, and `BD_ACCOUNT_REF`.
Optional settings SHALL remain `PAPERLESS_DONE_TAG` (default `ghostfolio-done`),
`MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`,
`LOG_LEVEL`, `ACTIVITY_REVIEW_FILE`, `ACTIVITY_RECONCILIATION`,
`NOTICE_COVERAGE`, `IMPORT_CREATE_FROM`, and `CASH_BALANCE`. Their existing rules SHALL remain.
`NOTICE_COVERAGE` SHALL accept only 0 (default) or 1; 1 selects report-only
execution regardless of `DRY_RUN`.

Nonempty `NOTICE_DIR` SHALL select folder mode and require an absolute container
directory path. Both `PAPERLESS_URL` and `PAPERLESS_TOKEN` SHALL then be absent
or empty. Absent or empty `NOTICE_DIR` SHALL select Paperless and require both
Paperless settings. Both sources, neither source, invalid settings, or a
nonunique/inactive/excluded target SHALL give `invalid_configuration`, exit 1.
Configuration errors SHALL stop before service access. Omit secrets.
Nonempty `NOTICE_WAIVER_FILE` SHALL be invalid in Paperless mode.

#### Scenario: Folder without Paperless
- **WHEN** Run has valid `NOTICE_DIR` and no Paperless settings
- **THEN** it reads folder notices without contacting Paperless.

#### Scenario: Conflicting or absent source
- **WHEN** Run has both source configurations or neither
- **THEN** `invalid_configuration`, no service access, exit 1.

#### Scenario: Missing Paperless token
- **WHEN** Run selects Paperless without its token
- **THEN** `invalid_configuration`, `PAPERLESS_TOKEN`, exit 1.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** Run finds colliding target names
- **THEN** `invalid_configuration`, exit 1.

### Requirement: Usable Ghostfolio evidence

Incomplete/masked/invalid evidence SHALL give `activities_unavailable` before selection/writes. assetProfile precedes SymbolProfile. Draft/excluded/non-YAHOO identities count without holdings/matches. Future events defer: `future_activity`.

#### Scenario: Masked evidence
- **WHEN** evidence masked
- **THEN** `activities_unavailable`, no writes.

#### Scenario: Exclusion
- **WHEN** target excluded
- **THEN** `invalid_configuration`, exit 1.

#### Scenario: Future
- **WHEN** date future
- **THEN** `future_activity`, exit 1; current BUY remains eligible.

### Requirement: Simulation by default

`DRY_RUN=0` SHALL enable financial writes; absent/1 simulates; otherwise `invalid_configuration`. Review refresh/action notifications remain available.

#### Scenario: Simulated BUY
- **WHEN** BUY simulated
- **THEN** `DRY RUN`, exact fields.

### Requirement: Paperless source

In Paperless mode, read all selected original notices with `Source = Bourse
Direct`, including done-tagged notices. Paperless SHALL remain read-only.
Rejected tokens SHALL give `paperless_auth_failed`; unexpected answers,
`paperless_unreachable`. Errors SHALL show only HTTP status/code/document ID.
Omit holder/address; account references appear only in identity comments/logs.
`BourseDirect_` files without `Source = Bourse Direct` SHALL stop writes with
`source_field_missing`. Folder mode SHALL require no Paperless metadata.

#### Scenario: Wrong Paperless token
- **WHEN** Run uses a rejected Paperless token
- **THEN** `paperless_auth_failed`, exit 1.

#### Scenario: Paperless down
- **WHEN** Run cannot reach Paperless
- **THEN** `paperless_unreachable`, exit 1.

#### Scenario: Source field missing
- **WHEN** Run finds a Paperless `BourseDirect_` file without Source
- **THEN** `source_field_missing`, no writes.

### Requirement: Account selection

Selection SHALL require one labelled account/notice; remove spaces once; match `BD_ACCOUNT_REF`; count others. Missing/multiple: `notice_unreadable`.

#### Scenario: Other account
- **WHEN** accounts differ
- **THEN** selected rows; others counted.

### Requirement: Unreadable documents block writes

Unreadable notices/accounts or unknown field labels SHALL stop activity
writes with `notice_unreadable`, exit 1. Cash follows its separate requirements. Simulation SHALL list readable activities.
With `IMPORT_CREATE_FROM`, an unreadable Paperless original SHALL be exempt
from this normal write block only when its document `created` is a valid
`YYYY-MM-DD` before the cut-off. Missing, invalid or current dates retain the
block. Filename and ingestion date SHALL NOT exempt a notice. Acquisition or
authorization failure SHALL remain a failure. Log the exempt document ID and
unreadable finding. Coverage SHALL still report incomplete evidence,
`notice_unreadable` and exit 1. Never infer security or financial content.

Folder originals SHALL have no metadata-based unreadable exemption. An unknown
printed trade/payment date SHALL be unreadable and held, including when other
readable rows are historical. Filename, mtime, ctime and copy date SHALL grant
no exemption. A partially readable old date SHALL NOT exempt an unreadable file.

#### Scenario: Unreadable document
- **WHEN** Run reads an unreadable PDF without an eligible Paperless exemption
- **THEN** `notice_unreadable`, no activity writes, exit 1; cash keeps its separate guards.

#### Scenario: Historical unreadable Paperless notice
- **WHEN** Run reads an unreadable original with Paperless `created` before the cut-off
- **THEN** normal writes can continue; logs retain the finding; coverage fails as incomplete.

#### Scenario: Missing or current Paperless date
- **WHEN** Run reads an unreadable Paperless original with missing, invalid or boundary-day `created`
- **THEN** `notice_unreadable`, no activity writes, exit 1; cash keeps its separate guards.

#### Scenario: Old-looking folder file
- **WHEN** Run has a cut-off and an unreadable folder PDF with an old filename or mtime
- **THEN** `notice_unreadable`, no financial writes, exit 1.

### Requirement: Amount checks

Amounts SHALL be EUR. BUY/SELL: abs(QUANTITE)×COURS, HALF_UP cents, equals BRUT; preserve quantity/price. BUY-debit=BRUT+COURTAGE+TVA; SELL-credit=BRUT−COURTAGE−TVA; TVA=0. Missing BUY brokerage=0 only with explicit TVA=0/Debit=BRUT: `brokerage_zero_inferred`. Coupons: positive EUR credits; otherwise `amount_check_failed`, affected rows withheld.

#### Scenario: Altered gross
- **WHEN** BRUT inconsistent
- **THEN** `amount_check_failed`, exit 1.

#### Scenario: Rounding
- **WHEN** fractional-cent gross
- **THEN** HALF_UP matches; values preserved.

#### Scenario: Brokerage
- **WHEN** qualifying COURTAGE omitted
- **THEN** `brokerage_zero_inferred`, zero fee.

### Requirement: Activity content

BUY/SELL SHALL use absolute quantity/source price/EUR/printed date at midnight UTC; fee=brokerage+attributed-BUY-TTF. DIVIDEND: quantity=1/net-credit/fee=0. Identity: `BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`; KIND=type; key=broker reference, otherwise normalized rows+occurrence rank. Ignore file metadata. Permit notes after blank separator.

#### Scenario: Simulated coupon
- **WHEN** coupon simulated
- **THEN** DIVIDEND, quantity 1, net, fee 0.

### Requirement: Charged TTF attribution

Charged TTF SHALL require exactly one BUY within account/notice/date/ISIN. Never estimate/allocate. Ambiguity: `ttf_attribution_failed`; hold affected BUYs, continue independent events.

#### Scenario: Attribution
- **WHEN** TTF unique
- **THEN** brokerage+TTF; quantity/price preserved.

#### Scenario: Ambiguous tax
- **WHEN** TTF ambiguous
- **THEN** `ttf_attribution_failed`, BUYs held.

### Requirement: Security resolution

Resolve ISIN through `MAPPING_FILE.symbol_mapping`, then unique EUR lookup. Otherwise hold ISIN with `unresolved_security` and mapping hint. Nonempty missing/invalid mapping SHALL give `invalid_mapping`.

#### Scenario: Lookup
- **WHEN** lookup nonunique
- **THEN** `unresolved_security`, mapping hint.

### Requirement: No duplicate activity

Duplicate: identical account/identity/date/type/security/currency/quantity/price/fee. Compare identity first lines; preserve notes. Moved/conflicting identities SHALL give `owned_activity_conflict`, except eligible corrections. Both modes match unchanged legacy/unowned trades by side/security(or ISIN)/quantity/price within two days: maximize one-to-one matches, minimize distance. Dividends match security/net within three days. Other nearby values give `possible_duplicate`. Never import review-held events. Malformed/unsupported reserved identities: `invalid_identity`, stop writes; read valid v1/v2 without migration ownership. Unproved optional migrations never make unchanged duplicates required actions.

#### Scenario: Regeneration
- **WHEN** copies regenerated
- **THEN** same identities, no duplicates.

#### Scenario: Movement
- **WHEN** identity moved
- **THEN** `owned_activity_conflict`, no recreation.

#### Scenario: Invalidity
- **WHEN** identity malformed
- **THEN** `invalid_identity`, no writes.

#### Scenario: Repeat
- **WHEN** inputs repeated
- **THEN** only duplicates, zero creations.

#### Scenario: Duplicate coupon
- **WHEN** legacy coupon matches
- **THEN** duplicate, no DIVIDEND creation.

### Requirement: Sell guard

SHALL use current holdings plus chronological new rows; equal-date SELL first; no replay. Negative positions hold SELL: `sell_exceeds_holding`.

#### Scenario: Oversell
- **WHEN** holdings insufficient
- **THEN** `sell_exceeds_holding`, exit 1.

### Requirement: Custody fees ignored

Custody fees SHALL give `custody_fee_ignored`; import/exit unchanged.

#### Scenario: Custody
- **WHEN** custody fee present
- **THEN** `custody_fee_ignored`, SELL unaffected.

### Requirement: Stop on a share-count change

DIVISION SHALL give `share_count_change`; unknown operations, `unknown_operation`.
With ISIN, hold that security across notices; independent securities continue.
In Paperless mode, `PAPERLESS_DONE_TAG` SHALL waive these codes for that document
only; other rows remain eligible. The importer SHALL never apply that tag.
In folder mode, optional `NOTICE_WAIVER_FILE` SHALL be an absolute read-only
regular UTF-8 text file, at most 65,536 bytes. Each nonempty line SHALL contain
`sha256:<64 lowercase hex digits>`, one ASCII space, and exactly one of the two
stop codes. Duplicate pairs or other content SHALL be invalid. Blank lines are
allowed. Its path SHALL be outside `NOTICE_DIR` and separate from the review path.
Links, path overlaps and inode aliases SHALL be rejected. Missing, unreadable,
oversized or malformed files SHALL give `invalid_configuration` before service access.
Each entry SHALL waive only that document's matching stop code, like the done tag.
Unknown digests SHALL be ignored and counted. Other stops and guards SHALL remain.
Filenames, timestamps, directories and review `yes` SHALL NOT waive stops.
The importer SHALL never write this file, move notices or create done markers.
Existing historical cut-off rules SHALL remain applicable in both modes.

#### Scenario: Division and coupon in one notice
- **WHEN** Run reads an unwaived current DIVISION with a coupon for the same security
- **THEN** `share_count_change`, coupon held.

#### Scenario: Stop cleared
- **WHEN** Run reads a Paperless notice with the configured waiver tag
- **THEN** its stop is waived and the coupon remains subject to all other checks.

#### Scenario: Folder waiver clears stop
- **WHEN** Run reads a DIVISION with its exact digest and `share_count_change` waiver
- **THEN** that stop clears; other guards still apply to the security's coupon.

#### Scenario: Renamed waived file
- **WHEN** Run reads renamed bytes with the same waived digest
- **THEN** the matching stop stays waived.

#### Scenario: Changed bytes are not waived
- **WHEN** Run reads changed PDF bytes with only the old digest waived
- **THEN** the stop remains; the old digest is ignored and counted.

#### Scenario: Malformed waiver file
- **WHEN** Run has malformed waiver content
- **THEN** `invalid_configuration`, no service access, exit 1.

### Requirement: Additive writes with readback

Never delete. Only specified corrections update. Imports SHALL confirm once with identical account/comment/symbol/data-source/date/type/quantity/price/fee/currency. Permit delayed readback, never resend. Incomplete/conflicting/extra evidence: `import_unconfirmed`, stop writes. Only confirmed rows advance holdings.

#### Scenario: Unconfirmed import
- **WHEN** confirmation absent
- **THEN** `import_unconfirmed`, no resend.

#### Scenario: Delayed readback
- **WHEN** delayed evidence exact
- **THEN** confirmed once; execution continues.

### Requirement: Exact BUY fee correction

Fee-only correction SHALL require one account/date/security/quantity/price-matched BUY, brokerage-only fee, unique charged TTF. `ttf` authority includes exact unowned matches without `yes`; preserve comments bytes. Correct fees: no-op. Persistent review required even with profile `off`; unset file holds BUY: `review_evidence`; independent imports continue. Share budget/recovery below. Exact readback required; uncertainty: `import_unconfirmed`, no resend/double-counted TTF.

#### Scenario: Fee correction
- **WHEN** file usable, TTF proved
- **THEN** fee-only update; repeat unchanged.

#### Scenario: Review missing
- **WHEN** review file unset
- **THEN** `review_evidence`, independent imports continue.

### Requirement: Exit code, summary and notification

Report `success`, `success with user action required`, or `failure` at INFO/WARNING/ERROR. Classify codes:

| Exit | Codes |
| --- | --- |
| 0, action | `review_approval`, `review_evidence`, `coverage_gap`, `position_mismatch`, `coverage_unverifiable`, `cash_unavailable` |
| 0, information | `custody_fee_ignored`, `brokerage_zero_inferred` |
| 1, failure | `invalid_configuration`, `invalid_mapping`, `paperless_auth_failed`, `paperless_unreachable`, `source_field_missing`, `notice_unreadable`, `amount_check_failed`, `activities_unavailable`, `unresolved_security`, `owned_activity_conflict`, `possible_duplicate`, `invalid_identity`, `sell_exceeds_holding`, `share_count_change`, `unknown_operation`, `future_activity`, `import_unconfirmed`, `ghostfolio_auth_failed`, `ttf_attribution_failed`, `ghostfolio_unreachable`, `unhandled_error`, `review_unavailable`, `notice_source_unavailable` |

Count imports/simulations/duplicates/conforming/corrections/migrations/holds/deferred work/delivery; mark unavailable/overlapping counts. Actions SHALL state reason/scope/impact/next-step/resolution, including imported events. Apprise SHALL send at most one redacted failure/action summary/run, including simulation; group by sorted reason/count pairs. Notify on first, changed or cleared groups,
including a cleared reason with count zero. Remind unchanged groups only after
168 hours since confirmed delivery. Same-count event replacements stay grouped.
Failures notify each run. Clean runs without previous groups stay silent.
Keep only private context-bound grouped delivery state beside review state.
Missing, corrupt, unsafe or unwritable state and clock rollback leave actions
eligible. Only confirmed delivery advances state. Failed runs cannot certify
resolution. Preserve full private findings each run. Omit identifiers/securities/amounts/paths/secrets. Report sent/failed/unconfirmed; never retry timeout or change financial selection/exit for delivery failure.

#### Scenario: Failure notification
- **WHEN** a failure persists or a grouped action notification is due
- **THEN** the run reports confirmed, failed or unconfirmed delivery; failures use `Failure notification sent` on confirmed delivery.

### Requirement: Schedule

`CRON` SHALL schedule imports; absent runs once; invalid exits 1.

#### Scenario: Schedule
- **WHEN** `CRON=bad`
- **THEN** `Invalid CRON`, exit 1.

### Requirement: Persistent operator review

`ACTIVITY_REVIEW_FILE` SHALL enable YAML reference/financial proposals, groups/conforming rows, exact before/after/changed-fields/source/target/evidence/authority/status/block. Initialize only after valid acquisition. Unsafe paths/permissions/links/input-overlap/concurrency/unavailable-evidence: `review_unavailable` before writes. Preserve recovery evidence. Only `decision: yes` approves existing unchanged eligible proposals; `reject` rejects that pair without writes. Preserve unchanged choices; changed evidence invalidates. Invalidated rejections/rebuilt evidence never grant immediate automatic authority. Blocked `yes` stays blocked. Hold related imports only.

#### Scenario: Consent
- **WHEN** `yes` evidence changes
- **THEN** clear consent; no execution.

### Requirement: Source-proven correction fields

Pair validated event/activity within the same active account/type/YAHOO security/EUR, except the manually approved coupon currency replacement below. ISIN conflicts/competing candidates SHALL block pairs; exact references win. Fees/order/aggregates never prove identity. Change only proved date/price/fee/reference, plus the manual coupon quantity/currency fields below; preserve ID/owner/account/security/type/tags/notes and BUY/SELL quantity. Preserve currency except for the manual coupon replacement below. DIVIDEND SHALL retain validated net, quantity 1. Report quantity differences/groups; never merge/split/delete. Legacy migration SHALL require reproducible event/account proof; otherwise `review_evidence`. Migrate comments alone; assess financial corrections later.

#### Scenario: Separate migration
- **WHEN** finds proved legacy ownership plus a fee discrepancy
- **THEN** it changes only the comment; another run evaluates fee.

### Requirement: Explicit reconciliation profiles

`ACTIVITY_RECONCILIATION` SHALL accept `off`(default)/`conservative`/`balanced`/`permissive`. Non-off requires review file+explicit IANA `TZ`; otherwise `invalid_configuration`. Off retains manual/TTF/recovery authority without TZ. Profiles never create `yes`. Require mutually unique pairs; conservative requires recognized unique reference; others permit unreferenced pairs.

| Profile | Absolute gross | Relative | Date distance |
| --- | --- | --- | --- |
| conservative | 0 EUR | 0 | 0 days |
| balanced | 0.01 EUR | 0.1% | 0 days |
| permissive | 1 EUR | 1% | BUY/SELL 2; DIVIDEND 3 days |

Require both limits: exact positive quantity×price gross without fees; source-relative. Validate fees independently without matching limit. No FX/residue exception. Compare printed source/destination dates in `TZ`; write midnight UTC; show dates/instants. Outside-limit eligible pairs remain manually reviewable.

#### Scenario: Threshold
- **WHEN** pair at/beyond limits
- **THEN** automatic selection requires both limits.

### Requirement: Bounded corrections and durable uncertainty

Apply every eligible manual/profile/migration/TTF correction, oldest first; stable ties; imports stay uncapped. Simulation SHALL show `would correct`. Persist before/after/authority before PUT. Next PUTs require exact changed/preserved-field readback and D=150 seconds after confirmation. Qualify D in labs. A new release raises D when the lab margin no longer passes. Uncertainty SHALL retain approvals and hold account writes across restarts without resend. Only exact confirmation settles pending; other evidence/settings/simulation/file changes SHALL NOT settle it.

#### Scenario: Restart
- **WHEN** an uncertain correction resumes
- **THEN** retain the hold until exact confirmation; never retry or double count.

### Requirement: Review delivered implementations

Agents SHALL review delivered commit-pinned IBKR/BD code/tests/proofs before implementation. Record reuse/adaptations/gaps/acceptance-commands in Beads. Contradictions block affected work.

#### Scenario: Review missing
- **WHEN** comparison missing
- **THEN** affected work unstarted.

### Requirement: Account statements in the source

Folder/Paperless monthly statements SHALL use title+opening/closing `Solde au` recognition; count them; never create/correct/hold activities or give `notice_unreadable`. Other unsupported PDFs/securities statements retain `notice_unreadable`.

#### Scenario: Statement with notices
- **WHEN** notices/statement coexist
- **THEN** count statement; notices unaffected.

#### Scenario: Unknown PDF
- **WHEN** PDF unsupported
- **THEN** `notice_unreadable`, no writes.

### Requirement: Opt-in cash balance

`CASH_BALANCE` SHALL accept absent/0 (no amount read/write, `cash=not managed`) or 1; otherwise `invalid_configuration CASH_BALANCE` before service access.

Select `BD_ACCOUNT_REF` statements under notice rules; count/ignore others. Validate opening+movements=closing; consecutive opening=previous closing. Cash SHALL equal latest closing+later same-account BUY/SELL/coupon net, exact decimal EUR cents. Target SHALL be EUR.

Simulation logs closing-date/later-notice-count/proposed-cash without writes. Live SHALL write balance only, once, preserve other fields, confirm readback; equal balances: no write. Report `cash=simulated|unchanged|updated|unavailable`.

Unreadable Paperless documents block cash unless reliably dated strictly before latest closing; unreadable folder files block. No/malformed/inconsistent statements, broken chains, currency mismatch or unconfirmed write SHALL give `cash_unavailable`, exit 0 with user action. No cash write; preserve activity selection/imports/exit. Cash logs: dates/counts/amounts only; omit statement text/holder/address.

#### Scenario: Cash
- **WHEN** closing=348.66 EUR, later BUY=120.00 EUR net
- **THEN** simulate/store/readback 228.66 EUR.

#### Scenario: Off
- **WHEN** setting absent
- **THEN** no cash read/write; `cash=not managed`.

#### Scenario: Inconsistent statement
- **WHEN** reconciliation fails
- **THEN** `cash_unavailable`; activities unaffected.

#### Scenario: Invalid setting
- **WHEN** `CASH_BALANCE=yes`
- **THEN** `invalid_configuration CASH_BALANCE`, exit 1 before access.

#### Scenario: Old unreadable document
- **WHEN** Paperless date strictly precedes closing
- **THEN** no cash block; activity protections remain.

#### Scenario: Relevant unreadable document
- **WHEN** date unknown/at/after closing, or folder unreadable
- **THEN** cash blocked.

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

Position statements SHALL NOT supply position evidence. Monthly account statements only supply cash under the opt-in cash requirements. Absolute
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

### Requirement: Safe read-only folder acquisition

The folder SHALL be mounted read-only. The importer SHALL never modify originals,
create markers, move files or write review state inside the source directory.
It SHALL select immediate regular files with case-insensitive `.pdf` extension.
It SHALL NOT recurse. Other entries SHALL be ignored and counted as ignored.
Each selected PDF SHALL contain 1 through 20,971,520 bytes (20 MiB).
Selected PDF symlinks, non-regular PDF entries, links in the configured directory
path, empty or oversized PDFs SHALL give `notice_unreadable`, exit 1, and block
all financial writes. Links SHALL NOT be followed.

A missing, unreadable or unlistable directory, or incomplete/changed acquisition
before dispatch SHALL give `notice_source_unavailable`, exit 1, and block all
financial writes. A selected file that cannot be read SHALL give
`notice_unreadable` with the same block. Readable previews can remain available;
coverage SHALL state incomplete evidence. The new code SHALL use the existing
redacted failure-notification rules. Notifications SHALL omit paths and names.

#### Scenario: Uppercase PDF and other entries
- **WHEN** Run reads one valid `.PDF`, a text file and a nested directory
- **THEN** only the PDF supplies rows; the other entries are counted as ignored.

#### Scenario: Unsafe PDF entry
- **WHEN** Run selects a PDF symlink, special file, empty file or file above 20 MiB
- **THEN** `notice_unreadable`, no financial writes, exit 1.

#### Scenario: Incomplete folder acquisition
- **WHEN** Run cannot enumerate the directory or a selected file changes during acquisition
- **THEN** `notice_source_unavailable`, no financial writes, exit 1; coverage is incomplete.

### Requirement: Content identity without duplicate creation

A folder document SHALL use `sha256:<digest of original PDF bytes>` as its
document identity. Its path, name, directory order and timestamps SHALL NOT
define identity. Identical copies SHALL share one document identity. Report
source-file and distinct-document counts separately. Preserve existing
source-copy counting for historical exclusions.

Financial activity identity SHALL remain `BD#v3` under the existing row rules.
Neither the content hash nor source mode SHALL change it. Equal logical events
in byte-different regenerated PDFs SHALL retain existing duplicate checks.
Renaming, moving to another configured folder, copying, or switching sources
SHALL NOT create an already represented activity. Confirmed destination evidence,
not a file marker, SHALL prove completion. Every run SHALL read selected PDFs again.

#### Scenario: Copy and repeat
- **WHEN** Run follows a confirmed import with renamed and duplicate copies of its original
- **THEN** repeated events are duplicates, zero creations, and originals remain unchanged.

#### Scenario: Regenerated or switched source
- **WHEN** Run finds an already represented event through a regenerated PDF or the other source
- **THEN** its financial identity is unchanged and no replacement activity is created.

### Requirement: Folder dates and source-independent review

In folder mode, `IMPORT_CREATE_FROM` SHALL compare each row's printed trade or
payment date from the PDF. Never use file metadata. Earlier rows SHALL remain
available for review and coverage but SHALL NOT become creations or simulated
holdings. The boundary day SHALL remain eligible. Existing historical-stop
rules and correction authority SHALL remain unchanged.

`ACTIVITY_REVIEW_FILE` SHALL provide the same proposals, holds, approvals,
recovery and exact readback in both modes. Source and review paths SHALL remain
separate; unsafe overlap SHALL give `review_unavailable` before financial writes.
A rename of unchanged bytes SHALL NOT change source evidence. Changed content,
association or destination evidence SHALL invalidate consent under existing rules.
Switching sources SHALL NOT itself authorize corrections or settle pending work.

#### Scenario: Printed date wins
- **WHEN** Run reads old and boundary-day folder rows whose filenames and mtimes suggest opposite dates
- **THEN** only the boundary-day row can become a creation; historical review remains available.

#### Scenario: Rename versus changed evidence
- **WHEN** Run refreshes review after a rename, then after a content change
- **THEN** the rename retains unchanged evidence; changed evidence clears stale consent.

### Requirement: Folder coverage parity

`NOTICE_COVERAGE=1` SHALL read all selected folder originals. On the same supported
originals and destination, both sources SHALL produce the same logical findings
and exact values. Acquisition counts and source identifiers can differ.
Existing conforming, correction, unresolved, absent, unsupported, unreadable and
position findings SHALL remain available. No source mode SHALL claim complete
broker history. Paperless tag waivers SHALL NOT transfer to folder mode.
Unreadable or incomplete acquisition SHALL retain its failure and incomplete status.
Coverage SHALL send no financial POST/PUT/DELETE, open or settle no review journal,
and change no review decision, including with `DRY_RUN=0`, `yes` or pending work.

#### Scenario: Same originals through both sources
- **WHEN** Run reports coverage through each source on the same supported originals and destination
- **THEN** logical findings and values agree; review decisions and journals stay unchanged.

#### Scenario: Coverage with approvals and an unreadable file
- **WHEN** Run uses folder coverage with `DRY_RUN=0`, approvals, pending work and an unreadable PDF
- **THEN** no financial writes or journal settlement; `notice_unreadable`, incomplete coverage, exit 1.

### Requirement: Clear diagnostic status

The connector SHALL log `custody_fee_ignored` at INFO. The message SHALL keep the document reference and row count. Import selection, exit status, and notification rules SHALL stay unchanged.

When `ACTIVITY_RECONCILIATION=off` and `ACTIVITY_REVIEW_FILE` is unset, the reconciliation and review summaries SHALL state `disabled`. They SHALL NOT present unavailable review counts as measured zeros.

When review is configured but no result is available, the summaries SHALL state `unavailable`. Measured results SHALL retain their exact counts, including zero, and the overlap information. A profile set to `off` with a review file SHALL NOT be reported as disabled: manual review remains available.

#### Scenario: Informational custody fee

- **WHEN** a run reads a retained custody-fee notice
- **THEN** it logs `custody_fee_ignored` at INFO, with the document reference and row count; activity selection and exit status stay unchanged.

#### Scenario: Review disabled

- **WHEN** a run uses profile `off` without a review file
- **THEN** both summaries state `disabled`; they do not present review counts as measured zeros.

#### Scenario: Review result unavailable

- **WHEN** a run has a review file but fails before review produces counts
- **THEN** both summaries state `unavailable`; the existing failure remains visible.

#### Scenario: Measured review result

- **WHEN** review completes with a review file, including with profile `off`
- **THEN** the summaries report the measured counts and overlap information; a measured zero stays zero.

### Requirement: Safe reason for a coupon without an ISIN

For a recognized `COUPONS` row with no ISIN, the connector SHALL retain `notice_unreadable` and add the fixed local diagnostic `reason=missing_isin` with the document reference. The reason SHALL contain no source text, holder data, account reference, or inferred security.

All existing unreadable-source protections SHALL remain in effect. A historical Paperless notice with a reliably proved date before the creation cut-off SHALL remain excluded from normal writes. Coverage SHALL still report incomplete evidence. Other unreadable inputs SHALL retain their existing diagnostic and write protection. Notification content and grouping SHALL stay unchanged.

#### Scenario: Historical coupon without an ISIN

- **WHEN** a run reads the retained coupon without an ISIN and proves its date precedes the creation cut-off
- **THEN** it reports `notice_unreadable`, `reason=missing_isin`, and the document reference; it excludes that notice and preserves eligibility for independent recent activities.

#### Scenario: Coupon without a safe historical date

- **WHEN** the same coupon has no reliable date or a date at or after the creation cut-off
- **THEN** the run reports the fixed reason and retains the existing activity-write block and failure status.

#### Scenario: Other unreadable source

- **WHEN** an input is unreadable for another reason
- **THEN** the run does not claim `missing_isin`; it keeps the existing failure and write protection.

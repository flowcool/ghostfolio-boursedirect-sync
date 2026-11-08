# notice-import Specification

## Purpose

Import Bourse Direct PDF BUY/SELL/DIVIDEND notices into one Ghostfolio account/container.

Run: `docker compose run --rm -T <service>`. Paperless notices: `Source = Bourse Direct`; optional `PAPERLESS_DONE_TAG`.

## Requirements

### Requirement: Settings from ENV only

ENV requires `GHOST_HOST`, `GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`, `PAPERLESS_URL`, `PAPERLESS_TOKEN`; optional `PAPERLESS_DONE_TAG` (default `ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`, `LOG_LEVEL`, `ACTIVITY_REVIEW_FILE`, `ACTIVITY_RECONCILIATION`. Invalid settings/nonunique/inactive/excluded targets SHALL give `invalid_configuration`. Omit secrets.

#### Scenario: Missing token
- **WHEN** token missing
- **THEN** `invalid_configuration`, `PAPERLESS_TOKEN`, exit 1.

#### Scenario: Ambiguous account
- **WHEN** names collide
- **THEN** `invalid_configuration`, exit 1.

### Requirement: Usable Ghostfolio evidence

Incomplete/masked/invalid evidence gives `activities_unavailable` before selection/writes. assetProfile precedes SymbolProfile. Draft/excluded/non-YAHOO identities count without holdings/matches. Future events defer: `future_activity`.

#### Scenario: Unsafe activity evidence
- **WHEN** evidence masked
- **THEN** `activities_unavailable`, no writes.

#### Scenario: Excluded target
- **WHEN** target excluded
- **THEN** `invalid_configuration`, exit 1.

#### Scenario: Future activity
- **WHEN** date future
- **THEN** `future_activity`, exit 1; current BUY remains eligible.

### Requirement: Simulation by default

`DRY_RUN=0` enables financial writes; absent/1 simulates; otherwise `invalid_configuration`. Review refresh/action notifications remain available.

#### Scenario: Simulated BUY
- **WHEN** BUY simulated
- **THEN** `DRY RUN`, exact fields.

### Requirement: Paperless source

Read all originals; Paperless stays read-only. Rejected tokens give `paperless_auth_failed`; unexpected answers, `paperless_unreachable`. Errors show only HTTP status/code/document ID. Omit holder/address; account references only in identity comments/logs. `BourseDirect_` files without `Source = Bourse Direct` SHALL stop writes with `source_field_missing`.

#### Scenario: Wrong Paperless token
- **WHEN** token rejected
- **THEN** `paperless_auth_failed`, exit 1.

#### Scenario: Paperless down
- **WHEN** service unavailable
- **THEN** `paperless_unreachable`, exit 1.

#### Scenario: Source field missing
- **WHEN** Source missing
- **THEN** `source_field_missing`, no writes.

### Requirement: Account selection

Before target selection: one labelled account/notice; remove spaces once; match `BD_ACCOUNT_REF`; count others. Missing/multiple: `notice_unreadable`.

#### Scenario: Other account
- **WHEN** accounts differ
- **THEN** selected rows; others counted.

### Requirement: Unreadable documents block writes

Unreadable notices/accounts/unknown labels SHALL stop activity writes: `notice_unreadable`. Simulation lists readable activities.

#### Scenario: Unreadable document
- **WHEN** PDF unreadable
- **THEN** `notice_unreadable`, no writes.

### Requirement: Amount checks

Amounts SHALL be EUR. BUY/SELL: abs(QUANTITE)×COURS, HALF_UP cents, equals BRUT; preserve quantity/price. BUY debit SHALL equal BRUT+COURTAGE+TVA; SELL credit, BRUT−COURTAGE−TVA; TVA SHALL equal zero. Missing BUY brokerage means zero only with explicit TVA=0 and Debit=BRUT: `brokerage_zero_inferred`. Coupons require positive EUR credits; otherwise `amount_check_failed`, affected rows withheld.

#### Scenario: Altered amount
- **WHEN** BRUT inconsistent
- **THEN** `amount_check_failed`, exit 1.

#### Scenario: Rounded gross
- **WHEN** fractional-cent gross
- **THEN** HALF_UP matches; values preserved.

#### Scenario: Omitted brokerage
- **WHEN** qualifying COURTAGE omitted
- **THEN** `brokerage_zero_inferred`, zero fee.

### Requirement: Activity content

BUY/SELL: absolute quantity, source price, EUR, printed date midnight UTC; fee=brokerage+attributed BUY TTF. DIVIDEND: quantity 1, net credit, fee 0. Identity: `BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`; KIND=type; key=broker reference, otherwise normalized rows+occurrence rank. Ignore file metadata. Permit notes after blank separator.

#### Scenario: Simulated coupon
- **WHEN** coupon simulated
- **THEN** DIVIDEND, quantity 1, net, fee 0.

### Requirement: Charged TTF attribution

Charged TTF requires exactly one BUY within account/notice/date/ISIN. Never estimate/allocate. Ambiguity: `ttf_attribution_failed`; hold affected BUYs, continue independent events.

#### Scenario: Attributed TTF
- **WHEN** TTF unique
- **THEN** brokerage+TTF; quantity/price preserved.

#### Scenario: Ambiguous TTF
- **WHEN** TTF ambiguous
- **THEN** `ttf_attribution_failed`, BUYs held.

### Requirement: Security resolution

Resolve ISIN through `MAPPING_FILE.symbol_mapping`, then unique EUR lookup. Otherwise hold ISIN with `unresolved_security` and mapping hint. Nonempty missing/invalid mapping SHALL give `invalid_mapping`.

#### Scenario: Nonunique lookup
- **WHEN** lookup nonunique
- **THEN** `unresolved_security`, mapping hint.

### Requirement: No duplicate activity

Duplicate: identical account/identity/date/type/security/currency/quantity/price/fee. Compare identity first lines; preserve notes. Moved/conflicting identities SHALL give `owned_activity_conflict`, except eligible corrections. Both modes match unchanged legacy/unowned trades by side/security(or ISIN)/quantity/price within two days: maximize one-to-one matches, minimize distance. Dividends match security/net within three days. Other nearby values give `possible_duplicate`. Never import review-held events. Malformed/unsupported reserved identities SHALL stop writes with `invalid_identity`; read valid v1/v2 without assuming migration ownership. Unproved optional migrations never make unchanged duplicates required actions.

#### Scenario: Regenerated notice
- **WHEN** copies regenerated
- **THEN** same identities, no duplicates.

#### Scenario: Moved identity
- **WHEN** identity moved
- **THEN** `owned_activity_conflict`, no recreation.

#### Scenario: Invalid identity
- **WHEN** identity malformed
- **THEN** `invalid_identity`, no writes.

#### Scenario: Second run
- **WHEN** inputs repeated
- **THEN** only duplicates, zero creations.

#### Scenario: Existing coupon
- **WHEN** legacy coupon matches
- **THEN** duplicate, no DIVIDEND creation.

### Requirement: Sell guard

Current holdings+chronological new rows; equal dates SELL first; no replay. Negative positions hold SELL: `sell_exceeds_holding`.

#### Scenario: Insufficient holdings
- **WHEN** holdings insufficient
- **THEN** `sell_exceeds_holding`, exit 1.

### Requirement: Custody fees ignored

Custody fees: `custody_fee_ignored`; import/exit unchanged.

#### Scenario: Custody fee
- **WHEN** custody fee present
- **THEN** `custody_fee_ignored`, SELL unaffected.

### Requirement: Stop on a share-count change

DIVISION SHALL give `share_count_change`; unknown operations, `unknown_operation`. ISIN holds span notices; independent securities continue. `PAPERLESS_DONE_TAG` SHALL waive these codes for that document only; other rows remain eligible.

#### Scenario: DIVISION/coupon
- **WHEN** DIVISION unwaived
- **THEN** `share_count_change`, coupon held.

#### Scenario: Stop cleared
- **WHEN** document waived
- **THEN** coupon eligible, hold cleared.

### Requirement: Additive writes with readback

Never delete. Only specified corrections update. Confirm imports once with identical account/comment/symbol/data-source/date/type/quantity/price/fee/currency. Permit delayed readback, never resend. Incomplete/conflicting/extra evidence: `import_unconfirmed`, stop writes. Only confirmed rows advance holdings.

#### Scenario: Unexpected import response
- **WHEN** confirmation absent
- **THEN** `import_unconfirmed`, no resend.

#### Scenario: Delayed confirmation
- **WHEN** delayed evidence exact
- **THEN** confirmed once; execution continues.

### Requirement: Exact BUY fee correction

Fee-only correction requires one account/date/security/quantity/price-matched BUY, brokerage-only fee, unique charged TTF. `ttf` authority includes exact unowned matches without `yes`; preserve comments bytes. Correct fees: no-op. Persistent review required even with profile `off`; unset file holds BUY: `review_evidence`; independent imports continue. Share budget/recovery below. Exact readback required; uncertainty: `import_unconfirmed`, no resend/double-counted TTF.

#### Scenario: Brokerage-only BUY
- **WHEN** file usable, TTF proved
- **THEN** fee-only update; repeat unchanged.

#### Scenario: Missing review
- **WHEN** review file unset
- **THEN** `review_evidence`, independent imports continue.

### Requirement: Exit code, summary and notification

Report `success`, `success with user action required`, or `failure` at INFO/WARNING/ERROR. Classify codes:

| Exit | Codes |
| --- | --- |
| 0, action | `review_approval`, `review_evidence` |
| 0, information | `custody_fee_ignored`, `brokerage_zero_inferred` |
| 1, failure | `invalid_configuration`, `invalid_mapping`, `paperless_auth_failed`, `paperless_unreachable`, `source_field_missing`, `notice_unreadable`, `amount_check_failed`, `activities_unavailable`, `unresolved_security`, `owned_activity_conflict`, `possible_duplicate`, `invalid_identity`, `sell_exceeds_holding`, `share_count_change`, `unknown_operation`, `future_activity`, `import_unconfirmed`, `ghostfolio_auth_failed`, `ttf_attribution_failed`, `ghostfolio_unreachable`, `unhandled_error`, `review_unavailable` |

Count imports/simulations/duplicates/conforming/corrections/migrations/holds/deferred/delivery; mark unavailable/overlap. Actions include reason/scope/impact/next-step/resolution, including imported events. Apprise: at most one redacted failure/action summary/run, including simulation; repeat unresolved actions; clean runs silent. Omit identifiers/securities/amounts/paths/secrets. Report sent/failed/unconfirmed; never retry timeout; delivery failure preserves financial selection/exit.

#### Scenario: Failure notification
- **WHEN** failure/action persists
- **THEN** `Failure notification sent` on delivery; otherwise failed/unconfirmed.

### Requirement: Schedule

`CRON` schedules imports; absent runs once; invalid exits 1.

#### Scenario: Invalid schedule
- **WHEN** `CRON=bad`
- **THEN** `Invalid CRON`, exit 1.

### Requirement: Persistent operator review

`ACTIVITY_REVIEW_FILE`: YAML reference/financial proposals, groups/conforming rows, exact before/after/changed-fields/source/target/evidence/authority/status/block. Initialize only after valid acquisition. Unsafe paths/permissions/links/input-overlap/concurrency/unavailable-evidence: `review_unavailable` before writes. Preserve recovery evidence. Only `decision: yes` approves existing unchanged eligible proposals; `reject` changes no activity. Preserve unchanged choices; changed evidence invalidates. Invalidated rejections/rebuilt evidence never grant immediate automatic authority. Blocked `yes` stays blocked. Hold related imports only.

#### Scenario: Changed consent
- **WHEN** `yes` evidence changes
- **THEN** clear consent; no execution.

### Requirement: Source-proven correction fields

Pair validated events/activities: same active account/type/YAHOO-security/EUR. Block ISIN conflicts/competing candidates; exact references win. Fees/order/aggregates never prove identity. Replace only proved date/price/fee/reference; preserve ID/owner/account/security/type/currency/tags/notes/BUY-SELL-quantity. DIVIDEND keeps validated net, quantity 1. Report quantity/group differences; never merge/split/delete. Legacy migration requires reproducible event/account proof; otherwise `review_evidence`. Separate comment migrations from financial corrections.

#### Scenario: Separate migration
- **WHEN** legacy ownership proved, fee differs
- **THEN** comment only; fee next run.

### Requirement: Explicit reconciliation profiles

`ACTIVITY_RECONCILIATION`: `off`(default)/`conservative`/`balanced`/`permissive`. Non-off requires review file+explicit IANA `TZ`; otherwise `invalid_configuration`. Off retains manual/TTF/recovery authority without TZ. Profiles never create `yes`. Require mutually unique pairs; conservative requires recognized unique reference; others permit unreferenced pairs.

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

Apply all eligible manual/profile/migration/TTF corrections oldest-first, stable ties; imports uncapped. Simulation: `would correct`. Persist before/after/authority before PUT. Next PUT requires exact changed/preserved-field readback+D=150 seconds after confirmation. Qualify D in labs; raise D next release if margin fails. Uncertainty retains approvals, holds account writes across restarts, never resends. Only exact confirmation settles pending; other evidence/settings/simulation/file changes cannot.

#### Scenario: Restart
- **WHEN** uncertain correction resumes
- **THEN** hold until exact confirmation; no retry/double-count.

### Requirement: Review delivered implementations

Before implementation review delivered commit-pinned IBKR/BD code/tests/proofs. Record reuse/adaptations/gaps/acceptance-commands in Beads. Contradictions block affected work.

#### Scenario: Missing review
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

Unreadable Paperless documents block cash unless reliably dated strictly before latest closing; folder files block. No/malformed/inconsistent statements, broken chains, currency mismatch or unconfirmed write SHALL give `cash_unavailable`, exit 0 with user action. No cash write; preserve activity selection/imports/exit. Omit statement-text/holder/address.

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

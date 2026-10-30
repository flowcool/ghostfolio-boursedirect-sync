# notice-import

`Run` means `docker compose run -T --no-deps importer` with inputs; report exit status. Retain containers/proof.

## MODIFIED Requirements

### Requirement: Settings from ENV only

ENV SHALL supply `GHOST_HOST`, `GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`, `PAPERLESS_URL`, `PAPERLESS_TOKEN`; optional `PAPERLESS_DONE_TAG` (default `ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`, `LOG_LEVEL`, `ACTIVITY_REVIEW_FILE`, `ACTIVITY_RECONCILIATION`. Invalid settings/nonunique/inactive/excluded targets SHALL give `invalid_configuration`. Omit secrets.

#### Scenario: Missing Paperless token
- **WHEN** token missing
- **THEN** `invalid_configuration`, `PAPERLESS_TOKEN`, exit 1.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** names collide
- **THEN** `invalid_configuration`, exit 1.

### Requirement: Usable Ghostfolio evidence

Incomplete/masked/invalid evidence SHALL give `activities_unavailable` before selection/writes. assetProfile SHALL precede SymbolProfile. Draft/excluded/non-YAHOO rows SHALL occupy identities without supporting holdings/matches. Future events SHALL defer with `future_activity`.

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

`DRY_RUN=0` SHALL enable financial writes; absent/1 SHALL simulate without financial writes. Otherwise `invalid_configuration`. Review refresh/action notifications SHALL remain available.

#### Scenario: Real BUY in simulation
- **WHEN** BUY simulated
- **THEN** `DRY RUN`, exact fields.

### Requirement: Paperless source

Read all original notices; Paperless SHALL remain read-only. Rejected tokens SHALL give `paperless_auth_failed`; unexpected answers, `paperless_unreachable`. Errors SHALL show only HTTP status/code/document ID. Omit holder/address; account references appear only in identity comments/logs. `BourseDirect_` files without `Source = Bourse Direct` SHALL stop writes with `source_field_missing`.

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

Before target selection require one labelled account/notice. Remove spaces once; match `BD_ACCOUNT_REF`. Count other accounts. Missing/multiple accounts SHALL give `notice_unreadable`.

#### Scenario: Notice of another account
- **WHEN** accounts differ
- **THEN** selected rows; others counted.

### Requirement: Unreadable documents block writes

Unreadable notices/accounts or unknown field labels SHALL stop all writes with `notice_unreadable`. Simulation SHALL list readable activities.

#### Scenario: Unreadable document
- **WHEN** PDF unreadable
- **THEN** `notice_unreadable`, no writes.

### Requirement: Amount checks

All amounts SHALL be EUR. For BUY/SELL, abs(QUANTITE) × COURS rounded HALF_UP to cents SHALL equal BRUT. Keep quantity/price. BUY debit SHALL equal BRUT+COURTAGE+TVA; SELL credit, BRUT−COURTAGE−TVA; TVA SHALL equal zero. Missing BUY brokerage SHALL mean zero with explicit TVA=0 and Debit=BRUT: `brokerage_zero_inferred`. Coupons SHALL be positive EUR credits. Otherwise report `amount_check_failed`, without importing affected rows.

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

BUY/SELL SHALL use absolute quantity, source price, EUR, printed date at midnight UTC. Fee SHALL equal brokerage plus attributed BUY TTF. DIVIDEND SHALL use quantity 1, net credit, fee 0. Identity SHALL be `BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`; KIND equals type; key uses broker reference, otherwise normalized rows with occurrence rank. Ignore file metadata for identity. Identity first lines SHALL permit notes after a blank separator.

#### Scenario: Real coupon in simulation
- **WHEN** coupon simulated
- **THEN** DIVIDEND, quantity 1, net, fee 0.

### Requirement: Charged TTF attribution

Charged TTF SHALL attach to exactly one BUY within source account/notice/date/ISIN. Never estimate/allocate. Ambiguity SHALL give `ttf_attribution_failed`, holding affected BUYs while independent events continue.

#### Scenario: Attributed TTF
- **WHEN** TTF unique
- **THEN** brokerage+TTF; quantity/price preserved.

#### Scenario: Ambiguous TTF
- **WHEN** TTF ambiguous
- **THEN** `ttf_attribution_failed`, BUYs held.

### Requirement: Security resolution

Resolve ISIN through `MAPPING_FILE.symbol_mapping`, then unique EUR lookup. Otherwise hold ISIN with `unresolved_security` and mapping hint. Nonempty missing/invalid mapping SHALL give `invalid_mapping`.

#### Scenario: No EUR lookup result
- **WHEN** lookup nonunique
- **THEN** `unresolved_security`, mapping hint.

### Requirement: No duplicate activity

Identical account/identity/date/type/security/currency/quantity/price/fee SHALL mean duplicate. Compare identity first lines; preserve notes. Moved/conflicting identities SHALL give `owned_activity_conflict`, except eligible corrections. In both modes, unchanged legacy/unowned trades SHALL match same side/security (or ISIN)/quantity/price within two days: maximize one-to-one matches, then minimize distance. Dividends SHALL match same security/net within three days. Other nearby values give `possible_duplicate`. Review-held events SHALL NOT become imports. Malformed/unsupported reserved identities SHALL stop writes with `invalid_identity`; read valid v1/v2 without assuming migration ownership. Optional unproved migration SHALL NOT turn unchanged duplicates into required actions.

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

#### Scenario: Coupon already in Ghostfolio
- **WHEN** legacy coupon matches
- **THEN** duplicate, no DIVIDEND creation.

### Requirement: Sell guard

Use current holdings plus chronological new rows, SELL first on equal dates. No replay. Negative positions SHALL hold SELL with `sell_exceeds_holding`.

#### Scenario: Sell without a position
- **WHEN** holdings insufficient
- **THEN** `sell_exceeds_holding`, exit 1.

### Requirement: Custody fees ignored

Custody fees SHALL produce `custody_fee_ignored`, without import/exit change.

#### Scenario: Sell notice with a custody fee
- **WHEN** custody fee present
- **THEN** `custody_fee_ignored`, SELL unaffected.

### Requirement: Stop on a share-count change

DIVISION SHALL give `share_count_change`; unknown operations, `unknown_operation`. With ISIN, hold that security across notices; independent securities continue. `PAPERLESS_DONE_TAG` SHALL waive these codes for that document only; other rows remain eligible.

#### Scenario: Division and coupon in one notice
- **WHEN** DIVISION unwaived
- **THEN** `share_count_change`, coupon held.

#### Scenario: Stop cleared
- **WHEN** document waived
- **THEN** coupon eligible, hold cleared.

### Requirement: Additive writes with readback

Never delete. Only specified corrections SHALL update. Imports SHALL confirm once with identical account/comment/symbol/data-source/date/type/quantity/price/fee/currency. Uncertainty SHALL permit delayed readback, never resend. Incomplete/conflicting/extra evidence SHALL stop writes with `import_unconfirmed`; only confirmed rows advance holdings.

#### Scenario: Unexpected import response
- **WHEN** confirmation absent
- **THEN** `import_unconfirmed`, no resend.

#### Scenario: Delayed confirmation
- **WHEN** delayed evidence exact
- **THEN** confirmed once; execution continues.

### Requirement: Exact BUY fee correction

One account/date/security/quantity/price-matched BUY with brokerage-only fee and unique charged TTF SHALL qualify for fee-only correction. Dedicated `ttf` authority SHALL include exact unowned matches without `yes`; preserve comments byte-for-byte. Correct fees: no-op. Persistent review SHALL be required, including profile `off`. An unset file SHALL hold that BUY with `review_evidence`; independent imports continue. Share budget/recovery below. Confirm exact readback; uncertainty SHALL give `import_unconfirmed`, without resend or double-counted TTF.

#### Scenario: Existing brokerage-only BUY
- **WHEN** file usable, TTF proved
- **THEN** fee-only update; repeat unchanged.

#### Scenario: Missing correction file
- **WHEN** review file unset
- **THEN** `review_evidence`, independent imports continue.

### Requirement: Exit code, summary and notification

Report `success`, `success with user action required`, or `failure` at INFO/WARNING/ERROR. Classify codes:

| Exit | Codes |
| --- | --- |
| 0, action | `review_approval`, `review_evidence` |
| 0, information | `custody_fee_ignored`, `brokerage_zero_inferred` |
| 1, failure | `invalid_configuration`, `invalid_mapping`, `paperless_auth_failed`, `paperless_unreachable`, `source_field_missing`, `notice_unreadable`, `amount_check_failed`, `activities_unavailable`, `unresolved_security`, `owned_activity_conflict`, `possible_duplicate`, `invalid_identity`, `sell_exceeds_holding`, `share_count_change`, `unknown_operation`, `future_activity`, `import_unconfirmed`, `ghostfolio_auth_failed`, `ttf_attribution_failed`, `ghostfolio_unreachable`, `unhandled_error`, `review_unavailable` |

Count imports/simulations/duplicates/conforming/corrections/migrations/holds/deferred work/delivery; mark unavailable/overlapping counts. Actions SHALL state reason/scope/impact/next-step/resolution, including imported events. Apprise SHALL send at most one redacted failure/action summary/run, including simulation; repeat unresolved actions; clean runs stay silent. Omit identifiers/securities/amounts/paths/secrets. Report sent/failed/unconfirmed; never retry timeout or change financial selection/exit for delivery failure.

#### Scenario: Failure notification
- **WHEN** failure/action persists
- **THEN** `Failure notification sent` on delivery; otherwise failed/unconfirmed.

### Requirement: Schedule

Valid `CRON` SHALL schedule imports; absence runs once; invalid values exit 1.

#### Scenario: Invalid schedule
- **WHEN** `CRON=bad`
- **THEN** `Invalid CRON`, exit 1.

## ADDED Requirements

### Requirement: Persistent operator review

`ACTIVITY_REVIEW_FILE` SHALL enable YAML reference/financial proposals, groups and conforming rows with exact before/after, changed fields, source/target, evidence, authority/status/block. Initialize after valid acquisition only. Unsafe paths/permissions/links/input overlap/concurrency/unavailable evidence SHALL give `review_unavailable` before financial writes. Preserve recovery evidence. Only `decision: yes` SHALL approve unchanged eligible proposals already present; `reject` rejects that pair without activity changes. Preserve unchanged choices; invalidate changed evidence. Invalidated rejections/rebuilt evidence SHALL NOT grant immediate automatic authority. Blocked `yes` SHALL remain blocked. Hold related imports only.

#### Scenario: Changed consent
- **WHEN** reads `yes` with changed evidence
- **THEN** it clears consent without executing that proposal.

### Requirement: Source-proven correction fields

Pair validated event/activity within the same active account/type/YAHOO security/EUR. ISIN conflicts/competing candidates SHALL block pairs; exact references win. Fees/order/aggregates never prove identity. Change only proved date/price/fee/reference; preserve ID/owner/account/security/type/currency/tags/notes and BUY/SELL quantity. DIVIDEND SHALL retain validated net, quantity 1. Report quantity differences/groups; never merge/split/delete. Legacy migration SHALL require reproducible event/account proof; otherwise `review_evidence`. Migrate comments alone; assess financial corrections later.

#### Scenario: Separate migration
- **WHEN** finds proved legacy ownership plus a fee discrepancy
- **THEN** it changes only the comment; another run evaluates fee.

### Requirement: Explicit reconciliation profiles

`ACTIVITY_RECONCILIATION` SHALL accept `off` (default), `conservative`, `balanced`, `permissive`. Non-off SHALL require review file and explicit IANA `TZ`, otherwise `invalid_configuration`. Off SHALL retain manual/TTF/recovery authority without requiring TZ. Profiles never create `yes`. Pairs SHALL be mutually unique; conservative requires recognized unique reference; others permit unreferenced pairs.

| Profile | Absolute gross | Relative | Date distance |
| --- | --- | --- | --- |
| conservative | 0 EUR | 0 | 0 days |
| balanced | 0.01 EUR | 0.1% | 0 days |
| permissive | 1 EUR | 1% | BUY/SELL 2; DIVIDEND 3 days |

Both limits SHALL pass: exact positive quantity×price gross, excluding fees; source-relative. Fees SHALL require independent validation without matching limit. No FX/residue exception. Compare printed source date with destination date in `TZ`; write midnight UTC. Show dates/instants. Eligible outside-limit pairs SHALL remain manually reviewable.

#### Scenario: Threshold
- **WHEN** compares pairs at/beyond either limit
- **THEN** it only selects pairs passing both limits automatically.

### Requirement: Bounded corrections and durable uncertainty

Manual/profile/migration/TTF updates SHALL share one correction per run; new imports remain uncapped. Choose oldest eligible work, stable ties. Keep deferred choices. Simulation SHALL show `would correct`. Persist before/after/authority before updating; require exact changed/preserved-field readback. Uncertainty SHALL hold all account writes across restarts without resend. Only exact confirmation SHALL settle pending work; old/missing/changed/unavailable evidence, simulation, profile changes or file removal SHALL NOT settle it.

#### Scenario: Restart
- **WHEN** resumes an uncertain correction
- **THEN** it retains the hold until exact confirmation without retry or double counting.

### Requirement: Review delivered implementations

Before implementation, agents SHALL review delivered, commit-pinned IBKR/BD code/tests/proofs. Record reuse/adaptations/gaps/acceptance-commands in Beads. Contradictions SHALL block affected work.

#### Scenario: Missing review
- **WHEN** implementation lacks this comparison
- **THEN** affected work remains unstarted.

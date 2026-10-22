# Spec Delta

## Purpose

Read Bourse Direct PDF notices from Paperless into one Ghostfolio account.
Add BUY, SELL and DIVIDEND activities. One container serves one source account.

"The run command" is `docker compose run --rm -T <service>; echo "exit=$?"`.
Run it for each configured service. "Notice documents" have Paperless custom
field `Source` exactly `Bourse Direct`, with or without `PAPERLESS_DONE_TAG`.

## ADDED Requirements

### Requirement: Settings from ENV only

The connector SHALL read its settings only from ENV. Required: `GHOST_HOST`,
`GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`,
`PAPERLESS_URL`, `PAPERLESS_TOKEN`. Optional: `PAPERLESS_DONE_TAG` (default
`ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`,
`APPRISE_TIMEOUT`, `LOG_LEVEL`. Missing or invalid settings SHALL stop with
`invalid_configuration`.
Logs SHALL omit secrets. `GHOST_ACCOUNT_NAME` SHALL match exactly one
Ghostfolio account, which SHALL be active. An excluded target SHALL give `invalid_configuration`.

#### Scenario: Missing Paperless token
- **WHEN** the run command runs without `PAPERLESS_TOKEN`
- **THEN** the output shows `invalid_configuration`, `PAPERLESS_TOKEN` and
  `exit=1`.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** two Ghostfolio accounts have the exact `GHOST_ACCOUNT_NAME`
- **THEN** the output shows `invalid_configuration` and `exit=1`.

### Requirement: Usable Ghostfolio evidence

Before selection, the connector SHALL reject incomplete or masked activity
lists and invalid values, eligibility or profiles with `activities_unavailable`,
without writes.
Current assetProfile SHALL take precedence over legacy SymbolProfile.
Draft, excluded and non-YAHOO activities SHALL not support holdings or manual
matches. Future source activities SHALL be deferred with `future_activity`.

#### Scenario: Unsafe activity evidence
- **WHEN** the run command receives incomplete, masked or invalid activity evidence
- **THEN** it shows `activities_unavailable`, 0 creations and `exit=1`.

#### Scenario: Excluded target
- **WHEN** the run command selects an excluded account
- **THEN** it shows `invalid_configuration` and `exit=1`.

#### Scenario: Future activity
- **WHEN** the run command reads a future BUY beside a current BUY
- **THEN** only the current BUY is proposed; it shows `future_activity` and `exit=1`.

### Requirement: Simulation by default

`DRY_RUN=0` SHALL send activities to Ghostfolio. `DRY_RUN=1`, or no value,
SHALL simulate. Another value SHALL give `invalid_configuration`. A simulation
SHALL log each activity to create, with all its fields. It SHALL not write to Ghostfolio or notify.

#### Scenario: Real BUY in simulation
- **WHEN** the run command runs without `DRY_RUN` on one real BUY notice
- **THEN** the output shows `DRY RUN`, a BUY line, `exit=0`.

### Requirement: Paperless source

Each run SHALL read every original notice PDF, without writing to Paperless.
Rejected tokens SHALL stop with `paperless_auth_failed`. Missing or unexpected
answers SHALL stop with `paperless_unreachable`. Logs SHALL show document IDs,
never holder names or addresses. Account numbers SHALL appear only in comments
and their log lines. Error logs SHALL show only HTTP status, error code and
document ID, never response bodies.

Original filenames starting with `BourseDirect_` without `Source = Bourse Direct`
SHALL give `source_field_missing` and stop all Ghostfolio writes.

#### Scenario: Wrong Paperless token
- **WHEN** the run command runs with an invalid `PAPERLESS_TOKEN`
- **THEN** the output shows `paperless_auth_failed` and `exit=1`.

#### Scenario: Paperless down
- **WHEN** the run command runs while Paperless is unavailable
- **THEN** the output shows `paperless_unreachable` and `exit=1`.

#### Scenario: Source field missing
- **WHEN** a Paperless document has an original file name that starts with
  `BourseDirect_` and lacks `Source = Bourse Direct`
- **THEN** the output shows `source_field_missing`, 0 activities created and
  `exit=1`.

### Requirement: Account selection

Before target selection, each notice SHALL have exactly one labelled account.
Remove spaces once and require full equality with `BD_ACCOUNT_REF`.
Import matching notices; only count other accounts. Missing or multiple labelled
accounts SHALL give `notice_unreadable`.

#### Scenario: Notice of another account
- **WHEN** the run command runs on a real BUY notice and a real notice of
  another account
- **THEN** the output shows one BUY line, 1 other-account notice and `exit=0`.

### Requirement: Unreadable documents block writes

An unreadable notice, unknown field label or unreadable account SHALL give
`notice_unreadable` and stop all Ghostfolio writes. Simulation SHALL still
list readable activities.

#### Scenario: Unreadable document
- **WHEN** the run command runs with `DRY_RUN=0` on a real BUY notice and a
  PDF that is not a notice
- **THEN** the output shows `notice_unreadable`, 0 activities created and
  `exit=1`.

### Requirement: Amount checks

For each BUY or SELL row, QUANTITE × COURS SHALL equal BRUT. A BUY debit SHALL
equal BRUT + COURTAGE + TVA. A SELL credit SHALL equal BRUT − COURTAGE − TVA.
TVA SHALL be zero. A COUPONS row SHALL be a positive credit. All amounts SHALL
be in EUR. A failed row SHALL get code `amount_check_failed`, without import.

#### Scenario: Altered amount
- **WHEN** the run command runs on a real BUY notice with a changed BRUT
- **THEN** the output shows `amount_check_failed`, 0 activities created and
  `exit=1`.

### Requirement: Activity content

A BUY or SELL activity SHALL have: quantity = QUANTITE without sign, unit
price = COURS, fee = COURTAGE, currency EUR. A COUPONS row SHALL give a
DIVIDEND with quantity 1, unit price = net credit of the row, and fee 0. The
activity date SHALL be the row date at midnight UTC. The comment SHALL be
`BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`. KIND is the activity type. The
row key SHALL include a stable document namespace. It SHALL use the broker
notice reference when the PDF shows one. Otherwise, it SHALL use the first 16
hex characters of the SHA-256 of the original PDF. The remaining key uses the
row content and its rank among identical rows of the notice.

#### Scenario: Real coupon in simulation
- **WHEN** the run command runs on a real coupon notice
- **THEN** the output shows one DIVIDEND line with quantity 1, the net credit
  as unit price, fee 0, and `exit=0`.

### Requirement: Security resolution

Resolve each ISIN through `MAPPING_FILE`'s `symbol_mapping`, then Ghostfolio
lookup. Accept exactly one EUR lookup result. Otherwise, skip that ISIN with
`unresolved_security` and log its mapping line. A missing or invalid mapping
file SHALL stop with `invalid_mapping`, unless `MAPPING_FILE` is empty.

#### Scenario: No EUR lookup result
- **WHEN** the mapping is empty and the ISIN of a notice has no single EUR
  lookup result
- **THEN** the output shows `unresolved_security`, a mapping line and `exit=1`.

### Requirement: No duplicate activity

A row SHALL be a duplicate, not imported, when an activity of the Ghostfolio
account has the same `BD#v3#` comment and the same date, type, quantity, unit
price and fee. The same comment with another value SHALL give code
`owned_activity_conflict`, without import. Legacy comments (`BD#v1#`, `BD#v2#`)
count as no `BD#v3#` comment. An activity without a `BD#v3#` comment SHALL
match a row when:

- for a BUY or SELL, it has the same side, security (or ISIN), quantity and
  unit price, and a date at most 2 days away. Each activity matches one row
  only, closest date first;
- for a DIVIDEND, it is a dividend of the same security with the same net
  amount, at most 3 days away.

Nearby trades with different quantity/price, or dividends with different net
amounts, SHALL get `possible_duplicate`, without import.

Malformed or unsupported reserved `BD#v` identities SHALL stop writes with
`invalid_identity`. Valid legacy v1/v2 comments SHALL remain readable.

#### Scenario: Invalid identity
- **WHEN** the run command reads an invalid reserved BD identity
- **THEN** it shows `invalid_identity`, 0 creations and `exit=1`.

#### Scenario: Second run
- **WHEN** the run command runs twice with `DRY_RUN=0` on the same notice
  documents both times
- **THEN** the second output shows 0 activities created, only duplicates, and
  `exit=0`.

#### Scenario: Coupon already in Ghostfolio
- **WHEN** the run command runs on the real notice of the coupon written by
  the legacy connector
- **THEN** the output shows that coupon as a duplicate and no DIVIDEND line.

### Requirement: Sell guard

The position of a security SHALL be the Ghostfolio position plus each new row,
in date order, with SELL rows first on the same date. A SELL that makes this
position negative SHALL get code `sell_exceeds_holding` and SHALL not be
imported.

#### Scenario: Sell without a position
- **WHEN** the run command runs on a real SELL notice of a security not held
- **THEN** the output shows `sell_exceeds_holding` and `exit=1`.

### Requirement: Custody fees ignored

A DROITS DE GARDE row SHALL get code `custody_fee_ignored`, without an import
and without an exit code change.

#### Scenario: Sell notice with a custody fee
- **WHEN** the run command runs on the real SELL notice with custody fees
- **THEN** the output shows the SELL line, `custody_fee_ignored` and `exit=0`.

### Requirement: Stop on a share-count change

A DIVISION row SHALL get code `share_count_change`. A row with an unknown
operation label SHALL get code `unknown_operation`. When either row has an
ISIN, no row of that ISIN SHALL be imported, from any notice document. Other
securities SHALL continue. `PAPERLESS_DONE_TAG` on a document SHALL clear these
two codes for its rows only; its other rows stay importable.

#### Scenario: Division and coupon in one notice
- **WHEN** the run command runs on the real notice with a coupon and a DIVISION
  of the same security
- **THEN** the output shows `share_count_change`, no DIVIDEND line and
  `exit=1`.

#### Scenario: Stop cleared
- **WHEN** the document with the DIVISION row has `PAPERLESS_DONE_TAG` and the
  run command runs
- **THEN** the output does not show `share_count_change`, and shows the coupon
  as a DIVIDEND line or a duplicate.

### Requirement: Additive writes with readback

The connector SHALL never update or delete data. After each import, each sent
`BD#v3#` comment SHALL read back exactly once, with the same account, comment,
symbol, data source, date, type, quantity, unit price, fee and currency.
Differences, empty, partial, repeated or extra results SHALL give
`import_unconfirmed` and stop all writes, without retry. Other comments do not
count. Only confirmed activities SHALL advance real holdings.

#### Scenario: Unexpected import response
- **WHEN** Ghostfolio answers a run with `DRY_RUN=0` with an empty activity
  list
- **THEN** the output shows `import_unconfirmed` and `exit=1`.

### Requirement: Exit code, summary and notification

The log SHALL end with one summary line of counts. The exit code SHALL be 0
when each row is imported, simulated, a duplicate, a custody fee or of another
account. Else it SHALL be 1. With `DRY_RUN=0` and `APPRISE_URLS`
set, exit code 1 SHALL send one notification with the codes.

#### Scenario: Failure notification
- **WHEN** the run command runs with `DRY_RUN=0`, `APPRISE_URLS` and an
  `unresolved_security` row
- **THEN** the output shows `Failure notification sent` and `exit=1`.

### Requirement: Schedule

A valid `CRON` SHALL schedule the import. Without `CRON`, the import SHALL
run once. An invalid `CRON` SHALL stop the container with exit code 1.

#### Scenario: Invalid schedule
- **WHEN** the run command runs with `CRON=bad`
- **THEN** the output shows `Invalid CRON` and `exit=1`.

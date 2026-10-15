# Spec Delta

## Purpose

Read Bourse Direct PDF notices from Paperless. Add new BUY, SELL and DIVIDEND
activities to one Ghostfolio account. One container serves one Bourse Direct
account.

"The run command" is `docker compose run --rm -T boursedirect-sync; echo
"exit=$?"`. "Notice documents" are the Paperless documents whose custom field
`Source` is exactly `Bourse Direct`, with or without the tag
`PAPERLESS_DONE_TAG`.

## ADDED Requirements

### Requirement: Settings from ENV only

The connector SHALL read its settings only from ENV. Required: `GHOST_HOST`,
`GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `BD_ACCOUNT_REF`,
`PAPERLESS_URL`, `PAPERLESS_TOKEN`. Optional: `PAPERLESS_DONE_TAG` (default
`ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`,
`APPRISE_TIMEOUT`, `LOG_LEVEL`. A missing or invalid setting SHALL stop the run
with code `invalid_configuration`. The log SHALL never show a secret.

#### Scenario: Missing Paperless token
- **WHEN** the run command runs without `PAPERLESS_TOKEN`
- **THEN** the output shows `invalid_configuration`, `PAPERLESS_TOKEN` and
  `exit=1`.

### Requirement: Simulation by default

`DRY_RUN=0` SHALL send activities to Ghostfolio. `DRY_RUN=1`, or no value,
SHALL simulate. Another value SHALL give `invalid_configuration`. A simulation
SHALL log each activity to create (date, type, symbol, quantity, unit price,
fee, comment). It SHALL not write to Ghostfolio or notify.

#### Scenario: Real BUY in simulation
- **WHEN** the run command runs without `DRY_RUN` on one real BUY notice
- **THEN** the output shows `DRY RUN`, a BUY line, `exit=0`.

### Requirement: Paperless source

Each run SHALL read the original PDF of every notice document. The connector
SHALL never write to Paperless. A rejected token SHALL stop the run with code
`paperless_auth_failed`. No answer or an unexpected answer SHALL stop it with
code `paperless_unreachable`. The log SHALL show the Paperless document ID,
never the holder name or address. The account number SHALL appear only in
the comment and its log line.

#### Scenario: Wrong Paperless token
- **WHEN** the run command runs with an invalid `PAPERLESS_TOKEN`
- **THEN** the output shows `paperless_auth_failed` and `exit=1`.

### Requirement: Account selection

The connector SHALL import only the notices whose text shows the account
reference `BD_ACCOUNT_REF`. It SHALL skip the notices of other accounts and
log only their count.

#### Scenario: Notice of another account
- **WHEN** the run command runs on a real BUY notice and a real notice of
  another account
- **THEN** the output shows one BUY line, 1 other-account notice and `exit=0`.

### Requirement: Unreadable documents block writes

A document that is not a readable Bourse Direct notice, has an unknown field
label or has no readable account reference SHALL get code
`notice_unreadable`. This code SHALL stop all Ghostfolio writes of the run. A
simulation SHALL still list the readable activities.

#### Scenario: Unreadable document
- **WHEN** the run command runs with `DRY_RUN=0` on a real BUY notice and a
  PDF that is not a notice
- **THEN** the output shows `notice_unreadable`, 0 activities created and
  `exit=1`.

### Requirement: Amount checks

For each BUY or SELL row, QUANTITE × COURS SHALL equal BRUT. A BUY debit SHALL
equal BRUT + COURTAGE + TVA. A SELL credit SHALL equal BRUT − COURTAGE − TVA.
TVA SHALL be zero. A COUPONS row SHALL be a positive credit. All amounts SHALL
be in EUR. A failed row SHALL get code `amount_check_failed` and SHALL not be
imported.

#### Scenario: Altered amount
- **WHEN** the run command runs on a real BUY notice with a changed BRUT
- **THEN** the output shows `amount_check_failed` and `exit=1`.

### Requirement: Activity content

A BUY or SELL activity SHALL have: quantity = QUANTITE without sign, unit
price = COURS, fee = COURTAGE, currency EUR. A COUPONS row SHALL give a
DIVIDEND with quantity 1, unit price = net credit of the row, and fee 0. The
activity date SHALL be the row date at midnight UTC. The comment SHALL be
`BD#v3#<BD_ACCOUNT_REF>:<KIND>:<row key>`. KIND is the activity type. The
row key is made from the row content and its rank among identical rows of the
notice.

#### Scenario: Real coupon in simulation
- **WHEN** the run command runs on a real coupon notice
- **THEN** the output shows one DIVIDEND line with quantity 1, the net credit
  as unit price, fee 0, and `exit=0`.

### Requirement: Security resolution

The connector SHALL find the symbol of each ISIN first in the `symbol_mapping`
entries of `MAPPING_FILE`, then with a Ghostfolio lookup by ISIN. The lookup
SHALL give a symbol only for exactly one EUR result. Otherwise, the rows of
that ISIN SHALL get code `unresolved_security` and SHALL not be imported. The
log SHALL give a mapping line for each such ISIN. A missing or invalid mapping
file SHALL stop the run with code `invalid_mapping`, unless `MAPPING_FILE` is
empty.

#### Scenario: No EUR lookup result
- **WHEN** the mapping is empty and the ISIN of a notice has no single EUR
  lookup result
- **THEN** the output shows `unresolved_security`, a mapping line and `exit=1`.

### Requirement: No duplicate activity

A row SHALL be a duplicate, not imported, when an activity of the Ghostfolio
account has the same `BD#v3#` comment. An activity with a `BD#v3#` comment
SHALL match only by this exact comment. Legacy comments (`BD#v1#`, `BD#v2#`)
count as no `BD#v3#` comment. An activity without a `BD#v3#` comment SHALL
match a row when:

- for a BUY or SELL, it has the same side, security (or ISIN), quantity and
  unit price, and a date at most 2 days away. Each activity matches one row
  only, closest date first;
- for a DIVIDEND, it is a dividend of the same security with the same net
  amount, at most 3 days away.

A BUY or SELL near such an activity, with another quantity or price, SHALL get
code `possible_duplicate`, without import.

#### Scenario: Second run
- **WHEN** the run command runs twice with `DRY_RUN=0`
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
Another result SHALL give code `import_unconfirmed`: a difference, or an
empty, partial, repeated or extra result. This code SHALL stop all writes of
the run; no retry.

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

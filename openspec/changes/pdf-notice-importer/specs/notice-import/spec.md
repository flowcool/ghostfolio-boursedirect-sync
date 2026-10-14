# Spec Delta

## Purpose

Read Bourse Direct PDF notices from Paperless. Add new BUY, SELL and DIVIDEND
activities to one Ghostfolio account.

"The run command" is `docker compose run --rm -T boursedirect-sync; echo
"exit=$?"`. Each scenario reads its output. "Notice documents" are the
Paperless documents whose custom field `PAPERLESS_SOURCE_FIELD` is exactly
`PAPERLESS_SOURCE_VALUE` (case sensitive), without the tag `PAPERLESS_DONE_TAG`.

## ADDED Requirements

### Requirement: Settings from ENV only

The connector SHALL read its settings only from ENV. Required: `GHOST_HOST`,
`GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, `PAPERLESS_URL`,
`PAPERLESS_TOKEN`. Optional: `PAPERLESS_SOURCE_FIELD` (default `Source`), `PAPERLESS_SOURCE_VALUE`
(default `Bourse Direct`),
`PAPERLESS_DONE_TAG` (default `ghostfolio-done`), `MAPPING_FILE`, `DRY_RUN`,
`TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`, `LOG_LEVEL`. A missing or
invalid setting SHALL stop the run with code `invalid_configuration`. The log
SHALL never show a token.

#### Scenario: Missing Paperless token
- **WHEN** the run command runs without `PAPERLESS_TOKEN`
- **THEN** the output shows `invalid_configuration`, `PAPERLESS_TOKEN` and
  `exit=1`.

### Requirement: Simulation by default

`DRY_RUN=0` SHALL send activities to Ghostfolio. `DRY_RUN=1`, or no value,
SHALL simulate. Another value SHALL give `invalid_configuration`. A simulation SHALL log one line for each activity that it would create: date, type, symbol, quantity,
unit price and fee. It SHALL write nothing to Ghostfolio and send no
notification.

#### Scenario: Real BUY in simulation
- **WHEN** the notice documents hold one real BUY notice and the run command
  runs without `DRY_RUN`
- **THEN** the output shows `DRY RUN`, a BUY line, `exit=0`.

### Requirement: Paperless source

Each run SHALL read the original PDF file of every notice document. The
connector SHALL never write to Paperless. Before any Ghostfolio write, a
rejected token SHALL stop the run with code `paperless_auth_failed`; no answer
or an unexpected answer SHALL stop it with code `paperless_unreachable`. A
document that is not a readable Bourse Direct notice, or that has an unknown
field label, SHALL get code `notice_unreadable` and SHALL be skipped. The log
SHALL show the Paperless ID of a document, never the account number, holder
name or address.

#### Scenario: Wrong Paperless token
- **WHEN** the run command runs with an invalid `PAPERLESS_TOKEN`
- **THEN** the output shows `paperless_auth_failed`, no activity line and
  `exit=1`.

#### Scenario: Paperless down
- **WHEN** the run command runs and `PAPERLESS_URL` does not answer
- **THEN** the output shows `paperless_unreachable` and `exit=1`.

#### Scenario: Unreadable document
- **WHEN** the run command runs on a real BUY notice and a PDF that is not a
  notice
- **THEN** the output shows `notice_unreadable`, the BUY line and `exit=1`.

### Requirement: Amount checks

For each BUY or SELL row, QUANTITE × COURS SHALL equal BRUT. A BUY debit SHALL
equal BRUT + COURTAGE + TVA. A SELL credit SHALL equal BRUT − COURTAGE − TVA.
TVA SHALL be zero. Amounts SHALL be in EUR. A row that fails a check SHALL get
code `amount_check_failed` and SHALL not be imported.

#### Scenario: Altered amount
- **WHEN** the run command runs on a real BUY notice with a changed BRUT
- **THEN** the output shows `amount_check_failed`, no BUY line and `exit=1`.

### Requirement: Activity content

A BUY or SELL activity SHALL have: quantity = QUANTITE without sign, unit price =
COURS, fee = COURTAGE, currency EUR. A COUPONS row SHALL give a DIVIDEND with
quantity 1, unit price = net amount credited for that row, and fee 0. The
activity date SHALL be the row date at midnight UTC. The comment SHALL start
with `BD#`, followed by an identifier made from the row content.

#### Scenario: Real coupon in simulation
- **WHEN** the run command runs on a real coupon notice
- **THEN** the output shows one DIVIDEND line with quantity 1, the credited
  amount as unit price, fee 0, and `exit=0`.

### Requirement: Security resolution

The connector SHALL find the symbol of each ISIN first in the `symbol_mapping`
entries (`ISIN: "TICKER"`) of `MAPPING_FILE`, then with a Ghostfolio lookup by
ISIN. The lookup SHALL give a symbol only when exactly one EUR result exists.
Otherwise, each row of that ISIN SHALL get code `unresolved_security` and SHALL
not be imported. The log SHALL list each such ISIN with a line to paste into the
mapping file. A missing or invalid mapping file SHALL stop the run with code
`invalid_mapping`, unless `MAPPING_FILE` is empty.

#### Scenario: No EUR lookup result
- **WHEN** the mapping is empty, the ISIN of a notice has no single EUR lookup
  result, and the run command runs
- **THEN** the output shows `unresolved_security`, the ISIN, a mapping line and
  `exit=1`.

### Requirement: No duplicate activity

A row SHALL be a duplicate, not imported, when an activity of the Ghostfolio
account:

- has the same `BD#` comment; or
- for a BUY or SELL, has no `BD#` comment, the same side, security (or ISIN),
  quantity and unit price, and a date at most 2 days away. Each activity
  matches one row only, closest date first; or
- for a DIVIDEND, is a dividend of the same security at most 3 days away.

A BUY or SELL with such an activity at most 2 days away, but another quantity
or price, SHALL get code `possible_duplicate` and SHALL not be imported.

#### Scenario: Second run
- **WHEN** the run command runs twice with `DRY_RUN=0` and the same notice
  documents
- **THEN** the second output shows 0 activities created, only duplicates, and
  `exit=0`.

#### Scenario: Coupon already in Ghostfolio
- **WHEN** the run command runs on the real notice of the coupon that the legacy
  connector wrote to Ghostfolio on 2026-10-14
- **THEN** the output shows that coupon as a duplicate and no DIVIDEND line.

### Requirement: Sell guard

A SELL that makes the Ghostfolio position of the security negative SHALL get
code `sell_exceeds_holding` and SHALL not be imported.

#### Scenario: Sell without a position
- **WHEN** the run command runs on a real SELL notice for a security that the
  account does not hold
- **THEN** the output shows `sell_exceeds_holding` and `exit=1`.

### Requirement: TTF line stops the run

A row with the label TAXE TRANSACT FINANCIERES SHALL stop the run with code
`ttf_found` before any Ghostfolio write. The message SHALL tell the operator to
enter the TTF by hand, then add `PAPERLESS_DONE_TAG` to the document. The README
SHALL explain that notices do not show the TTF.

#### Scenario: TTF row
- **WHEN** the run command runs with `DRY_RUN=0` and a notice document with a
  TTF row
- **THEN** the output shows `ttf_found`, no activity line and `exit=1`.

#### Scenario: Stop cleared
- **WHEN** that document has `PAPERLESS_DONE_TAG` and the run command runs
- **THEN** the output does not show `ttf_found`.

### Requirement: Custody fees ignored

A DROITS DE GARDE row SHALL not be imported and SHALL get code
`custody_fee_ignored`. It SHALL not change the exit code.

#### Scenario: Sell notice with a custody fee
- **WHEN** the run command runs on the real SELL notice with a DROITS DE GARDE
  row
- **THEN** the output shows the SELL line, `custody_fee_ignored` and `exit=0`.

### Requirement: Stop on a share-count change

A DIVISION row SHALL get code `share_count_change`. A row with an unknown
operation label SHALL get code `unknown_operation` and SHALL not be imported.
When either row has an ISIN, no row of that ISIN SHALL be imported. The connector SHALL check
all notice documents before it writes any activity of an ISIN. Other
securities SHALL continue. The stop SHALL end when the document with that row
has `PAPERLESS_DONE_TAG`.

#### Scenario: Division and coupon in one notice
- **WHEN** the run command runs on the real notice with a coupon and a DIVISION
  of the same security
- **THEN** the output shows `share_count_change`, no DIVIDEND line for that
  security and `exit=1`.

### Requirement: Additive writes with readback

The connector SHALL only create activities, never update or delete data.
After each import, it SHALL compare each created activity in the Ghostfolio
response with the sent activity: account, comment, date, type, quantity, unit
price, fee and currency. A
difference, a missing activity or an unexpected response SHALL give code
`import_unconfirmed` and stop all writes of the run.

#### Scenario: Unexpected import response
- **WHEN** Ghostfolio returns a created activity with another quantity to a
  run with `DRY_RUN=0`
- **THEN** the output shows `import_unconfirmed` and `exit=1`.

### Requirement: Exit code, summary and notification

The log SHALL end with one summary line of counts. The exit code SHALL be 0 when each
row is imported, simulated, a duplicate or a custody fee. In all other cases,
the exit code SHALL be 1. With `DRY_RUN=0` and `APPRISE_URLS` set, exit code 1
SHALL send one notification with the codes.

#### Scenario: Failure notification
- **WHEN** the run command runs with `DRY_RUN=0`, `APPRISE_URLS` set and an
  `unresolved_security` row
- **THEN** the output shows `Failure notification sent` and `exit=1`.

### Requirement: Schedule

A valid `CRON` SHALL run the import on that schedule. Without `CRON`, the
import SHALL run once. An invalid `CRON` SHALL stop the container with exit
code 1.

#### Scenario: Invalid schedule
- **WHEN** the run command runs with `CRON=bad`
- **THEN** the output shows `Invalid CRON` and `exit=1`.

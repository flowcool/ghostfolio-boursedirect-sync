# Spec Delta

## Purpose

Read Bourse Direct PDF notices from one folder. Add new BUY, SELL and DIVIDEND
activities to one Ghostfolio account.

"The run command" is `docker compose run --rm -T boursedirect-sync; echo
"exit=$?"`. Each scenario reads its output.

## ADDED Requirements

### Requirement: Settings from ENV only

The connector SHALL read its settings only from ENV. Required: `GHOST_HOST`,
`GHOST_ACCESS_TOKEN` or `GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`. Optional:
`NOTICE_DIR` (default `/notices`), `MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`,
`APPRISE_URLS`, `APPRISE_TIMEOUT`, `LOG_LEVEL`. A missing or invalid setting
SHALL stop the run with code `invalid_configuration` before any network call. An
unknown Ghostfolio account name SHALL stop the run with code `account_failed`.

#### Scenario: Missing account name
- **WHEN** the run command runs without `GHOST_ACCOUNT_NAME`
- **THEN** the output shows `invalid_configuration`, `GHOST_ACCOUNT_NAME` and
  `exit=1`.

### Requirement: Simulation by default

Only `DRY_RUN=0` SHALL send activities to Ghostfolio. Any other value, or no
value, SHALL simulate. A simulation SHALL do all reads and checks. It SHALL log
one line for each activity that it would create: date, type, symbol, quantity,
unit price and fee. It SHALL write nothing to Ghostfolio and send no
notification.

#### Scenario: Real BUY in simulation
- **WHEN** the run command runs without `DRY_RUN` and `NOTICE_DIR` holds one
  real BUY notice
- **THEN** the output shows `DRY RUN`, one BUY line with date, symbol, quantity,
  unit price and fee, and `exit=0`.

### Requirement: Input folder

Each run SHALL read every `.pdf` file in `NOTICE_DIR`. It SHALL not change,
move or delete a file. An empty folder SHALL give zero activities and exit code
0. A file that is not a readable Bourse Direct notice, or that has an unknown
field label, SHALL get code `notice_unreadable`. The connector SHALL skip that
file and continue. The log SHALL never show the account number, the holder name
or the address from a notice.

#### Scenario: Unreadable file
- **WHEN** `NOTICE_DIR` holds one real BUY notice and one PDF that is not a
  notice, and the run command runs
- **THEN** the output shows `notice_unreadable` with the second file name, the
  BUY line and `exit=1`.

### Requirement: Amount checks

For each BUY or SELL row, QUANTITE × COURS SHALL equal BRUT. A BUY debit SHALL
equal BRUT + COURTAGE + TVA. A SELL credit SHALL equal BRUT − COURTAGE − TVA.
TVA SHALL be zero. Amounts SHALL be in EUR. A row that fails a check SHALL get code `amount_check_failed` and
SHALL not be imported.

#### Scenario: Altered amount
- **WHEN** the run command runs on a real BUY notice with a changed BRUT
- **THEN** the output shows `amount_check_failed`, no BUY line and `exit=1`.

### Requirement: Activity content

A BUY or SELL activity SHALL have: quantity = QUANTITE without sign, unit price =
COURS, fee = COURTAGE, currency EUR. A COUPONS row SHALL give a DIVIDEND with
quantity 1, unit price = net amount credited for that row, and fee 0. The
connector SHALL never calculate a gross amount or a withholding tax. The
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
not be imported. At the end, the log SHALL list each such ISIN with a line to
paste into the mapping file. A missing or invalid mapping file SHALL stop the
run with code `invalid_mapping`, unless `MAPPING_FILE` is empty.

#### Scenario: No EUR lookup result
- **WHEN** the mapping is empty and the ISIN of a notice has no single EUR
  lookup result, and the run command runs
- **THEN** the output shows `unresolved_security`, the ISIN, a mapping line and
  `exit=1`.

### Requirement: No duplicate activity

The connector SHALL read all activities of the Ghostfolio account before it
imports. A row SHALL count as a duplicate, and SHALL not be imported, when:

- an activity of the account has the same `BD#` comment; or
- for a BUY or SELL, an activity whose comment does not start with `BD#` has the
  same side, security (or a symbol with the same ISIN), quantity and unit price,
  and a date at most 2 days from the row date. Each existing activity matches
  one row only, closest date first; or
- for a DIVIDEND, a dividend of the same security has a date at most 3 days from
  the row date, with any comment.

A BUY or SELL with such an activity of the same side and security at most 2
days away, but another quantity or price, SHALL get code `possible_duplicate`
and SHALL not be imported.

#### Scenario: Second run with the same files
- **WHEN** the run command runs twice with `DRY_RUN=0` and the same files
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
`ttf_found` before any write. The message SHALL tell the operator to enter the
TTF by hand. The stop SHALL occur on each run while that file is in
`NOTICE_DIR`. The README SHALL explain that notices do not show the TTF and that
the operator enters it by hand.

#### Scenario: TTF row
- **WHEN** the run command runs with `DRY_RUN=0` and a file with a TTF row
- **THEN** the output shows `ttf_found`, no activity line and `exit=1`.

### Requirement: Custody fees ignored

A DROITS DE GARDE row SHALL not be imported. The log SHALL show code
`custody_fee_ignored`. This row SHALL not change the exit code.

#### Scenario: Sell notice with a custody fee
- **WHEN** the run command runs on the real SELL notice with a DROITS DE GARDE
  row, for a security that the account holds
- **THEN** the output shows the SELL line, `custody_fee_ignored` and `exit=0`.

### Requirement: Stop on a share-count change

A DIVISION row SHALL get code `share_count_change`. A row with an unknown label
and an ISIN SHALL get code `unknown_operation`. In both cases, no row of that
ISIN from any file SHALL be imported. The connector SHALL check all files
before it writes any activity of an ISIN. Other securities SHALL continue. A row
with an unknown label and no ISIN SHALL get code `unknown_operation` and SHALL
not be imported.

#### Scenario: Division and coupon in one notice
- **WHEN** the run command runs on the real notice with a coupon and a DIVISION
  of the same security
- **THEN** the output shows `share_count_change`, no DIVIDEND line for that
  security and `exit=1`.

### Requirement: Additive writes

The connector SHALL only create activities. It SHALL never update or delete an
activity, a cash balance or an account.

#### Scenario: Manual activity unchanged
- **WHEN** the run command runs with `DRY_RUN=0` and a row matches a manual
  activity
- **THEN** the output shows a duplicate, and Ghostfolio shows that activity with
  the same values.

### Requirement: Exit code, summary and notification

The log SHALL end with one summary line: notices read, activities created or
simulated, duplicates, rows not imported. The exit code SHALL be 0 when each
row is imported, simulated, a duplicate or a custody fee. In all other cases,
the exit code SHALL be 1. With `DRY_RUN=0` and `APPRISE_URLS` set, exit code 1
SHALL send one notification with the codes.

#### Scenario: Failure notification
- **WHEN** the run command runs with `DRY_RUN=0`, `APPRISE_URLS` set and a file
  that gives `unresolved_security`
- **THEN** the output shows the summary line, `Failure notification sent` and
  `exit=1`.

### Requirement: Schedule

With five valid numeric fields in `CRON`, the container SHALL run on that
schedule. With an empty `CRON`, it SHALL run once and stop. An invalid `CRON`
SHALL stop the container at start with exit code 1.

#### Scenario: Invalid schedule
- **WHEN** the run command runs with `CRON=bad`
- **THEN** the output shows `Invalid CRON` and `exit=1`.

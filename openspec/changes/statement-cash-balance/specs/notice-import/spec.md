## ADDED Requirements

### Requirement: Account statements in the source

The source (folder or Paperless) MAY contain Bourse Direct monthly account
statements ("Relevé de compte"). The importer SHALL recognize a statement by its
printed title and its opening and closing `Solde au` lines. A recognized
statement SHALL NOT be an operation notice. It SHALL never create, correct or
hold an activity. It SHALL NOT give `notice_unreadable`. Logs SHALL count
recognized statements. A PDF that is neither a supported notice nor a
recognized statement SHALL keep the existing `notice_unreadable` behavior.
Securities statements ("Relevé de titres") SHALL remain unsupported.

#### Scenario: Statement next to notices
- **WHEN** the source holds notices and one account statement, `CASH_BALANCE` absent
- **THEN** the notices import as today, the statement is counted, no `notice_unreadable`.

#### Scenario: Unknown PDF
- **WHEN** the source holds a PDF that is neither a notice nor a statement
- **THEN** `notice_unreadable`, no writes, as today.

### Requirement: Opt-in cash balance

Optional ENV `CASH_BALANCE` SHALL accept `0` or `1`. Absent SHALL mean `0`.
Other values SHALL give `invalid_configuration CASH_BALANCE` before service
access. With `0`, the importer SHALL read no statement amount and SHALL send no
cash write. The outcome line SHALL keep `cash=not managed`.

With `1`, the importer SHALL select the statements of `BD_ACCOUNT_REF`, with the
same account rule as notices. Statements of other accounts SHALL be counted and
ignored. The importer SHALL take the latest statement by closing date. It SHALL
check that its opening balance plus its movements equals its closing balance,
and that consecutive statements chain (opening equals the previous closing).
The proposed cash SHALL be the closing balance plus the net cash of supported
BUY, SELL and coupon notices of the same account dated after the closing date.
Money SHALL use exact decimal cents. The Ghostfolio account currency SHALL be
EUR.

Simulation SHALL log the statement closing date, the number of later notices
and the proposed cash, and SHALL send no cash write. Live mode SHALL send no write
when the stored balance already equals the proposed cash. Otherwise it SHALL
update only the account balance once per run, keep the other account fields, and
confirm the stored balance by readback. The outcome line SHALL report `cash=simulated`,
`cash=unchanged`, `cash=updated` or `cash=unavailable`.

No statement, an unreadable or inconsistent statement, a broken chain, a
currency mismatch or an unconfirmed cash write SHALL give `cash_unavailable`.
`cash_unavailable` SHALL be exit 0 with user action required. It SHALL send no
cash write and SHALL NOT change activity selection, imports or their exit code.
Logs SHALL show dates, counts and amounts only; they SHALL NOT show statement
text, holder name or address.

#### Scenario: Cash from latest statement and later notices
- **WHEN** `CASH_BALANCE=1`, the latest statement closes on 31/08 at 348.66 EUR, and one BUY notice of 120.00 EUR net is dated 05/09
- **THEN** simulation proposes 228.66 EUR; live mode stores 228.66 EUR and confirms it by readback.

#### Scenario: Setting off
- **WHEN** `CASH_BALANCE` is absent
- **THEN** no cash read or write, `cash=not managed`.

#### Scenario: Inconsistent statement
- **WHEN** the movements of the latest statement do not sum to its closing balance
- **THEN** `cash_unavailable`, no cash write, activities import normally, exit 0 with user action.

#### Scenario: Invalid setting
- **WHEN** `CASH_BALANCE=yes`
- **THEN** `invalid_configuration CASH_BALANCE`, no service access, exit 1.

# Proposal

## Why

Ghostfolio shows no correct cash for the Bourse Direct account. IBKR sync keeps cash current; this importer does not. The monthly account statement ("relevé de compte") gives the exact balance and every cash movement.

## What Changes

- The source (folder or Paperless) can contain monthly account statements.
- The importer recognizes a statement by its content. A statement is not an operation notice. It never creates an activity.
- New opt-in setting `CASH_BALANCE`. Absent or `0`: no cash read, no cash write (current behavior).
- With `CASH_BALANCE=1`, the importer computes: cash = closing balance of the latest statement + net amounts of supported notices dated after that statement.
- Simulation logs the proposed cash. Live mode updates the Ghostfolio account balance once per run and reads it back.
- An unreadable Paperless document strictly older than the latest closing does not block cash. Unknown dates and unreadable folder files still block it. Activity protections stay unchanged.
- An unreadable statement, a broken balance chain, a currency mismatch or an account mismatch stops the cash write. Activity import is not affected.
- Today a statement in the source stops all writes as an unreadable notice. After this change, it is recognized and counted.

| Statement line type (21 real statements, 12/2024–08/2026) | Effect on cash |
| --- | --- |
| Opening and closing balance (`Solde au`) | Source of truth at month end |
| `ACH CPT`, `ACHAT ETRANGER`, `ACHAT INTRODUCTION` | In statement; after it: from BUY notice |
| `VTE CPT`, `VENTE ETRANGER` | In statement; after it: from SELL notice |
| `COUPONS` | In statement; after it: from coupon notice |
| `TAXE TRANSACT` (TTF) | In statement; after it: from the BUY notice |
| `INVESTISSEMENT ESPECES` (deposit) | In statement only; next statement |
| `DROITS DE GARDE` (custody fee) | In statement only; next statement |
| `INDEMNISATION`, `ESPECES SUR OST`, `AMORTISSEMENT PARTIEL`, `DIVISION`, `TRANSFERT VALEUR`, `ATTRIBUTION`, `DET DROIT`, `RETRAIT TITRES` | In statement only; next statement |

Out of scope: securities statements (`releveTitres`), CTO, other currencies, cash history, statement collection (BillCollector, separate item).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `notice-import`: the source accepts account statements; new opt-in cash balance requirement; account settings documented.

## Impact

- Code: source classification, statement parser, cash computation, one account update (IBKR pattern), outcome line `cash=`.
- Config and docs: `CASH_BALANCE` in settings, `.env.example`, README (EN, FR), `llms.txt`.
- Lab proof with real statements. The account balance is overwritten when the setting is on.

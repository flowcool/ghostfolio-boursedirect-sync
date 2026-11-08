# Design

## Context

- `app.run_sync` reads every source document, then calls `notices.parse_text`. A PDF that is not a notice raises `notice_unreadable` and blocks all financial writes. A statement in the source therefore blocks the import today.
- Source documents come from `notice_source.acquire` (folder snapshot or Paperless `Source = Bourse Direct`). The same source will carry statements; no new source setting is needed.
- `ghostfolio.py` has no account update. IBKR has one: `ghostfolio_ibkr_sync/ghostfolio.py` `ghost_update_cash_balance` (GET account, currency check, dry-run log, PUT of the explicit `UpdateAccountDto` fields `balance, currency, id, name, platformId`). Ghostfolio rejects unknown body fields.
- Evidence (coordinator, 2026-11-08, 21 real `releveCompte.pdf`, 12/2024–08/2026): one page each; header `COMPTE N° … EUR PEA`; columns `Date | Désignation | Débit (€) | Crédit (€)`; opening and closing `Solde au : dd/mm/yyyy` lines. The opening balance equals the previous closing balance for all 21. A naive line parser reconciles 14 of 21 statements; the other 7 have lines without an amount or wrapped lines.

## Goals / Non-Goals

**Goals:**
- Stop treating statements as unreadable notices.
- Exact, opt-in cash with the same safety pattern as IBKR.

**Non-Goals:**
- Cash history by date, cash activities, import of statement movements as activities.
- Statement collection (separate BillCollector work).
- Platform metadata (separate work). It can reuse the same PUT later.

## Decisions

1. **Classify by content before notice parsing.** A new `statements.py` module checks the extracted text for the statement title and two `Solde au` lines. Recognized statements leave the notice path. Alternative: a Paperless tag or filename. Rejected: the folder source has no metadata, and content is the only proof that works for both sources.
2. **Column position decides the sign.** The amount is the last decimal on the line; its end column is compared with the `Crédit (€)` header column. A movement line without an amount continues to the next line or has zero cash. Each statement must reconcile exactly (opening + movements = closing); otherwise `cash_unavailable`. Gate: the parser must reconcile all 21 retained statements before any lab write.
3. **Latest statement + later notices.** Notices dated after the closing date add their net cash (BUY −, SELL +, coupon +), using the amounts already checked by `notices.checked_amounts`. Deposits, withdrawals and fees after the statement wait for the next statement. Alternative: rebuild cash from notices only. Rejected: deposits and fees are never on notices, so it drifts without correction.
4. **Reuse the IBKR update, adapted.** Port `ghost_update_cash_balance` to Decimal and to BD logging: GET, EUR check, explicit DTO with the stored `platformId`, PUT, then GET readback of `balance`. One write per run, after the activity phase. Failure maps to `cash_unavailable`, never to the import exit code.
5. **Settings.** `CASH_BALANCE` is parsed like `DRY_RUN` (`0`/`1`, absent = `0`). It is added to `.env.example`, Compose, README (EN, FR) and `llms.txt`.

## Risks / Trade-offs

- [Statement layout change] → exact reconciliation and the chain check stop the cash write; activities continue.
- [Cash between statements] → deposits and fees appear up to one month late. Logged with the statement date.
- [Overwrites a manual balance] → opt-in only; simulation shows the value first; README warns.
- [Notice and statement disagree on a trade amount] → the statement is authoritative at month end; the next statement corrects the drift.
- [Paperless delivery of statements needs collector work] → until collector support is available, the user drops statements by hand.

# Tasks

## 1. Statements in the source

- [ ] 1.1 Recognize account statements by content and remove them from the notice path. Count them in logs. Requirement: Account statements in the source. Scenarios: Statement next to notices; Unknown PDF. Files: statements.py (new), app.py, tests/test_statements.py, anonymized fixtures derived from real `releveCompte.pdf` text (no holder, address or account number). Check: `.venv/bin/python -m pytest tests/test_statements.py` and the existing notice tests.
- [ ] 1.2 Parse one statement exactly: closing date, opening and closing balance, signed movements by column, wrapped lines and lines without amount. Reject a statement that does not reconcile. Gate: all 21 retained statements under `inputs/boursedirect-all-history-20261026/pea/statements/` reconcile and chain; save a private result under `tmp/`. Requirement: Opt-in cash balance. Scenario: Inconsistent statement.

## 2. Cash computation and write

- [ ] 2.1 Add `CASH_BALANCE` (`0`/`1`, absent `0`, else `invalid_configuration CASH_BALANCE` before service access). Files: config.py, models.py, outcome.py, tests. Scenarios: Setting off; Invalid setting.
- [ ] 2.2 Compute cash = latest statement closing balance of `BD_ACCOUNT_REF` + net cash of supported BUY, SELL and coupon notices dated after it, in Decimal cents. Scenario: Cash from latest statement and later notices.
- [ ] 2.3 Port the IBKR account update (`ghost_update_cash_balance`) to `ghostfolio.py`: GET, EUR check, explicit DTO with stored `platformId`, one PUT, GET readback. Simulation logs only. Map every failure to `cash_unavailable` (exit 0, user action) without changing imports. Outcome `cash=` value. Files: ghostfolio.py, app.py, outcome.py, tests with mocked HTTP.

## 3. Documentation

- [ ] 3.1 Document `CASH_BALANCE`, statement download and the overwrite warning in README.md, README.fr.md (essential table), docs/configuration.md, `.env.example`, `llms.txt`.

## 4. Qualification

- [ ] 4.1 Run strict mypy, Ruff and the full pytest suite once after focused tests pass.
- [ ] 4.2 Lab proof on empty and golden labs with real statements and notices: simulation shows the proposed cash; live run stores it and readback matches; repeat run reports `cash=unchanged` and sends no write. Retain proof; stop and verify the labs.
- [ ] 4.3 One PR, green CI, Pullfrog head review, `pr-ship`. No release or production action without Florent's GO.

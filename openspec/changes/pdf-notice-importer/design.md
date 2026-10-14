# Design

One Python file on the `ghostfolio-ibkr-sync` skeleton. `ibkr` below means
`ibkr_to_ghostfolio.py` in that repository.

## Reused parts

| Part | Reused from |
| --- | --- |
| ENV settings, token exchange | ibkr `load_config`, `ghost_exchange_access_token` |
| Mapping file | ibkr `load_mapping`, `mapping.yaml.example` |
| Read all activities | ibkr `ghost_get_existing_orders` |
| Manual BUY/SELL match | ibkr `_match_manual_entry` (adds exact price) |
| Dividend match, 3 days | ibkr `_dividend_date_matches` |
| Sell guard | ibkr `filter_trades_by_holdings` |
| Import and accepted rows | ibkr `ghost_import_activities`, `accepted_import_subset` |
| Exit codes, notification | ibkr `record_failure`, `finalize_run`, `send_notification` |
| CRON, run once | ibkr `entrypoint.sh` |
| Image | ibkr `Dockerfile` |

## New parts without a sibling line

- PDF reading and row checks. Source: the legacy parser (tag `legacy-wip`).
- Ghostfolio lookup by ISIN, one EUR result. Source: decision of 2026-10-14 and
  the legacy resolver.
- `DRY_RUN` absent means simulation. ibkr imports when it is absent. Decision of
  2026-10-14.

## Open questions for Florent

1. Does `AssetProfileSplit` change held quantities on Ghostfolio 3.86.0
   (GitHub #115)? Recommendation: v1 stops on DIVISION in all cases. Test later.
2. How does the operator clear a TTF or share-count stop? Recommendation: fix
   Ghostfolio by hand, then move the file out of `NOTICE_DIR`. No new mechanism.
3. Which PDF text tool? Recommendation: `pdftotext -layout` (Debian
   `poppler-utils`) in the image.
4. Test data: only one real PDF exists (BUY). Recommendation: store the
   anonymized text of each real PDF. Each operation type waits for a real PDF.
5. PEA and PEA-PME: recommendation: one service and one folder per account.
6. `.claude/rules/security.md` forbids logging notice content. Recommendation:
   allow date, type, symbol, quantity, price and fee, as ibkr does.
7. Coupon as quantity 1 at the net amount, or quantity = shares? Recommendation:
   quantity 1. The amount stays exact, as in the legacy connector.
8. The TTF has no real notice or document to test. Recommendation: test the
   stop with an anonymized copy of the real statement row.
9. Task 1.1 replaces the legacy main file in `main`. Recommendation: yes. The
   legacy code stays in tag `legacy-wip`.

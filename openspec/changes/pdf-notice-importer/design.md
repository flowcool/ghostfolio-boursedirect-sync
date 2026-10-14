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

## Decisions (2026-10-14)

- PDF text: `pdftotext -layout` (Debian `poppler-utils`) in the image.
- Clear a TTF or share-count stop: the operator fixes Ghostfolio by hand, then
  moves the PDF out of `NOTICE_DIR`. BillCollector does not publish a document
  again (its requirement R4), so the file does not come back.
- One service and one `NOTICE_DIR` for each account (PEA, PEA-PME).
- Logs may show date, type, symbol, quantity, price and fee. Logs never show the
  account number, the holder name or the address.
- Coupon: quantity 1 at the net amount. The amount stays exact.
- Test data: anonymized `pdftotext` text of real PDFs. Each operation type waits
  for a real PDF from BillCollector. The TTF test uses an anonymized copy of the
  real statement row.
- Task 1.1 replaces the legacy main file. Task 1.3 removes the legacy-only
  files. The legacy code stays in tag `legacy-wip`.

## Known limit

Ghostfolio 3.86.0 has `AssetProfileSplit`. Its effect on held quantities is not
known (GitHub #115). v1 stops on DIVISION in all cases. A later check can
change this.

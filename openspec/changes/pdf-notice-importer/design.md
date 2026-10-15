# Design

One Python file on the `ghostfolio-ibkr-sync` skeleton. `ibkr` means
`ibkr_to_ghostfolio.py` there. The Ghostfolio core is copied from ibkr now. A
verified projection (`check_core.py`, as in degiro) comes after ibkr v3.0.0.

## Reused parts

| Part | Reused from |
| --- | --- |
| ENV settings, token exchange | ibkr `load_config`, `ghost_exchange_access_token` |
| Mapping file | ibkr `load_mapping` |
| Read all activities | ibkr `ghost_get_existing_orders` |
| Manual BUY/SELL match | ibkr `_match_manual_entry`, plus exact price |
| Dividend match | ibkr `_dividend_date_matches` |
| Sell guard | ibkr `filter_trades_by_holdings` |
| Import, strict readback | ibkr `ghost_import_activities`, `accepted_import_subset` (line 945) |
| Exit codes, notification | ibkr `record_failure`, `finalize_run` |
| CRON, image | ibkr `entrypoint.sh`, `Dockerfile` |

## New parts (no sibling line)

- Paperless source (decision D1). Facts from paperless-ngx `docs/api.md` and
  source at commit `2b00cf6`:
  - Header `Authorization: Token <token>`.
  - `GET /api/documents/?custom_field_query=["Source","exact","Bourse Direct"]`
    (URL-encoded). `Source` is a Text field that a Paperless workflow sets on
    BillCollector files; `exact` is case sensitive (paperless-ngx v3.3.1,
    `docs/api.md` lines 121-134; BillCollector spec commit `81cf068`). Results
    are paged (`page_size`, `next`) and list their tag IDs.
  - `GET /api/tags/?name__iexact=<tag>` gives the ID of the done tag.
  - `GET /api/documents/<id>/download/?original=true` returns the original
    file. Without `original`, Paperless returns its archived version.
  - Header `Accept: application/json; version=10` pins the API version.
  - Use a Paperless user with view permission only.
- PDF text: `pdftotext -layout` (Debian `poppler-utils`).
- Row parsing and checks: from the legacy parser (tag `legacy-wip`).
- Ghostfolio lookup by ISIN: decision of 2026-10-14.
- `DRY_RUN` absent means simulation (decision D4).

## Decisions (2026-10-14)

- Clear a stop: the operator fixes Ghostfolio by hand, then adds
  `PAPERLESS_DONE_TAG` to the document.
- v1 serves one Ghostfolio account. The `Source` filter does not separate PEA
  and PEA-PME. Before task 6.1 (first real write), Florent confirms that
  Paperless holds notices of one account only, or decides a per-account
  criterion.
- Coupon: quantity 1 at the net amount.
- Logs show date, type, symbol, quantity, price and fee only.
- Test data: anonymized `pdftotext` text of real PDFs.
- Task 1.3 removes the legacy-only files. The legacy code stays in tag
  `legacy-wip`.

## Known limit

The effect of Ghostfolio `AssetProfileSplit` on held quantities is not known
(GitHub #115). v1 stops on DIVISION in all cases.

The TTF is only on account statements, never on notices. The connector does
not read statements, so Ghostfolio cost prices exclude the TTF (Florent,
2026-10-15).

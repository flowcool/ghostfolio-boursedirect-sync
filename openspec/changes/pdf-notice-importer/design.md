# Design

One Python file on the `ghostfolio-ibkr-sync` skeleton. `ibkr` means
`ibkr_to_ghostfolio.py` there. The Ghostfolio core is copied from ibkr. A
verified projection (`check_core.py`, as in degiro) comes after ibkr v3.0.0.

## Reused parts

| Part | Reused from |
| --- | --- |
| ENV settings, token exchange | ibkr `load_config`, `ghost_exchange_access_token` |
| Mapping file | ibkr `load_mapping` |
| Read all activities | ibkr `ghost_get_existing_orders` |
| Manual BUY/SELL match | ibkr `_match_manual_entry`, plus exact price |
| Dividend match | ibkr `_dividend_date_matches`, with a change |
| Sell guard | ibkr `filter_trades_by_holdings` |
| Import, readback | ibkr `ghost_import_activities`, with a change |
| Exit codes, notification | ibkr `record_failure`, `finalize_run` |
| CRON, image | ibkr `entrypoint.sh`, `Dockerfile` |

## Changes from ibkr

- Readback: ibkr `accepted_import_subset` (line 945) accepts a short or empty
  list. Ghostfolio can answer HTTP 201 with an empty list when the same
  activity exists in another account. Here, an empty, partial, repeated or
  extra result gives `import_unconfirmed`.
- Dividend: ibkr change `dividend-proximity-amount-evidence` excludes its own
  comments from the 3-day match. It skips a manual row with another amount.
  Here, that row must have the same net amount.

## New parts (no sibling line)

- Paperless (decision D1; paperless-ngx `docs/api.md` lines 121-134, commit
  `2b00cf6`): header `Authorization: Token <token>`; `GET
  /api/documents/?custom_field_query=["Source","exact","Bourse Direct"]`
  (paged); `GET /api/tags/?name__iexact=<tag>`; `GET
  /api/documents/<id>/download/?original=true`; header `Accept:
  application/json; version=10`. The Paperless user has view permission only.
- PDF text: `pdftotext -layout` (Debian `poppler-utils`).
- Row parsing and checks: from the legacy parser (tag `legacy-wip`).
- Ghostfolio lookup by ISIN: decision of 2026-10-14.

## Decisions

- One container per Bourse Direct account (Florent, 2026-10-15). A notice of an
  account without a container is only counted.
- `PAPERLESS_DONE_TAG` clears only the blocking rows of a document (Florent,
  option A). The operator fixes Ghostfolio by hand first.
- Identity `BD#v3#<account>:<KIND>:<row key>` (Florent, 2026-10-15), as ibkr
  `IBKR#v2#`: Ghostfolio duplicate detection ignores the account.
  v1, v2: legacy. If the real PDF shows a notice reference (task 1.1),
  it joins the row key.
- Coupon: quantity 1 at the net amount.
- Logs show activity fields and the comment only.
- Test data: anonymized `pdftotext` text of real PDFs.

## Known limits

The effect of Ghostfolio `AssetProfileSplit` on held quantities is not known
(GitHub #115). v1 stops on DIVISION in all cases.

Notices do not show the TTF. Ghostfolio cost prices exclude it (Florent,
2026-10-15).

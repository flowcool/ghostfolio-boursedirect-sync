# Design

One Python file uses the `ghostfolio-ibkr-sync` skeleton. `ibkr` below means its
`ibkr_to_ghostfolio.py` file.

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

- Account target: ibkr `ghost_find_account_id` (lines 760-772) returns the first
  exact name. Here, exactly one match is required; otherwise use
  `invalid_configuration`. A notice has exactly one labelled account field.
  Remove its spaces once and compare the full value with `BD_ACCOUNT_REF`.
- Readback: ibkr `accepted_import_subset` (line 945) accepts a short or empty
  list. Here, any empty, partial, repeated or extra result gives
  `import_unconfirmed`.
- Error logs: ibkr `ghost_import_activities` (lines 1076-1089) logs raw bodies.
  Here, logs allow only HTTP status, error code and Paperless document ID.
- Dividend: ibkr `dividend-proximity-amount-evidence` excludes owned comments
  from the 3-day match. Here, a manual row also needs the same net amount.

## New parts (no sibling line)

- Paperless (paperless-ngx `docs/api.md` lines 121-134, commit `2b00cf6`): page
  through `Source = Bourse Direct` and download originals. A filter on original
  file name finds `BourseDirect_*` documents without that Source. Use a
  view-only Paperless user.
- PDF text: `pdftotext -layout` (Debian `poppler-utils`).
- Row parsing and checks: from the legacy parser (tag `legacy-wip`).
- Ghostfolio lookup by ISIN: decision of 2026-10-14.

## Decisions

- One container serves one Bourse Direct account. Other accounts are counted.
- `PAPERLESS_DONE_TAG` clears only blocking rows after manual correction.
- Identity is `BD#v3#<account>:<KIND>:<row key>`, as ibkr `IBKR#v2#`. The key
  starts with the broker reference, or the first 16 hex characters of the
  original PDF SHA-256. Ghostfolio duplicate detection ignores the account.
  v1 and v2 are legacy.
- Coupon: quantity 1 at the net amount.
- Test data: anonymized `pdftotext` text of real PDFs.

## Known limits

The effect of Ghostfolio `AssetProfileSplit` on held quantities is not known
(GitHub #115). v1 stops on DIVISION in all cases.

Notices do not show the TTF. Ghostfolio cost prices exclude it (Florent,
2026-10-15).

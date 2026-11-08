# Supported notices and limits

Use original Bourse Direct PDF operation notices from a read-only folder or
Paperless. See [Getting started](getting-started.md) for source setup and
[Configuration](configuration.md) for settings.

| Supported | Limits |
| --- | --- |
| EUR PEA and PEA-PME original operation notices | No CTO or arbitrary account types; no statements or OCR scans |
| Text-bearing `ACHAT COMPTANT`, `ACHAT ETRANGER`, `VENTE COMPTANT`, `VENTE ETRANGER` | Exact supported layout and EUR values; foreign labels do not imply FX conversion |
| `COUPONS` | Validated net credit; quantity 1 and fee 0 in Ghostfolio |
| Charged TTF | One unambiguous BUY in the same notice/account/date/ISIN |
| `DROITS DE GARDE` | Reported and ignored; no activity |
| Corporate actions or unknown operations | Held and reported; no automatic transformation |

Missing earlier BUYs can hold a SELL with `sell_exceeds_holding`. Supply the
supported history or resolve opening positions independently. No opening BUY
is invented. This importer is not a complete fiscal ledger.

Read [amount and fee checks](maintenance.md#amounts-and-fees) for TTF attribution
and correction rules. Read [coverage limits](maintenance.md#available-notice-coverage)
before interpreting a partial archive. For blocked operations, follow
[Troubleshooting](troubleshooting.md). Return to the [documentation index](README.md).

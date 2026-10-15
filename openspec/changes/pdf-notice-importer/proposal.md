# Proposal: PDF notice importer

## Why

BillCollector (a separate project) downloads the Bourse Direct notices as PDF
files and publishes them to Paperless. This change reads these files and adds
activities to Ghostfolio, on the `ghostfolio-ibkr-sync` skeleton.

## What changes

- The connector reads the PDF notices from Paperless, read-only.
- One container serves one Bourse Direct account. It imports only the notices
  of that account.
- It imports BUY, SELL and coupons (DIVIDEND at the net amount received).
- It stops on a security when a row changes the number of shares.
- It does not track the TTF and ignores custody fees.
- It does not import duplicates.
- ibkr contract: ENV settings only, simulation when `DRY_RUN` is absent,
  additive writes, `CRON`, `APPRISE_URLS`.

## Operation types

Sources: anonymized real HTML notices (tag `legacy-wip`), one real PDF notice
and one real account statement. Only a BUY was seen as a real PDF. The PDF
form of each other label is open until a real PDF exists.

| Label in a real document | Seen in | v1 behavior |
| --- | --- | --- |
| ACHAT COMPTANT | HTML notice | BUY |
| ACHAT ETRANGER | PDF notice | BUY |
| VENTE COMPTANT, VENTE ETRANGER | HTML notice | SELL |
| COUPONS | HTML notice | DIVIDEND, net |
| DROITS DE GARDE | HTML notice, statement | Ignored, message |
| DIVISION | HTML notice | Stop on security |
| TAXE TRANSACT FINANCIERES | Statement | Not tracked |
| Other label, with ISIN | Not seen | Stop on security |
| Other label, no ISIN | Not seen | Not imported, reported |

No saved document shows subscription rights, share withdrawal or share
transfer. The "other label" rows apply.

## Non-goals

- Notice download, broker login, Bitwarden.
- Account statements as input.
- Cash, custody fees, TTF or corporate actions as activities.
- Gross coupon amount and withholding tax.
- Currencies other than EUR.
- Update or delete of Ghostfolio data.
- Recovery tools, labs, release process.

## Capabilities

### New Capabilities

- `notice-import`: read PDF notices from Paperless and add new BUY, SELL and
  DIVIDEND activities to the Ghostfolio account of one Bourse Direct account.

### Modified Capabilities

None.

## Impact

New main Python file, image, `compose.yaml`, README and tests. Rollback:
revert the commits.

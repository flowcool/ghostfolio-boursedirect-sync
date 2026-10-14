# Proposal: PDF notice importer

## Why

The v1 rebuild needs a small and safe importer. BillCollector (a separate
project) downloads the Bourse Direct notices as PDF files. This change reads
these files and adds activities to Ghostfolio, on the `ghostfolio-ibkr-sync`
skeleton.

## What changes

- The connector reads the PDF notices in one mounted folder.
- It imports BUY, SELL and coupons (DIVIDEND at the net amount received).
- It stops on a security when a row changes the number of shares.
- It stops the run on a TTF line. The operator enters the TTF.
- It ignores custody fees, with a message.
- It does not import duplicates.
- ibkr contract: ENV settings only, simulation when `DRY_RUN` is absent,
  additive writes, `CRON`, `APPRISE_URLS`.

## Operation types

Sources: anonymized real HTML notices (tag `legacy-wip`), one real PDF notice
and one real account statement. The PDF has the same labels as the HTML notice.

| Label in a real document | Seen in | v1 behavior |
| --- | --- | --- |
| ACHAT COMPTANT | HTML notice | BUY |
| ACHAT ETRANGER | PDF notice | BUY |
| VENTE COMPTANT, VENTE ETRANGER | HTML notice | SELL |
| COUPONS | HTML notice | DIVIDEND, net |
| DROITS DE GARDE | HTML notice, statement | Ignored, message |
| DIVISION | HTML notice | Stop on security |
| TAXE TRANSACT FINANCIERES | Statement | Stop the run |
| Other label, with ISIN | Not seen | Stop on security |
| Other label, no ISIN | Not seen | Not imported, reported |

No saved document shows the labels of subscription rights, share withdrawal or
share transfer. The "other label" rows apply to them.

## Non-goals

- Notice download, Bourse Direct login, Bitwarden.
- Account statements as input.
- Cash balance, cash deposits, custody fees, TTF or corporate actions as
  activities.
- Gross coupon amount and withholding tax.
- Currencies other than EUR.
- Update or delete of Ghostfolio data.
- Recovery tools, labs, release process.

## Capabilities

### New Capabilities

- `notice-import`: read PDF notices from a folder and add new BUY, SELL and
  DIVIDEND activities to one Ghostfolio account.

### Modified Capabilities

None.

## Impact

New main Python file, image, `compose.yaml`, README and tests. Rollback: revert
the change commits. Simulation is the default.

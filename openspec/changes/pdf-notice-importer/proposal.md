# Proposal: PDF notice importer

## Why

Read notices from Paperless into Ghostfolio. Adopt the complete
applicable IBKR v3.0.0 core, with explicit Bourse Direct adaptations.

## What changes

- Read PDF notices from Paperless, read-only.
- One container imports notices for one Bourse Direct account.
- It imports BUY, SELL and coupons (DIVIDEND at the net amount received).
- It stops on a security when a row changes the number of shares.
- It does not track the TTF and ignores custody fees.
- It does not import duplicates.
- Maximize exact manual matches, then minimize their total date distance.
- Retain IBKR startup checks, complete activity reads, position guards,
  import confirmation, failure summaries, notifications and scheduling.
- The design pins the source.

## Operation types

Sources: retained real YTD PDF/HTML notices and an account statement.
PDF evidence covers BUY, SELL, COUPONS, custody fees and DIVISION.
Private originals stay outside Git.

| Label in a real document | Seen in | v1 behavior |
| --- | --- | --- |
| ACHAT COMPTANT | PDF notice | BUY |
| ACHAT ETRANGER | PDF notice | BUY |
| VENTE COMPTANT, VENTE ETRANGER | PDF notice | SELL |
| COUPONS | PDF notice | DIVIDEND, net |
| DROITS DE GARDE | PDF notice, statement | Ignored, message |
| DIVISION | PDF notice | Stop on security |
| TAXE TRANSACT FINANCIERES | Statement | Not tracked |
| Other label, with ISIN | PDF notice | Stop on security |
| Other label, no ISIN | Not seen | Not imported, reported |

SOUSCRIPTION and ATTRIBUTION appear in retained PDFs. Apply the "other label"
rules. Share withdrawals and transfers remain unverified.

## Non-goals

- Notice download, broker login, Bitwarden.
- Account statements as input.
- Cash, custody fees, TTF or corporate actions as activities.
- Gross coupon amount and withholding tax.
- Currencies other than EUR.
- Update or delete of Ghostfolio data.
- IBKR Flex, cash reconciliation and historical identity conversion.

## Capabilities

### New Capabilities

- `notice-import`: read PDF notices from Paperless and add new BUY, SELL and
  DIVIDEND activities to the Ghostfolio account of one Bourse Direct account.

### Modified Capabilities

None.

## Impact

Typed Python package, image, `compose.yaml`, README and
tests. Reuse IBKR image, CI and release checks, and the existing infra lab.
Replace the legacy runtime. Rollback: revert commits; retain imports.

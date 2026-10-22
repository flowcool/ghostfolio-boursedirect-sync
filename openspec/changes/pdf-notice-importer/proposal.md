# Proposal: PDF notice importer

## Why

Read BillCollector notices from Paperless into Ghostfolio. Adopt the complete
applicable IBKR v3.0.0 core, with explicit Bourse Direct adaptations.

## What changes

- The connector reads the PDF notices from Paperless, read-only.
- One container serves one Bourse Direct account. It imports only the notices
  of that account.
- It imports BUY, SELL and coupons (DIVIDEND at the net amount received).
- It stops on a security when a row changes the number of shares.
- It does not track the TTF and ignores custody fees.
- It does not import duplicates.
- Retain IBKR startup checks, complete activity reads, position guards,
  import confirmation, failure summaries, notifications and scheduling.
- Bourse Direct financial rules stay authoritative. The design pins the source.

## Operation types

Sources: real anonymized HTML notices (`legacy-wip`), one PDF notice and one
account statement. Only BUY has PDF evidence. Other forms remain unverified.

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

Subscription rights, share withdrawals and transfers remain unobserved.
Apply the "other label" rules.

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

New typed Python 3.14 application package, image, `compose.yaml`, README and
tests. Reuse IBKR image, CI and release checks, and the existing infra lab.
Replace the legacy runtime. Rollback: revert commits; retain imports.

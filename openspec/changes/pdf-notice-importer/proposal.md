# Proposal: PDF notice importer

## Why

Import Paperless notices into Ghostfolio. Adopt complete applicable IBKR v3.0.0 core.

## What changes

- One container imports notices for one Bourse Direct account.
- It imports BUY, SELL and coupons (DIVIDEND at the net amount received).
- It stops on a security when a row changes the number of shares.
- It adds uniquely attributed, charged TTF to BUY fees and ignores custody fees.
- It does not import duplicates.
- Maximize exact manual matches, then minimize their total date distance.
- Retain IBKR startup checks, complete activity reads, position guards,
  import confirmation, failure summaries, notifications and scheduling.

## Operation types

Sources: saved real notices and a statement. Originals stay private.

| Label in a real document | Seen in | v1 behavior |
| --- | --- | --- |
| ACHAT COMPTANT | PDF notice | BUY |
| ACHAT ETRANGER | PDF notice | BUY |
| VENTE COMPTANT, VENTE ETRANGER | PDF notice | SELL |
| COUPONS | PDF notice | DIVIDEND, net |
| DROITS DE GARDE | PDF notice, statement | Ignored, message |
| DIVISION | PDF notice | Stop on security |
| TAXE TRANSACT FINANCIERES | PDF notice, statement | Charged TTF in associated BUY fee |
| DET DROIT DE SOUSCRIPTION, INDEMNISATION, ESPECES SUR OST, ATTRIBUTION, RETRAIT TITRES FISCALISE | PDF notice | Stop on security |
| Other label, with ISIN | PDF notice | Stop on security |
| Other label, no ISIN | Not seen | Not imported, reported |

Retained notices cover October 2025–October 2026. Absent error cases keep
logged errors/protections; no new original is required. Other sources remain unverified.

## Non-goals

- Notice download, broker login, Bitwarden.
- Account statements as input.
- Cash, custody fees, standalone TTF or corporate-action activities.
- Gross coupon amount and withholding tax.
- Currencies other than EUR.
- Deletes and updates other than the approved BUY fee-only correction.
- IBKR Flex, cash reconciliation and historical identity conversion.

## Capabilities

### New Capabilities

- `notice-import`: import notices into one account.

### Modified Capabilities

None.

## Impact

Package, image, Compose, README and tests. Reuse IBKR checks and Infra labs.
Continue the current v1. Correct only an exact existing BUY whose fee is
brokerage alone. Preserve all other fields; confirm the charged TTF correction.
Rollback: revert commits; retain accepted financial state.

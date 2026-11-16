# Creation cut-off

## Why

Historical notices can differ from manual activities after a split or a price
correction. These differences must not create another activity.

## What Changes

Add optional `IMPORT_CREATE_FROM=YYYY-MM-DD`. Empty or absent means no cut-off.
Never create a row before this date. Keep historical rows for review and coverage.
Use the Paperless document date (`created`) for unreadable notices only.
An unreadable notice before the cut-off does not block normal writes.
Missing or invalid date evidence retains the existing write block.
Log excluded row and document counts. Keep full coverage findings.

| Operation | Scope |
| --- | --- |
| ACHAT COMPTANT, ACHAT ETRANGER, VENTE COMPTANT, VENTE ETRANGER, COUPONS | Creation cut-off; full review and coverage |
| TAXE TRANSACT FINANCIERES | Existing same-notice attribution |
| DROITS DE GARDE | Existing information only |
| DIVISION, DET DROIT DE SOUSCRIPTION, INDEMNISATION, ESPECES SUR OST, ATTRIBUTION, RETRAIT TITRES FISCALISE | Full coverage; historical stops do not block recent creations |

## Capabilities

### Modified Capabilities

- `notice-import`: creation cut-off and historical unreadable-notice handling.

## Non-goals

No historical acknowledgement list, quantity repair, inferred security, deletion,
broker access, production write, deployment or release publication.

## Impact

Extend ENV validation, notice dates, selection and counts. Keep current review
authority and exact readback. No new dependency. Deliver with v2.1.

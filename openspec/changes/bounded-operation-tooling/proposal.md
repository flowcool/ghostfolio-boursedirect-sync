# Proposal

## Why

Production validation lacks tested target, backup, bearer-delivery and preservation commands. Existing financial commands suffice; assembling them manually cannot enforce the missing boundaries.

## What Changes

- Add bounded preparation and proof commands behind `scripts/operation_run.py`; retain Compose and `recover-notice-write`.
- Trace each obligation to reused source/tests, demonstrated gaps and offline acceptance.
- Florent accepted this limited scope and required traceability on 2026-10-14 (`infra-srpp`). No implementation or live authority follows from this proposal.

The notice source and `unattended-notice-import` semantics remain unchanged:

| Observed operation | Existing scope |
| --- | --- |
| ACHAT COMPTANT / ACH CPT; VENTE COMPTANT / VTE CPT; ACHAT / VENTE ETRANGER | BUY/SELL |
| COUPONS | DIVIDEND |
| DROITS DE GARDE; TAXE TRANSACT FINANCIERES; DIVISION; DET DROIT DE SOUSCRIPTION; RETRAIT TITRES FISCALISE; TRANSFERT VALEUR; INVESTISSEMENT ESPECES | Out |

## Non-goals

New financial logic, automatic phase progression, retries, new labs/volumes, other-service changes, financial rollback, or `infra-a3ri` dispatch-scope semantics.

## Capabilities

### New Capabilities

- `operation-tooling`: bounded target preparation, secret delivery and preservation evidence.

### Modified Capabilities

None.

## Impact

Future repository CLI/tests and README only. No new dependency. Existing operation-plan commands require amendment and separate Florent validation after delivery/tests. Planning rollback: revert this commit.

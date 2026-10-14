# Proposal

## Why

Existing commands lack tested preparation/transport/preservation boundaries.

## What Changes

- Retain Compose, `recover-notice-write` and separate `infra-a3ri` scope.
- Trace schemas/phases, crash-safe authority, stdin bearer, strict preservation and six slices.
- Florent approved five corrections and the config exception (`infra-srpp`, 2026-10-14).

Notice semantics:

| Observed operation | Existing scope |
| --- | --- |
| ACHAT COMPTANT / ACH CPT; VENTE COMPTANT / VTE CPT; ACHAT / VENTE ETRANGER | BUY/SELL |
| COUPONS | DIVIDEND |
| DROITS DE GARDE; TAXE TRANSACT FINANCIERES; DIVISION; DET DROIT DE SOUSCRIPTION; RETRAIT TITRES FISCALISE; TRANSFERT VALEUR; INVESTISSEMENT ESPECES | Out |

## Non-goals

Financial redesign, progression/retry, new labs/volumes, other-service changes/financial rollback. Credential provisioning is operator-owned.

## Capabilities

### New Capabilities

- `operation-tooling`: bounded preparation, transport and evidence.

### Modified Capabilities

None.

## Impact

Future CLI/tests/README. Delivery precedes executable-plan approval; no implementation/live authority. Rollback: revert commit.

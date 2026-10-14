# Proposal

## Why

Existing Compose/product commands lack bounded AT1 transport/preservation. Reuse ADR0007 projection.

## What Changes

Separate canonical IBKR additions, adapter adoption and Bourse Direct controls. Persisted activities/native cash block; aggregates are diagnostics. Receipts cover mutations. Remove V1 backup inventories/restoration/deployment rollback.

| Observed operation | Scope |
| --- | --- |
| ACHAT COMPTANT / ACH CPT; VENTE COMPTANT / VTE CPT; ACHAT / VENTE ETRANGER | Existing BUY/SELL |
| COUPONS | Existing DIVIDEND |
| DROITS DE GARDE; TAXE TRANSACT FINANCIERES; DIVISION; DET DROIT DE SOUSCRIPTION; RETRAIT TITRES FISCALISE; TRANSFERT VALEUR; INVESTISSEMENT ESPECES | Out |

## Non-goals

New package/service/repository/lab/volume, other-service writes, broker-policy sharing, cash writes, financial repair/retry, backups/restore/rollback tooling. Credential provisioning remains operator-owned.

## Capabilities

### New Capabilities

- `operation-tooling`: bounded existing-command execution and evidence.

### Modified Capabilities

None.

## Impact

Future CLI/tests/README; sibling changes require separate approval. Existing operation-plan rules apply. Florent permits production Ghostfolio reads/dry-run and one daily broker acquisition maximum, retained privately; no financial import/recovery confirmation is currently authorized.

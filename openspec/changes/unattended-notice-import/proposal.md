# Proposal

## Why

v0.1.1 needs terminal account selection and never imports. v0.2 imports notices unattended using the IBKR/DEGIRO contract.

## What Changes

- **BREAKING**: rebuild on siblings, retaining proven Bitwarden/TOTP login and notice parsing.
- Read notices only, over 90 days, for one explicit PEA/PEA-PME per service.
- `DRY_RUN=0` imports; `1` or absent simulates. First acceptance uses explicit simulation; no new lab.
- Missing `BD_SOURCE_ACCOUNT_REF`: discover once, log options, stop; no automatic repeated login.
- Require YAML, possibly empty; prioritize overrides, existing Ghostfolio profiles, then lookup. Report unresolved candidates.
- Deduplicate and reconcile holdings before writing; insufficient shares stop the whole run with an error.
- Optional `CRON` and `APPRISE_URLS` failure alerts.

| Operation considered | v0.2 scope |
| --- | --- |
| ACHAT COMPTANT / ACH CPT | BUY from notice |
| VENTE COMPTANT / VTE CPT | SELL from notice |
| ACHAT / VENTE ETRANGER | BUY/SELL with established EUR amounts |
| COUPONS | DIVIDEND: credited EUR amount, notice date and ISIN |
| DROITS DE GARDE | Out; skip and report |
| TAXE TRANSACT FINANCIERES | Out as separate fee |
| DIVISION | Out; manual handling |
| DET DROIT DE SOUSCRIPTION / RETRAIT TITRES FISCALISE | Out; manual handling |
| TRANSFERT VALEUR | Out |
| INVESTISSEMENT ESPECES | Out; no cash updates |

Brokerage stays attached to trades. Unsupported notice rows skip and report; valid rows continue unless reconciliation blocks. Operations absent from notices cannot be reported.

## Non-goals

Full historical reconstruction, balance reconciliation, currency conversion, corporate actions, standalone MANUAL fees, automatic correction/deletion, a new lab, or new internal tooling.

## Capabilities

### New Capabilities

- `notice-sync`: unattended account discovery, notice acquisition, mapping, simulation and additive import.

### Modified Capabilities

None.

## Impact

Implementation affects Compose, entrypoint, connector, acquisition and README. Reuse Ghostfolio APIs. Revert the planning commit to roll back.

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
- Recognize manual BUY/SELL by established civil day, exact financial fields and one-to-one multiplicity, without requiring midnight UTC.
- Dry-run lists similar trades (±3 civil days) and dividends (±4), with total/fee/day differences. Manual dividends always require review. Uncertainty stops the whole run before writes.
- Optional `CRON` and `APPRISE_URLS` failure alerts.

| Operation considered | v0.2 scope |
| --- | --- |
| ACHAT COMPTANT / ACH CPT | BUY from notice |
| VENTE COMPTANT / VTE CPT | SELL from notice |
| ACHAT / VENTE ETRANGER | BUY/SELL with established EUR amounts |
| COUPONS | DIVIDEND: credited EUR amount, row date and ISIN |
| DROITS DE GARDE | Out; error log line, run succeeds |
| TAXE TRANSACT FINANCIERES | Out as separate fee |
| DIVISION | Out; manual Ghostfolio entry |
| DET DROIT DE SOUSCRIPTION / RETRAIT TITRES FISCALISE | Out; manual Ghostfolio entry |
| TRANSFERT VALEUR | Out |
| INVESTISSEMENT ESPECES | Out; no cash updates |

Brokerage stays attached to trades. Known out-of-scope rows and rows without ISIN log an error; the run succeeds. Unknown operations and unresolved instruments fail it. An unrecorded corporate action stops a later SELL.

## Non-goals

Full historical reconstruction, balance reconciliation, currency conversion, corporate actions, standalone MANUAL fees, reusing a broker session between runs (GH #67), automatic correction/deletion, a new lab, or new internal tooling.

## Capabilities

### New Capabilities

- `notice-sync`: unattended account discovery, notice acquisition, mapping, simulation and additive import.

### Modified Capabilities

None.

## Impact

Implementation affects Compose, entrypoint, connector, acquisition and README. Reuse Ghostfolio APIs. Revert the planning commit to roll back.

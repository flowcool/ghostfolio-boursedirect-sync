# Proposal

## Why

v0.1.1 needs terminal account selection and never imports. v0.2 imports notices unattended using the IBKR/DEGIRO contract.

## What Changes

- **BREAKING**: rebuild on siblings, retaining proven Bitwarden/TOTP login and notice parsing.
- Read notices for today and the previous 89 days in Europe/Zurich for one explicit PEA/PEA-PME per service; read all Ghostfolio history.
- `DRY_RUN=0` imports; `1` or absent simulates. First acceptance uses explicit simulation; no new lab.
- Missing `BD_SOURCE_ACCOUNT_REF`: discover once, log options, stop; no automatic repeated login.
- Require YAML, possibly empty; prioritize overrides, existing Ghostfolio profiles, then lookup. Report unresolved candidates.
- Reconcile stock at each sale date; later purchases never fund earlier sales. Unproved same-day dependencies refuse.
- Recognize manual trades by established civil day, exact financial fields and one-to-one multiplicity.
- Recognize same-day manual dividends by exact credited total/fees and multiplicity; quantity/price representation may differ.
- Dry-run reports unresolved candidates (trades ±3 civil days, dividends ±4) and differences. Runs never prompt; uncertainty refuses all writes.
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

Full broker-history reconstruction, balance reconciliation, currency conversion, corporate actions, standalone MANUAL fees, reusing a broker session between runs (GH #67), automatic correction/deletion, a new lab, or new internal tooling.

## Capabilities

### New Capabilities

- `notice-sync`: unattended account discovery, notice acquisition, mapping, simulation and additive import.

### Modified Capabilities

None.

## Impact

Implementation affects Compose, entrypoint, connector, acquisition and README. Reuse Ghostfolio APIs. Revert the planning commit to roll back.

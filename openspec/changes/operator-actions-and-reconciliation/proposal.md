# Proposal

## Why

The published importer adds valid notices and prevents duplicates. It cannot
yet give operators the persistent review and bounded corrections available in
IBKR v4.0.0. The accepted v1 contract is now archived.

## What Changes

- Require review of delivered IBKR and BD code, tests and proof before implementation.

- Report success, success with required action, or failure. Repeat unresolved
  action notifications, including simulation. Keep clean runs silent. Preserve v1 failure exit codes.
- Add optional persistent review with exact values, decisions and rejected pairs.
- Add `off`, `conservative`, `balanced` and `permissive` correction profiles.
  Default to `off`. Require unique source/target pairs and validated PDF evidence.
- Separate comment-only migration from financial correction. Share one existing
  activity update per run across manual decisions, profiles, migration and TTF.
- **BREAKING:** require a persistent review file before correcting charged TTF.
  Without it, hold that correction and continue independent imports.
- Preserve exact amounts, notes and unrelated fields. Stop uncertain corrections
  across restarts without resending them. New imports remain additive.

## Operation Scope

Source: the unchanged original-notice corpus used for the archived v1 contract.
Its proposal records the observed labels. This change adds no document source.

| Observed operation | Scope |
| --- | --- |
| ACHAT COMPTANT, ACHAT ETRANGER | BUY import and bounded review |
| VENTE COMPTANT, VENTE ETRANGER | SELL import and bounded review |
| COUPONS | DIVIDEND using net credit and quantity one |
| TAXE TRANSACT FINANCIERES | Uniquely attributed BUY fee; shared correction budget |
| DROITS DE GARDE | Informational; no activity |
| DIVISION | Existing security hold; no corporate-action execution |
| DET DROIT DE SOUSCRIPTION, INDEMNISATION, ESPECES SUR OST, ATTRIBUTION, RETRAIT TITRES FISCALISE | Existing unknown-operation holds; no activity |

Unobserved error shapes use explicitly derived regressions, never altered originals.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `notice-import`: actionable outcomes, persistent review and bounded corrections.

## Non-goals

Broker login, Paperless writes, cash updates, non-EUR conversion, gross coupon
reconstruction, full IBKR corporate-action detection, historical maintenance,
activity deletion, fusion, splitting, automatic schedule activation or publication.

## Impact

Settings, selection, update/readback, summaries, notifications, README and tests.
Reuse IBKR behavior at `e78bf215b1c3a4cf32e6e9bd2990ef13d38324c2`, PRs
[#322](https://github.com/flowcool/ghostfolio-ibkr-sync/pull/322) and
[#328](https://github.com/flowcool/ghostfolio-ibkr-sync/pull/328).
Reuse IBKR's module boundaries without a line-count budget. Keep the existing
exact-image release process.

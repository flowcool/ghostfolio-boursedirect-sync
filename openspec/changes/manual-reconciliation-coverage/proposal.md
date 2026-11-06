# Proposal

## Why

The notice comparison found 24 matched trades with different fees and four
probable manual coupon matches. Released selection can hide these differences
or propose a duplicate payment. It also lacks a full notice coverage report.

## What Changes

- Reuse v2 `ACTIVITY_REVIEW_FILE` and `ACTIVITY_RECONCILIATION`.
  Add manual fee-only BUY/SELL proposals and notice-net DIVIDEND proposals.
  Require file approval, the existing journal and exact readback.
- Search manual coupons within 31 calendar days, inclusively, in either direction.
  Require a unique pair. This does not prove payment identity.
  Permit explicit replacement of a wrong coupon currency with notice EUR.
  Never derive an exchange rate.
- Add `NOTICE_COVERAGE=1`. Report absent supported rows, uncertain matches and
  position changes unexplained by available notices. Send existing redacted alerts.
  This mode makes no financial writes, even with `DRY_RUN=0`.
- Keep already corrected history unchanged. Never delete or create a replacement
  activity to make a correction.
- Archive the completed v2 change and synchronize its released contract first.

## Operation Scope

Source: the retained 86-notice comparison. It contains the labels below.
The importer cannot parse account or position statements. Scope is notices only.
Absolute statement-position reconciliation remains unavailable.

| Observed operation | In scope / out of scope |
| --- | --- |
| ACHAT COMPTANT, ACHAT ETRANGER | Coverage; manual BUY fee correction |
| VENTE COMPTANT, VENTE ETRANGER | Coverage; manual SELL fee correction |
| COUPONS | Coverage; manual net/date correction |
| TAXE TRANSACT FINANCIERES | Existing unique BUY attribution; no estimate |
| DROITS DE GARDE | Existing information; no activity |
| DIVISION | Report unsupported; no split execution |
| DET DROIT DE SOUSCRIPTION, INDEMNISATION, ESPECES SUR OST, ATTRIBUTION, RETRAIT TITRES FISCALISE | Report unsupported; no correction/import |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `notice-import`: manual corrections and full available-notice coverage reporting.

## Non-goals

Broker login, Paperless writes, statement parsing, rights/split handling, inferred
opening trades for EMEIS or Millennium, BUY/SELL quantity repairs, deletions,
automatic historical creation outside normal import, or a second review mechanism.

## Impact

Extend existing selection, review, reporting, ENV validation, notifications and
README. No new dependency. This PR changes specifications only. Implementation,
release and production writes require their own authority. Proposed exceptions
replace the former historical-maintenance exclusion only after approval.

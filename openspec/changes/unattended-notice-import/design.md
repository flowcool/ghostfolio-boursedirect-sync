# Design

## Context

See proposal.md. Retained notices and destination evidence show non-midnight manual trades, fee discrepancies and a dividend with different day and total. Venue text does not establish a listing.

## Goals / Non-Goals

Reuse sibling deployment/APIs. Keep functional Python and bounded acquisition. This revision excludes mapping changes, financial corrections and historical reconstruction tooling.

## Decisions

- **Runtime:** adapt IBKR's `../ghostfolio-ibkr-sync/entrypoint.sh` supercronic validation/Compose example and DEGIRO's `../ghostfolio-degiro-sync/entrypoint.sh` one-shot default. Use `boursedirect-sync`; simulate first. Persist account/discovery/login/write state in private keyed YAML; serialize broker runs sharing credentials.
- **Broker:** reuse form/TOTP from `collector/source-authentication-dom.mjs`, vault access from `collector/bitwarden-cli.mjs`, navigation from `scripts/source_qualification.py` and `parse_contract_note`. Preserve one-attempt refusal, logout/cleanup, pinned Playwright seccomp and nonroot sandboxed Chromium. Discovery precedes destination/mapping validation.
- **Mapping:** retain DEGIRO's `verified_mapping_document` in `../ghostfolio-degiro-sync/degiro_to_ghostfolio.py`: readable YAML, possibly empty; overrides → existing profiles → ISIN lookup; unique EUR selection. No venue inference, yfinance/OpenFIGI or mapping selection from reconciliation reports.
- **Ghostfolio:** reuse IBKR's `ghost_exchange_access_token`, complete activity reading and rejected-symbol batch reduction; DEGIRO's durable journal/exact acceptance comparison. Keep activities-only payloads, Decimal, source/destination-account-scoped comments from normalized notice fields and identical-row multiplicity; exclude ticker/URL/capture time. New rows retain source-day midnight UTC; owned recognition/readback stays exact. Source execution time stays in identity/order.
- **Manual reconciliation:** adapt DEGIRO's `match_manual_activity` candidate search, replacing automatic proximity adoption with notice-sync's reviewed contract. Manual BUY/SELL uses established civil day and exact financial fields, consumed one-to-one. Retained provenance or explicit operator confirmation establishes entry context; current server TZ does not. Private keyed evidence records that context. Dry-run completes candidate reporting before refusal: trades ±3 civil days, dividends ±4; quantity × price, signed EUR/percentage differences, day gaps and fees. No amount cutoff. Every manual dividend remains for review, including equivalent quantity/price representations. Unverified context remains blocking.
- **Holdings:** retain IBKR's `ghost_get_existing_orders` net baseline and DEGIRO's `reconcile_trade_holdings` before POST; order pending source date/execution time. Only confirmed BUYs fund dispatched SELLs; recheck after rejection.

## Risks / Trade-offs

Unresolved overlap, unknown provenance or ambiguous multiplicity → report, stop the whole run before writes. Missing EUR proof/nonzero TVA → skip, fail; never infer semantics. Lookup uncertainty → retain overrides. Dry-run does not prove persistence.

## Migration Plan

Retain previous private state/image for rollback. Revert the planning commit without service changes.

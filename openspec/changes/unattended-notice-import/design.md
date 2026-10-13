# Design

## Context

See proposal.md. Saved real captures contain domestic/foreign trades, coupon notices with ISIN, and custody charges without ISIN. The existing parser extracts execution venue, but that does not identify a Yahoo listing.

## Goals / Non-Goals

Reuse sibling deployment and API mechanisms. Keep a functional Python connector and bounded broker acquisition. Do not carry forward the legacy request-controller framework or build acceptance tooling.

## Decisions

- **Runtime:** adapt `../ghostfolio-ibkr-sync/entrypoint.sh` (validated supercronic schedule), its README Compose example, and `../ghostfolio-degiro-sync/entrypoint.sh` (one-shot default). Name the service `boursedirect-sync`. Explicit simulation is the first slice; imports remain a product feature. Persist account/discovery/login/write state in private keyed YAML and serialize broker runs across services sharing credentials.
- **Broker:** extract the proven form/TOTP steps from `collector/source-authentication-dom.mjs`, vault operations from `collector/bitwarden-cli.mjs`, account/calendar navigation from `scripts/source_qualification.py`, and `parse_contract_note` from `boursedirect_to_ghostfolio.py`. Preserve one-attempt refusal and logout/cleanup. Use pinned Playwright seccomp, nonroot Chromium, no disabled sandbox. Discovery precedes Ghostfolio/mapping validation so minimal ENV can list accounts.
- **Mapping:** adapt DEGIRO's `verified_mapping_document` (`ISIN: {symbol, currency}`) in `../ghostfolio-degiro-sync/degiro_to_ghostfolio.py`, accepting an empty map. Require EUR. Try existing profiles, then `GET /api/v1/symbol/lookup?query=<ISIN>`. Reject ambiguity instead of choosing the first result or adding yfinance/OpenFIGI; log candidates.
- **Ghostfolio:** reuse IBKR's `ghost_exchange_access_token`, complete activity reading and unresolved-symbol batch reduction; adapt DEGIRO's durable write journal and exact acceptance comparison. Use activities-only payloads. Build stable comments from source/destination account ownership and normalized notice fields, preserving identical-row multiplicity; exclude ticker, retrieval URL and capture timestamp. Midnight UTC preserves the source day in Europe/Zurich. Keep Decimal through serialization/readback.
- **Holdings:** baseline = IBKR's Ghostfolio net quantities (`ghost_get_existing_orders`), not broker positions. Adapt DEGIRO's `reconcile_trade_holdings` before any POST, ordering pending trades by source date/execution time. Unlike IBKR, insufficiency aborts the run. Dispatch BUYs before dependent SELLs; only confirmed purchases fund sales. Recheck after rejected BUYs.

## Risks / Trade-offs

- Lookup varies by installed version and Yahoo availability → verify read-only lookup during the mapping slice; use YAML when unresolved.
- Overlapping notices/manual entries → reuse sibling exact matching; ambiguous multiplicity skips rather than guesses.
- Missing EUR proof or nonzero TVA → report, skip and fail the run; never infer conversion/tax semantics.
- Dry-run proves proposals, not persistence → creation/readback acceptance waits for separately authorized writes; no new lab.

## Migration Plan

Fresh v0.2 ENV/state replaces v0.1.1 bindings; retain old private state for rollback. Pin the previous image to revert runtime. Reverting the planning commit changes no service.

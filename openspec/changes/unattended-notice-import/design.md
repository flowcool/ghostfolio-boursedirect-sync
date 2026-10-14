# Design

## Context

Retained evidence shows non-midnight trades, fee discrepancies and mismatched dividend day/total. Venue does not establish listing.

## Goals / Non-Goals

Reuse sibling deployment/APIs, functional Python and bounded acquisition. Full destination history does not reconstruct broker history. No corrections or new tooling.

## Decisions

- **Runtime:** adapt IBKR's `../ghostfolio-ibkr-sync/entrypoint.sh` supercronic validation/Compose example and DEGIRO's `../ghostfolio-degiro-sync/entrypoint.sh` one-shot default. Use `boursedirect-sync`; simulate first. Persist account/discovery/login/write state in private keyed YAML; serialize broker runs sharing credentials.
- **Broker:** reuse form/TOTP from `collector/source-authentication-dom.mjs`, vault access from `collector/bitwarden-cli.mjs`, navigation from `scripts/source_qualification.py` and `parse_contract_note`. Preserve one-attempt refusal, logout/cleanup, pinned Playwright seccomp and nonroot sandboxed Chromium. Discovery precedes destination/mapping validation.
- **Mapping:** adapt DEGIRO's `verified_mapping_document` in `../ghostfolio-degiro-sync/degiro_to_ghostfolio.py` to accept empty YAML and add existing-profile/ISIN lookup after overrides. Require unique EUR selection; no venue inference, yfinance/OpenFIGI or selection from reports.
- **Ghostfolio:** reuse IBKR's `ghost_exchange_access_token`, complete activity reading and rejected-symbol batch reduction; DEGIRO's durable journal/exact acceptance comparison. Keep activities-only payloads, Decimal, source/destination-account-scoped comments from normalized notice fields and identical-row multiplicity; exclude ticker/URL/capture time. New rows retain source-day midnight UTC; owned recognition/readback stays exact. Source execution time stays in identity/order.
- **Manual reconciliation:** adapt DEGIRO's `match_manual_activity` search to exact same-day comparison and one-to-one multiplicity. Trades require exact financial fields; dividends compare quantity × price with net credit and fees. Retained day provenance remains required; server TZ proves nothing historical. Runs never prompt. Dry-run lists unresolved candidates at ±3/±4 civil days with signed total/fee/day differences before refusal; no amount cutoff or automatic correction.
- **Holdings:** reuse IBKR's complete `ghost_get_existing_orders` read and DEGIRO's `reconcile_trade_holdings` safeguards, replacing the current-net baseline with dated stock. Merge relevant existing and pending trades; count represented notices once. All prior Ghostfolio history funds opening stock; later BUYs never fund earlier SELLs. Use proven source execution order within a day. If preceding-day stock is insufficient and order is unproved, report/refuse. Only exact readback-confirmed BUYs fund dispatch; recheck after rejection.

## Risks / Trade-offs

Unresolved overlap, unknown provenance or ambiguous multiplicity → report, stop the whole run before writes. Missing EUR proof/nonzero TVA → skip, fail; never infer semantics. Lookup uncertainty → retain overrides. Dry-run does not prove persistence. Task 4.2 proves safeguards offline; 5.1 follows without corrections. Final task 6.1 alone owns actual creation, exact response/readback and duplicate-only repeat. It waits for development completion, operator reconciliation and scoped authorization; no runtime safeguard changes.

## Migration Plan

Rollback: retain previous private state/image; revert the planning commit.

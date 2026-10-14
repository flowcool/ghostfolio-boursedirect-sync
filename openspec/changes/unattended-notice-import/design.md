# Design

## Context

Retained trades have non-midnight timestamps and fee discrepancies. Venue does not establish listing.

## Goals / Non-Goals

Reuse siblings, functional Python and bounded acquisition. No broker-history reconstruction, corrections or new tooling.

## Decisions

- **Runtime:** adapt IBKR's `../ghostfolio-ibkr-sync/entrypoint.sh` supercronic validation/Compose example and DEGIRO's `../ghostfolio-degiro-sync/entrypoint.sh` one-shot default. Use `boursedirect-sync`; simulate first. Persist account/discovery/login/write state in private keyed YAML; serialize broker runs sharing credentials.
- **Broker:** reuse form/TOTP from `collector/source-authentication-dom.mjs`, vault access from `collector/bitwarden-cli.mjs`, navigation from `scripts/source_qualification.py` and `parse_contract_note`. Preserve one-attempt refusal, logout/cleanup, pinned Playwright seccomp and nonroot sandboxed Chromium. Discovery precedes destination/mapping validation.
- **Mapping:** adapt DEGIRO's `verified_mapping_document` in `../ghostfolio-degiro-sync/degiro_to_ghostfolio.py` to accept empty YAML and add existing-profile/ISIN lookup after overrides. Require unique EUR selection; no venue inference, yfinance/OpenFIGI or selection from reports.
- **Ghostfolio:** reuse IBKR's `ghost_exchange_access_token`, complete activity reading and rejected-symbol batch reduction; DEGIRO's durable journal/exact acceptance comparison. Keep activities-only payloads, Decimal, source/destination-account-scoped comments from normalized notice fields and identical-row multiplicity; exclude ticker/URL/capture time. New rows retain source-day midnight UTC; owned recognition/readback stays exact. Source execution time stays in identity/order.
- **Manual reconciliation:** adapt DEGIRO's `match_manual_activity` search to exact same-day comparison and one-to-one multiplicity. Trades compare exact fields; dividends compare net credit and fees. Retained provenance or explicit legacy acceptance supplies the day; server TZ proves nothing historical. No prompts or amount cutoff. Report ±3/±4-day candidates and differences before refusal.
- **Holdings:** reuse IBKR's complete `ghost_get_existing_orders` read and DEGIRO's `reconcile_trade_holdings`. Require stock-day proof only for account/instrument keys with a pending SELL. Preserve relevant history, including pre-window trades, and count represented notices once. Later BUYs never fund earlier SELLs. Use source-proven intraday order. Refuse insufficient stock or unproved required order. Without a pending SELL, return all proposals in source order. Only exact readback-confirmed BUYs fund dispatch; recheck after rejection.

## Risks / Trade-offs

Explicit legacy acceptance binds a complete snapshot by private path/SHA-256, account, approval reference and IANA display timezone. Its displayed days remain an uncertain convention, not historical proof. Changed, missing or additional manual history refuses. Genuine entry receipts take precedence. No automatic correction or execution-order inference occurs. Complete offline simulation precedes separately authorized real import.

Unresolved overlap, unaccepted provenance or ambiguous multiplicity stops writes. Missing EUR proof/nonzero TVA skips and fails. Lookup uncertainty retains overrides. Offline checks do not prove persistence. Task 6.1 alone validates real creation/readback/repeat after development, reconciliation and distinct authorization.

## Migration Plan

Rollback: retain previous private state/image; revert the planning commit.

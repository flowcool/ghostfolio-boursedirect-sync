# Pure preparation source replay

`compute_prepared_sources(config_raw, documents, max_bytes, max_depth)` returns
`artifact` and ordered ledger `snapshots`, without files, network, locks or state.
Each configured alias has exactly `statement` bytes and ordered `notes` bytes;
the complete capture schema and byte bounds are checked before HTML parsing.
Limits are positive exact integers. Preparation retains existing financial
matching, unsupported-operation refusal, source hashes, stable IDs and ordering.

`validate_prepared_sources` compares the full typed keyed YAML artifact with that
recomputation. Only mapping key order normalizes; scalar types, extra fields,
sequence order, byte hashes and financial identities must match. Reordering note
captures changes ordered source provenance even when financial rows remain equal.

This qualifies the currently supplied configuration. Existing prepared artifacts
have no configuration hash and omit mapping evidence reference strings. A change
only to those nonempty references can produce the same artifact. Execution must
separately pin the current configuration in its reviewed operator declaration;
this is not proof of historical configuration immutability or broker authenticity.

The existing `prepare` publisher captures each config/document once and calls this
computation before its unchanged journal revision guards and account-binding locks.
All original captured paths still participate in publication collision checks.
Replay alone never updates or resolves the preparation ledger.

Design: `docs/plans/2026-10-09-qualified-application.md`, Gate1, independently
approved by Astra. Tests: `tests/test_preparation_replay.py` plus existing
preparation, source, identity and preservation tests. No production execution.

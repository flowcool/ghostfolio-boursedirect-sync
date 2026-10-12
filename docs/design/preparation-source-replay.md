# Pure preparation source replay

## Scope after the 2026-10-12 daily amendment

The helper below replays the existing statement-based preparation format.
The amended [daily product contract](daily-saved-input-preview.md) requires
notice-only preparation with no monthly source cross-checking. Exact replay of
original notice bytes remains required; replay must not add a statement dependency.
`validate_prepared_sources` also accepts the notice preparation format below;
qualified application replays its original notices through the same boundary.

## Independent notice preparation

`prepare` accepts `schema_version: 1`, `source_mode: notices`, `account`,
`mappings`, explicit `as_of`, and keyed `notices`. Each notice entry has `date`
(the captured source calendar day) and `document` (a local HTML path). One
original notice is allowed per source calendar day. No statement reference or
monthly ledger is accepted. Paths use the existing bounded local reader.

`compute_prepared_notices` recomputes the exact source parser, EUR mappings,
net dividend conversion and approved90day selection. It returns the existing
internal preparation artifact with source-account event markers and original
notice hashes; individual activities retain `import_ready: false`. The complete
supplied note bytes participate in replay, including out-of-window notices.
Presentation whitespace changes therefore invalidate the frozen preparation.

Daily diagnostics can report supported candidates alongside source exceptions.
Application preparation requires every supplied notice to parse and every
in-window supported operation to have qualified mappings/currency; unresolved
source exceptions refuse with `NOTICE_APPLICATION_SOURCE_UNQUALIFIED`. Missing
ISIN exclusions remain allowed. This is a source qualification gate for a write,
not a monthly matching requirement or a legacy resolution workflow.

`prepare` publishes the existing `prepared-<account-uuid>.yaml` output and a
separate target-bound `notice-preparation` revision journal, using existing
account/target locks and binding checks. Original notice hashes persist across
window changes and missing inputs. Same-day byte changes refuse before replacing
output or retained state. It does not modify the historical statement ledger.
Qualified application archives each original notice and its exact config before
dispatch, then reuses the existing per-event intent, baseline, acceptance,
readback and uncertain-result controls. Dryrun/default application gates remain.


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

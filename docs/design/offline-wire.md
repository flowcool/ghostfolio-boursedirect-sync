# Offline reviewed wire and acceptance contract

`build_wire_payload(keyed_activities)` produces private deterministic UTF-8 JSON
bytes and their SHA256. This pure helper performs no persistence or HTTP and
always returns `import_ready=false`. It accepts internal Decimal records or their
canonical decimal strings from a preparation artifact. It requires one immutable
account-key/target binding, valid stable ownership markers, explicit EUR YAHOO
BUY/SELL, valid symbol/calendar date, positive quantity/price and nonnegative fee.
It never derives activities from unsupported records or includes private source
fields in the allowlisted DTO.

The numeric boundary checks the shortest `json.dumps` token after binary64
conversion against the original Decimal, without epsilon or rounding. Safe
integral values use integer tokens after the same check. Precision loss, overflow,
underflow, floats, booleans and nonfinite inputs block the entire payload.
Scientific tokens may be emitted for exactly preserved source values; canonical
prepared strings remain plain decimals. This checks emitted decimal value, not
binary-exact storage or universal server precision.

Activities sort by source calendar day then stable marker, matching preparation's
ordering; same-day execution chronology is not invented. Dates use explicit
`T00:00:00.000Z`. Source execution clocks remain private evidence. Canonical
object keys, compact separators and allowlisted fields fix the bytes. A future
transport must send those exact reviewed bytes; rebuilding another body is outside
this contract. Producing bytes proves neither source approval nor write readiness.

`reviewed_wire_rows(review)` checks the digest, false readiness, exact DTO keys,
identity/account/date/numeric rules, and byte-for-byte canonical reconstruction.
It rejects a changed body, a recomputed digest over noncanonical bytes, extra DTO
fields, duplicate markers/JSON keys and invalid numeric tokens.

`compare_import_response(review, raw_json)` compares raw number tokens as Decimal
against those submitted bytes. Every accepted row must have a unique remote ID,
one submitted marker, exact target account/type/currency, matching current asset
profile (legacy only when current is absent), exact financial values and the same
timezone-qualified instant. Equivalent numeric spellings and offset-qualified
representations of that instant are equal. Same-day different instants fail.

Results distinguish `complete`, `skipped` (empty accepted array), `partial` and
`conflicting` (malformed, unexpected, duplicated or changed rows). Positive exact
rows encountered before a conflict remain evidence, never permission to retry.
The helper reports codes and missing markers and keeps readiness false. A POST
response lacks complete account/tag/active context: full snapshot readback remains
mandatory. Neither empty POST nor empty GET can clear an uncertain write fence.
HTTP status handling, transport, immutable persisted review bytes, durable intent,
crash recovery and isolated delayed-insertion rehearsal remain separate gates.

Evidence: [reviewed numeric policy](../plans/2026-10-08-manual-document-import.md),
[pinned isolated API observations](ghostfolio-api-lab.md) and
[full snapshot adoption](offline-adoption.md). Synthetic socket-forbidden tests
cover exact numbers, unsafe integers, excessive precision, scientific notation,
review tampering, target ownership, dates, multiplicity and response conflicts.
Rollback: revert the scoped local commit; existing private artifacts and journals
are unchanged. Blast radius is local code/tests/documentation, with no network.

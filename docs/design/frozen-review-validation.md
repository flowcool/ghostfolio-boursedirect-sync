# Frozen review validation

The callable `compute_offline_review(config_raw, captures, max_bytes)` computes the
existing strict offline review from captured bytes. `review` uses the same helper.
The capture map has exactly prepared, snapshot, resolutions and history_evidence.
Configuration references are validated and hashed, but the helper does not resolve
paths. Trusted orchestration must capture the actual referenced files once.

`validate_frozen_review(review_raw, review_sha256, config_raw, captures, max_bytes)`
requires an external lowercase SHA256 pin of the saved report bytes, then compares
its complete restricted-YAML content with recomputation. Sorted safe YAML
serialization normalizes mapping order while preserving scalar types, sequence
order and nulls. A matching pin proves bytes; it does not prove human approval.
Changed provenance, inputs, binding, dispositions, blockers, holdings or wire fail.
Readiness remains false. A shortfall report can contain diagnostic wire; callers
must still reject dispatch. An all-existing report has null wire.

Each input must be bytes within a positive exact-integer budget. The existing
strict YAML loader rejects anchors/aliases, duplicate/nonstring keys and nesting
beyond32 before construction. Snapshot numeric shapes are bounded before holdings
and financial fingerprinting. Aggregate potential holdings precision is capped
at10000 or the smaller byte budget, with the existing28-digit minimum and8-digit
margin. All prepared quantities and potentially contributing target/security
BUY/SELL snapshot quantities count, including currently inactive/future rows.
This is a development resource bound, not financial rounding.

The helpers perform no file/network/persistence operation. Existing eligibility
rules evaluate the current clock; an old report can become invalid when a future
activity becomes eligible. The pin authenticates neither capture time nor source
origin. Preparation source declarations are not raw-document authenticity proof.

The owned disposable runner validates before its first source POST, uses the same
captured preparation and snapshot, and retains a private frozen bundle under
`inputs/frozen-review/`: config.yaml, review.yaml, four role `.bytes` files and
pin.yaml. These survive repeat review and compensation, allowing offline cold
replay after teardown. The fixture controller pin is lab integrity evidence only.
No production application command, write authorization or recovery override is
introduced. See the [approved plan](../plans/2026-10-09-frozen-review-validation.md).

Rollback: revert the scoped implementation commit; retain private captures and
journals. Code rollback does not compensate any remote activity.

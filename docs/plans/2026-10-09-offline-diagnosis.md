# Reproducible offline legacy diagnosis proposal

## Need and evidence

The strict sample has three prepared activities and three likely existing target
trades. Two are blocked by nonmidnight context, one by a fee discrepancy. The
existing review command requires a complete acquisition-history assertion and
explicit adoption evidence before it can produce a review. Those assertions are
not established. A private one-off analysis supplied useful evidence, but future
operators need to reproduce the diagnosis without manufacturing those assertions.

This is a diagnostic extension of the public v0, not a date-policy amendment or
import implementation. Existing reconciliation, holdings, ownership and financial
gates remain authoritative and unchanged. Actual validation owner25 remains open.

## Contract

Add `diagnose --config FILE --input-root DIR --max-bytes N`. Its keyed configuration
has exactly schema_version1, prepared and snapshot references. Capture config and
both bounded regular local files once; existing root/symlink protections apply.
Validate the preparation artifact with the same checks as review and validate the
whole remote snapshot before reporting any candidates. Malformed/redacted input
fails without replacing any previous diagnosis. Source binding and source digests
must be preserved. No credentials, network, history declaration or resolutions.

For each prepared source, record exact financial matches and candidates from the
reviewed one-day legacy rejection predicate. Factor that existing predicate into a
shared pure helper, retaining its behavior exactly. Include all normalized remote
rows, including inactive, unsupported, foreign-owned and already relevant rows.
Candidates reference one keyed remote evidence map containing original saved
timestamp, normalized day and exact financial values/context; source entries carry
IDs and discrepancy fields. Do not duplicate full remote records per source. Do not interpret
source similarity as identity or adopt a candidate. Records without a candidate
are explicitly `NO_CANDIDATE_IN_BOUNDED_CHECK`, never classified as new.

Record owned-marker collisions separately even when they fall outside the numeric
candidate predicate. An owned-marker mismatch must not disappear into no-candidate
diagnostics. The report describes conflicts; it is not a resolution or a delivery
plan. Do not copy the snapshot's full raw records/comments into the report.

Write `outputs/diagnosis-<account-key>.yaml` atomically with 0600 in 0700 outputs,
under the existing target preparation lock. Bind config/prepared/snapshot hashes
and source digests, with schema_version1, explicit diagnostic artifact kind and
`import_ready=false`. No wire field/body, holdings coverage verdict, adoption,
new-activity list or write intent may be generated. Transient existing numeric
validation may remain; no deliverable wire artifact is emitted or persisted.

Stdout contains counts, fixed codes and readiness false only. A readable diagnosis
exits 2; invalid input exits 1. Candidate absence is a bounded observation, not proof
of duplicate absence, mapping correctness, date provenance or complete history.
Error text must not expose paths, account identifiers, comments or financial values.
Before publication, reject an output destination resolving to any captured
config/prepared/snapshot path, with a fixed code and preserved input bytes.
Bound source-count times remote-count to one million comparisons, materialized
candidate references to ten thousand, and encoded output bytes to the supplied
max-bytes budget. Exceeding a budget fails
without publication or silent truncation. Record evaluation time explicitly:
the normalized active flag includes the current-time check and is not immutable
snapshot evidence. The candidate predicate remains independent of that flag.

## Phases and ownership

1. Independent Astra review and resolve design findings before coding.
2. One implementation issue owns shared validation/predicate extraction, diagnostic
   command and discriminating socket-forbidden tests. Preserve existing review and
   quarantine behavior with the complete suite.
3. A separate sequential review issue owns independent financial/security PR review.
   Open the PR and leave it open. CodeRabbit triggers and final merge are managed
   externally under Florent's latest instruction; root must not trigger or merge.
4. Run the public command on existing private saved evidence and compare the three
   known diagnostic cases. Do not renew source acquisition or alter remote state.

Required tests cover exact/near/no candidates, both one-day boundaries and context
differences, owned-marker collisions/duplicate markers, malformed snapshots and
prepared bindings, input/output path collisions, explicit budgets, private permissions,
preservation of existing output and all
inputs/journals, captured-byte provenance, no wire/intent, safe stdout and exits.
Pure diagnosis intentionally makes no complete acquisition or adoption claim.

## Blast radius, rollback and limits

Local pure analysis and ignored private artifacts only; no dependency or external
transport changes. Rollback: revert the scoped implementation; retain snapshots,
preparation, journals and diagnostic artifacts. Verify the revert diff and full
suite. No remote rollback is necessary. Existing source-acceptance criteria are
not copied into this implementation issue or discharged by a diagnostic report.

# Saved-input diagnosis contract

`diagnose --config FILE --input-root DIR --max-bytes N` describes uncertainty
without a complete-history assertion or adoption resolutions. It never contacts
Ghostfolio, adopts records, checks holdings coverage or changes financial facts.
The [Astra-reviewed plan](../plans/2026-10-09-offline-diagnosis.md) defines its scope.

The private keyed configuration has exactly:

```yaml
schema_version: 1
prepared: prepared.yaml
snapshot: snapshot.json
```

Both references must be bounded regular local files within input-root. Copy the
unchanged preparation artifact there, or select a common root containing both
private files. Config and inputs are captured once; report hashes cover exactly
those bytes. Preparation identity/account/trade/numeric/readiness checks are shared
with `review`; the entire snapshot is validated before any output is published.

The report `outputs/diagnosis-<account-key>.yaml` contains source digests, source
observations, candidate references and one keyed remote-evidence map. Exact financial
fingerprints and the existing inclusive one-UTC-day legacy predicate are observations
only. Candidate context flags remain visible; owned-marker collisions are collected
across all rows even outside the similarity predicate. Duplicate ownership and a
remote candidate shared by sources remain unresolved. Raw free-text comments and
full remote records are excluded; ownership labels are fixed codes.

Exact numbers are decimal strings and original saved timestamps are preserved.
`active_at_evaluation` includes the existing current-time check; the report records
evaluation start in UTC and does not claim that eligibility is immutable. Candidate
selection is independent of eligibility. No candidate means only
`NO_CANDIDATE_IN_BOUNDED_CHECK`, never a new import. No history, mapping, date or
identity proof is inferred from that absence or from exact similarity.

Output is atomic 0600 within 0700 outputs under the existing target preparation lock.
Resolved destination/input collisions, including existing hard-link aliases, reject
before replacement. The comparison budget is one million source/remote pairs and
at most ten thousand candidate references are materialized; encoded
report size cannot exceed max-bytes. Exceeding a budget fails without truncation.
Invalid inputs, lock conflicts and collision/budget failures preserve a previous
report. Input bytes and preparation/intent journals are never rewritten.
Path-resolution failures use a fixed `INVALID_OUTPUT_PATH` code rather than logging
paths from an underlying exception.

There is no emitted wire body, new-activity list, adoption resolution, holdings
verdict or write intent. Shared preparation validation may transiently validate
numeric wire representation in memory; those bytes do not enter this artifact.
The diagnostic artifact kind and `import_ready=false` explicitly exclude delivery.
Stdout reports counts and fixed blocker codes only; success exits 2, invalid input
exits 1. Read the private report locally rather than pasting account/financial data.

Tests use synthetic isolated files and forbid sockets and adoption/holdings/intent/
snapshot transport calls. Rollback: revert scoped code/tests/docs and retain private
inputs, diagnoses and journals. No remote rollback is needed.

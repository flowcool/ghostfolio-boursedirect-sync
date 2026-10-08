# Saved-snapshot review command

`review --config FILE --input-root DIR --max-bytes N` is entirely offline. Its
keyed YAML configuration has exactly schema_version1 and four file references:
`prepared`, `snapshot`, `resolutions`, `history_evidence`. All inputs must be
regular bounded local files inside the explicit root, with no symlinks. Each is
read once into captured bytes, used for both parsing and provenance digest.
The prepared YAML is the existing preparation artifact; snapshots are full raw
Ghostfolio activity-list JSON, resolutions are keyed explicit adoption entries,
and history evidence is the snapshot-bound complete-acquisition declaration.

Example private configuration:

```yaml
schema_version: 1
prepared: prepared.yaml
snapshot: snapshot.json
resolutions: adoption-resolutions.yaml
history_evidence: history-evidence.yaml
```

Snapshot-bound evidence (substitute exact private values):

```yaml
kind: complete_acquisition_history
target_account_id: YOUR_TARGET_ACCOUNT_ID
snapshot_sha256: YOUR_EXACT_RAW_SNAPSHOT_SHA256
confirmed_by: YOUR_REVIEWER
reference: YOUR_INDEPENDENT_HISTORY_EVIDENCE_REFERENCE
```

An empty resolutions file must contain `{}`. Matching manual activities require
the resolutions described in [adoption](offline-adoption.md); similarity is never
enough. This command does not fetch a snapshot or establish history completeness.
It fails on stale/missing evidence or unresolved adoption, and checks conservative
[chronological coverage](chronological-holdings.md).

The private artifact `outputs/review-<account-key>.yaml` records engine contract,
exact input SHA256s, source digests, full reconciliation/coverage and blockers.
Only new activities become the [wire](offline-wire.md) body's UTF-8 string plus
its exact digest; all-existing/adopted reviews contain `wire: null`. Holdings
shortfalls may produce a diagnostic body but always block readiness. The artifact
is0600 in0700 outputs, written atomically under the shared preparation target
lock. The retained body string re-encodes to the exact reviewed bytes; no separate
float recomputation is permitted by future delivery. Invalid inputs do not replace
the previous review. No intent journal or external activity is created.

Stdout contains only counts, safe blocker codes and `import_ready=false`. Success
exits2 (readable diagnostic review with remaining gates), invalid input exits1.
All artifacts remain private; run from the repository so ignore rules apply.
Neither creating this file nor its digest authorizes apply. Source approval,
actual destination/account/profile/date version, security review, production
permission and independently verified recovery still stand. A review captures
local files at one read instant; it is not an atomic snapshot of a live system.

Rollback: revert scoped CLI/parser-refactor/tests/docs commit and retain existing
private inputs/journals/reviews. No network, production or shared-state tests.

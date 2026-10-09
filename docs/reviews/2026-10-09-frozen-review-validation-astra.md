# Frozen review validation — Astra design review

Date: 2026-10-09. Scope: the frozen-review plan and existing review, preparation,
adoption, quarantine, holdings, YAML, Decimal and wire helpers, plus the disposable
runner's consumption path. Design review only; no implementation review, private
input inspection, runtime execution, network request or Beads mutation.

Reviewed amended plan: `docs/plans/2026-10-09-frozen-review-validation.md`,
SHA256 `3dfa765b3f39ef980ee55841081c6c4926e65a4f2e77fafcab0b4a69ebd6d1fe`.
Inspected code baseline: Git commit
`d65e655f6ce4e5b3e6964df40c7d99e90d1bae4f`.

**Verdict: APPROVE.** The revised plan incorporates the clock-contract correction
and aggregate precision budget discussed below. The shared computation and typed
comparison are appropriate. No production authorization or source-authenticity
claim follows from this approval. Required tests and owned rehearsal remain
implementation acceptance evidence, not evidence supplied by this review.

1. **Medium, resolved in revised plan — hidden clock dependency.**
   `parse_remote_activity_snapshot` computes eligibility with `datetime.now`,
   and `verify_chronological_holdings` rejects future source days using the same
   ambient clock. Extracting their caller does not yield a deterministic function
   of captured bytes. Preserve current behavior and describe the new helper as
   side-effect-free computation at evaluation time, with no generated timestamp
   or new schema. Recalculation can invalidate an old report when future-date
   eligibility changes; reject the mismatch conservatively. Do not imply that
   the report pin authenticates capture time. Test an eligibility-boundary drift
   with a controlled clock. The implementing agent proposed this exact resolution
   during review and incorporated it in the plan before implementation.

2. **High, addressed by planned gates — recompute all authority-bearing content.**
   The existing runner directly parses the saved report and independently builds
   one-row wire from an earlier prepared object. Checking only wire hashes or
   report shape would leave adoption, holdings, input provenance and blockers
   outside validation. Gate2 correctly compares the entire recomputed report.
   Canonical safe YAML serialization with sorted mapping keys is acceptable for
   typed comparison under the existing restricted loader: bool/int, string/date,
   null and sequence order must remain distinguishable. Plain Python mapping
   equality is insufficient. Test nested substitutions, not only schema_version.
   Return the recomputed value, preserving false readiness and diagnostic wire
   on shortfalls. Null wire is a valid all-existing computation.

3. **Medium, addressed by planned gates — hashes bind bytes, not origins.**
   Hashing exact config bytes binds its reference strings, including path changes;
   hashing each exact captured value binds its named role. The pure boundary
   cannot prove those bytes came from those paths or that referenced HTML,
   mappings and source declarations are true/current. The trusted CLI/runner must
   perform bounded acquisition once, resolve the actual configuration references,
   and pass exactly that capture set. Keep the externally supplied report pin
   separate from the parsed report. A laboratory controller computing that pin
   demonstrates lab integrity only. The plan's explicit authenticity exclusions
   are necessary and sufficient for this scoped boundary.

4. **High, addressed by planned gates — enforce budgets before expensive work.**
   `verify_chronological_holdings` currently parses the raw snapshot, fingerprints
   remote values and sizes Decimal precision from quantity exponents. The new
   boundary must bound numeric shapes before those operations, and mask malformed
   exponent failures with fixed codes. Calling the bounded parser after holdings
   is too late. Ensure any subsequent raw parse cannot bypass the prevalidated
   bytes. Test tiny scientific-notation inputs with huge exponents, whole-snapshot
   redaction and irrelevant numeric fields according to the documented bound
   scope. The existing guard skips zero: this is not a demonstrated holdings
   exploit because trade quantity must be positive and nontrade quantities are
   excluded, but do not later reuse that guard as a universal exponent bound.
   The revised plan also caps aggregate holdings precision cost before entering
   the Decimal context; individually bounded quantities alone do not bound their
   sum. Its conservative inclusion of potentially contributing inactive trades
   prevents clock eligibility from bypassing the budget. Exact-limit and one-over
   tests must establish this additional rejection policy without rounding values.

5. **Medium, addressed by existing loader — avoid alias expansion before comparison.**
   `parse_keyed_yaml` already rejects anchor/alias tokens before compose, enforces
   unique string mapping keys and checks nesting before constructing values.
   Reuse it for every YAML byte input. No new parsed-graph API or global loader
   rewrite is warranted. Byte bounds plus this policy avoid recursive/shared
   alias graphs reaching canonical serialization. Keep negative anchor/cycle,
   excessive nesting and duplicate-key tests, including benign reordered keys
   that must compare successfully under a separately correct raw byte pin.

6. **High, addressed by Gate4 — trusted runner consumption remains a separate gate.**
   Validate before the first source POST and derive dispatch markers and exact
   single-row values from the same validated capture/report chain. Do not validate
   one prepared capture and dispatch from a second read or stale earlier object.
   Keep the current financial-shortfall checks; validation success alone does not
   authorize dispatch. Fake tampering must leave only the fixture seed POST and
   execute owned cleanup. Rehearse the changed owned runner, retain single-row
   archives and uncertainty journals, and prove the zero-new repeat and complete
   owned compensation. Existing single-event locks, baseline checks, tombstones
   and one-POST uncertainty behavior remain independent requirements.

The scoped rollback by commit revert, retaining private evidence and journals, is
appropriate. No new portable operational knowledge was established by this
design review; findings concern this repository's existing computation boundary.

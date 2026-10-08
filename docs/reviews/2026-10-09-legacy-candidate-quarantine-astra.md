# Astra design review: legacy candidate quarantine

Verdict: **APPROVE**, with the wire-artifact wording clarification incorporated
before implementation. Reviewer: independent Codex agent using GPT-6 Astra.
Baseline: `dace2579a155113050f9b207c053cd0e897f60a6`.
Scope: proposed plan, pure parser/reconciliation/holdings/review code and existing
contracts/tests. No private inputs, network, live systems or mutations inspected.

The exact fingerprint includes fee, currency and UTC day. Context rejection only
applies to exact candidates, so a nearby trade with different fees can reach the
new classification. Rejecting that transition strengthens the boundary without
authorizing adoption. The three actual candidates are supplied diagnostic
evidence, not independently verified adoption proof.

Implementation invariants:

- Retain owned-marker and exact-candidate handling, explicit resolutions and
  multiplicity checks unchanged; guard only the no-exact-candidate transition.
- Search all normalized rows, including inactive, unsupported, foreign-owned and
  already claimed rows. Eligibility cannot erase similarity evidence.
- Compare account, symbol, data source, type, quantity and price exactly. Handle
  both Decimal/date values and serialized prepared strings without float tolerance.
- Compare normalized UTC calendar days with inclusive distance zero or one day.
  Do not rewrite dates or infer a historical timezone.
- Ignore fee, price currency and eligibility in the rejection predicate. Preserve
  parser errors for malformed/redacted snapshots.
- Abort safely before a review output is replaced or an intent is created. Errors
  contain codes, never account IDs or trade values.

Required tests: same-day changed fee/nonmidnight context; both one-day boundaries
and two-day negative controls; UTC-crossing offset timestamps; currency and
eligibility discrepancies; independent identity/quantity/price isolation; serialized
prepared values and Decimal scales; already claimed candidates and ordering;
existing ownership/adoption/stale-resolution/multiplicity regressions; CLI rejection
preserving inputs, journal and any previous review artifact; full required suite.

The wording correction distinguishes transient in-memory numeric wire validation
from emitting/persisting a deliverable artifact. Moving unrelated wire validation
is unnecessary. Matching this predicate blocks a new classification; absence does
not prove no duplicates, complete history, correct mapping or readiness. Legitimate
repeated trades can be blocked and need a separate reviewed resolution contract.

KB verdict: **Used and sufficient**. Indexed saved-snapshot and import-date
concepts agree with project contracts; no new corpus mutation from this review.

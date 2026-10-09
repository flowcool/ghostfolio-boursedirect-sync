# Frozen reconciliation computation boundary

Date:2026-10-09. Design owner:`infra-4g8u.53`. Astra review before code.
Autonomous progress continues without PR-review waiting; production writes remain
prohibited. This package introduces no CLI, endpoint or authorization override.

## Problem, authority and scope

The [single-event lab core](../design/single-event-lab-dispatch.md) validates exact
wire and baseline transitions, but the runner manually trusts the saved report
joining source preparation, snapshot, adoption/history and new dispositions.
Original review digest/input invalidation obligations need a reusable computational
boundary before any future application delivery. Inspect the complete current
review command, preparation artifact validator, holdings/adoption/quarantine,
wire validation, bounded snapshot helpers and runner before extraction.

Factor side-effect-free review computation into one helper reused by the
existing offline command and a frozen-report validator. A validated result proves
only equivalence to supplied captured inputs, not source authenticity, current raw
HTML/config/mappings, current remote state, exclusive access, human approval or
production permission. Those remain named gates. Never turn existing false
readiness/blockers into authority, and never infer a history assertion or adoption.

## Gate1 — shared side-effect-free report computation

`compute_offline_review(config_raw, captures, max_bytes)` receives the exact saved
review config bytes and a keyed map containing precisely prepared/snapshot/
resolutions/history_evidence bytes. Enforce positive exact integer byte budget and
bounded bytes for each input before parsing. Validate config schema1/path reference
strings exactly as the CLI currently does, but pure computation never resolves
those paths or reads files. Use the existing strict keyed YAML loader and prepared
artifact schema/binding/canonical-wire checks. Bound numeric snapshot shapes before
holdings/fingerprint/context precision calculation using the extracted guard.
Guard malformed scientific exponent overflow with fixed error codes. Before
holdings precision assignment, cap aggregate quantity digit/exponent contribution
plus its existing8-digit margin at10000 or the smaller max-bytes budget (minimum
context28 still applies). Include all prepared quantities and all potential
target/security BUY/SELL quantities even if currently inactive; conservative
overcount is permitted and cannot hide a later eligibility transition. Existing
finite/positive guards still apply. This is an initial development resource budget,
not a financial precision threshold; characterize exact boundary/one-over fixtures.
No network, files, state, locks, timestamp publication or persistence in this helper.
Existing eligibility/future-source rules read the clock: recomputation evaluates
them now, not at authenticated capture time. Do not describe it as time-invariant
mathematics. If identical captured bytes change disposition/holdings across a
future-date boundary, frozen comparison conservatively fails. Preserve the current
engine/report schema; no fabricated historical evaluation timestamp is added.

Recompute adoption and snapshot-bound complete-acquisition chronology exactly as
the existing review command, including unresolved legacy/date/context/fee failures
and holdings shortfalls. Derive new activities and canonical batch wire solely
from the supplied prepared artifact plus computed dispositions. Preserve current
engine/schema/artifact-kind, exact input/source hashes, target/account, false
readiness, blockers, adoption, holdings and wire representation. All-existing
reviews have null wire. A holdings shortfall can retain diagnostic wire, but stays
blocked; computation does not mean safe delivery. Preserve complete existing
review behavior and publication/input collision guard.

## Gate2 — exact frozen report and external byte pin

`validate_frozen_review(review_raw, review_sha256, config_raw, captures, max_bytes)`
requires bounded raw report bytes and exact lowercase64hex digest matching them.
The digest is an externally supplied caller pin: it proves bytes, not who approved
them. Parse strict keyed YAML, reject missing/additional keys and incompatible
engine/schema/readiness representations, then compare the entire parsed report
against the recomputed expected report with **type-sensitive** equality.
Python bool/int equality cannot accept true as activity_count1/schema_version1.
Canonical YAML or a recursive bounded typed comparison is acceptable if its exact
alias/type normalization policy is documented and tested; do not use plain dict
equality alone. Key order or benign YAML scalar syntax may normalize, but the raw
digest still pins original reviewed bytes.

Changed config/path/provenance, prepared activities or source digests, snapshot,
resolution/history evidence, count/disposition/binding, blocker/shortfall or wire
body/count/digest must fail rather than trust the report's claims. No free-text
completion/production evidence is accepted. Never rewrite inputs, report or
history. Return the recomputed existing report (readiness false) for trusted local
orchestration, not a new authorization artifact or unreviewed payload variant.
Zero-new/null wire is a valid verified computation, not permission to retry a
tombstoned digest. Shortfalls remain valid diagnostic reports, not dispatchable.

## Gate3 — resource, privacy and adversarial evidence

Capture byte limits alone do not bound YAML alias expansion/recursive graphs.
The existing `parse_keyed_yaml` already rejects every anchor/alias before compose,
requires string/unique mapping keys and bounds nesting to32. Reuse that exact
policy for report/config/prepared/resolutions/history bytes before comparison;
no caller-supplied parsed graph or extra global loader policy is accepted.
Characterize ordinary fixtures and alias/cycle attempts; preserve refusal before
expanding serialization. Retained synthetic prepared/review/config/resolutions/
history files were inspected and contain zero anchor/alias tokens.

Socket/filesystem-write/persistence-forbidden tests cover current report
recomputation and zero-new/null wire, diagnosed shortfall, wrong external digest,
whole report/input/provenance/wire tampering, true-as1, missing/additional keys,
key ordering/typed YAML normalization, stale adopted IDs/fee/date/quarantine,
whole snapshot redaction, malformed scientific exponents, aggregate precision
boundary/one-over, time-eligibility drift, size/alias/cycle bounds
and no input mutation. Existing review tests retain publication behavior.

## Gate4 — trusted runner consumption and delivery

Before the first source dispatch, the owned runner captures its actual saved
review/config/fourinputs once, externally pins the report's raw SHA256 and calls
the validator. Use only recomputed new dispositions/wire after success. Fail before
any source POST on invalid report/input. A pin calculated by the fixture controller
is explicitly laboratory evidence, never human production approval. Original
private report/batch and actual single-row archives remain unchanged.

Add fake-runner tamper failure proving only seed POST occurs and all owned cleanup
still runs. Required full suite, semantic diff/numstat/privacy audit before commit.
Repeat the explicit owned3.81.0 fixture rehearsal if integration changes to verify
three source POSTs/threeconfirmed/count6/zero-new repeat/compensation6/count0 and
resource absence. Open stacked PR, leave review/merge external; root production
and real source/adoption/history gates stay open.

Blast radius: pure application computation/validation, its existing offline review
caller, tests/docs and newly owned disposable fixture adapter. Rollback: revert
scoped commit; retain private inputs/reports/journals. No real broker/production
request or new operational secret/authorization policy is introduced.

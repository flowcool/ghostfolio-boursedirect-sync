# Offline retained-intent verification — Astra design review

Date: 2026-10-09. Design owner: `infra-4g8u.45`.
Final verdict: **APPROVE** the amended plan for the specified offline implementation.
The initial review required two design corrections; both are addressed below.
This is the required independent design gate, not a PR review. CodeRabbit review
and final merge remain external.

## Scope and evidence

Reviewed the proposed [offline verification plan](../plans/2026-10-09-offline-intent-verification.md)
against project guidance, Python/security rules, the original reviewed manual
import plan, and the wire, write-intent, schema and diagnosis contracts. Inspected
the complete relevant input/YAML/private-publication helpers, snapshot normalizer,
financial fingerprint, wire builder/validator, journal validator/transitions,
resolution/persistence helpers, existing offline command publication and CLI.

Code baseline: `ec4565de6d08768b8daae2076863e39bc90ff04e`. The reviewed plan was
an untracked proposal at review time. Initial finding line references apply to
plan SHA256 `6c5900fdb84ce2ec5c85bff133996f24d93de6a0953c2f7a25030542e0a95af6`.
The follow-up review read the complete amended plan at SHA256
`7777fc7a80b6f1c245020467a81740ce4da7bf697cc5459bc14f483b89647372`.
The final approval applies to that amendment and the implementation checks below.

No network request, Docker operation, private account/lab-file read, Beads access,
test execution or implementation edit occurred. Only this report was written.
The availability and contents of retained count6/count0 lab artifacts are supplied
design prerequisites, not independently established by this review.

## R1 — A saved capture cannot establish post-quiescence chronology

Severity: medium. **Addressed in the amended plan.**

Evidence: Gate2 lines 78–82 proposes `POST_QUIESCENCE_ACTIVITY_OBSERVED` for a
quiescent intent whose previously absent marker appears in the supplied snapshot.
`validate_write_journal` retains a resolution snapshot digest and accepted subset,
but no capture/resolution chronology. `parse_remote_activity_snapshot` validates
activity dates, not when the response was captured. `evaluation_started_at_utc`
dates the local analysis, not the remote capture.

A perfectly valid input can be an older snapshot containing an activity removed
before the saved quiescence resolution. The proposed code would then label an
earlier observation as post-quiescence. Historical marker reuse by a later request
is another possible explanation, already correctly acknowledged by the plan;
neither explanation can be selected from these inputs. An activity's operation
timestamp cannot repair the missing capture chronology.

Required change: use an explicitly chronology-neutral observation, for example
`MARKER_PRESENT_OUTSIDE_RECORDED_ACCEPTED_SUBSET`. Define its exact predicate as
`recorded state == quiescent`, marker absent from that intent's accepted map, and
at least one current supplied-capture row carrying the marker. Preserve duplicate,
context, financial and ID conflict codes independently. State that the capture can
precede or follow the resolution and that the observation attributes no creation,
arrival, cancellation failure or delivery to an individual request. Do not add a
new capture-authentication mechanism for this limited command.

Required tests: an older presence capture paired with a later absent quiescent
resolution; a later reused marker in a distinct intent; duplicate/conflicting rows
for the previously absent marker. All remain per-digest observations with unchanged
journal bytes, false readiness and no chronology/causality claim. Confirmed journal
plus empty post-compensation capture must remain recorded-confirmed/currently-absent
without asserting stale evidence or failed acceptance.

Follow-up disposition: Gate2 now uses
`PRESENT_MARKER_NOT_IN_RECORDED_ACCEPTED_SET`, expressly permits the saved capture
to predate resolution, and forbids freshness, authenticated capture-time and
post-resolution arrival claims. Gate4 requires stale-capture coverage. This closes
the design blocker; the behavior still needs implementation evidence.

## R2 — Enforce resource budgets before expanding evidence

Severity: medium. **Addressed in the amended plan.**

Evidence: Gate1 lines 41–44 caps expected marker references at 10,000 and checks
encoded output against max-bytes. Gate2 requires every duplicate candidate to be
retained per intent, and expressly allows historical marker reuse. The existing
`canonical_decimal` uses `format(value, "f")`; the remote normalizer accepts finite
Decimal scientific values without an exponent/expanded-length budget. Checking
output length only after constructing/serializing it does not constrain the work
or memory needed to reach that check.

Two distinct expansions need a guard:

1. A comment index avoids scanning unrelated rows but does not bound the sum of
   per-intent candidate references. Repeated historical occurrences of one marker,
   each matching many duplicate remote rows, can expand into many more than 10,000
   output references while satisfying the expected-marker cap.
2. A short remote numeric token such as `1e100000000` is finite and compact in the
   input but requires approximately 100 million characters in fixed decimal form.
   Fingerprinting or evidence rendering can expand it before an output-size check.

Required change: retain the expected-marker cap and separately cap the total
materialized candidate/evidence references, including independent journal-ID
evidence. Check the cap before adding each batch/reference, or use a clearly
bounded shared representation. Reject without truncating or choosing candidates.
Preflight selected numeric values using Decimal metadata before any plain-decimal
formatting/fingerprinting; reject values whose expanded representation exceeds a
documented bound tied to the explicit budget. This can be local to verification;
a repository-wide numeric rewrite is unnecessary. Retain the final encoded-byte
check as a separate publication guard.

Required tests: exact-boundary and one-over expected references; exact-boundary
and one-over expanded candidate references using historical reuse and duplicate
remote markers; compact large positive and negative exponents rejected before
fixed-point expansion; ordinary exact scientific values preserved. Verify fixed
error codes, no output replacement, no input/journal change and no network.

Follow-up disposition: Gate1 now separately caps expected and materialized
candidate references at 10,000, counting reused markers and duplicate candidates
before materialization. It also bounds every normalized remote Decimal's
prospective fixed-point representation to `min(4096, max_bytes)` using metadata
before formatting/fingerprinting, including unrelated rows. Gate4 adds the
corresponding discriminating tests. This closes the design blocker. Count the
independent journal-ID evidence within the same materialization budget.

## Accepted boundaries and implementation checks

- The proposed command is observational. It must not invoke resolution or write
  transitions, even pure transition helpers, as an implementation shortcut.
  Test traps should cover `resolve_write_intent`, `write_intent_transition` and
  `persist_write_transition`, in addition to all transport paths.
- Full-snapshot validation before selection and comment indexing across all
  accounts/types/contexts are correct. Unique positive readback requires the
  complete existing sent fingerprint and all three context predicates. Duplicate
  markers never become positive merely because one duplicate is exact.
- The independent remote-ID index is necessary. A stored accepted ID with a
  missing/changed marker remains observable when the expected marker has zero
  matches. A same-marker replacement ID cannot satisfy stored-ID evidence.
  The exact count and `all_expected_exactly_present` must exclude journal-ID
  conflicts; financial equality may be reported separately if useful.
- Remote `operation_date` is a UTC-derived day under the current normalizer,
  not independently proven broker source-day evidence. Name/document that field
  accordingly and preserve the original timestamp alongside the sent source day.
- No empty readback, preserved recorded state, marker reuse, or positive local
  comparison grants replay, remote quiescence, source completeness or readiness.
  An empty valid journal produces no delivery assertion.
- Captured-byte provenance, explicit field allowlists, omission of free-text
  comments/completion reviewer/reference, safe count/code-only stdout, and private
  atomic publication are appropriate. Check each captured input against output
  path and existing inode aliases before publication. The local lock coordinates
  publication; it does not turn separately captured inputs into a live transaction.
- Retained synthetic lab captures can verify the finished CLI offline. Their
  count6/count0 behavior cannot replace the discriminating synthetic conflict,
  chronology, budget, preservation and transport-prohibition tests above.

## Gate closure and knowledge verdict

The follow-up design gate is satisfied. No unresolved design blocker remains.
Implementation, required full offline tests and the retained synthetic saved-data
CLI checks remain necessary; this report does not attest they have run or passed.
The approval grants no dispatcher, cancellation input, fence mutation, production
access, replay permission or PR/merge approval.

Knowledge verdict: **Used and sufficient**. Narrow indexed lookup reached the
current `saved-input-report-preservation` and `saved-snapshot-compatibility`
concepts, which corroborate the owning repository contracts and were checked
against current helpers. No retrieval escalation or new portable operational
incident was established. These design findings belong to this plan/review.

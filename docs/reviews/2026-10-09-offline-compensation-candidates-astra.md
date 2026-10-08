# Offline compensation candidates — Astra design review

Date: 2026-10-09. Design owner: `infra-4g8u.47`.
Verdict: **APPROVE** for the bounded offline implementation described below.
This is an independent design gate, not a PR review. External CodeRabbit review
and Florent's merge workflow remain unchanged.

Reviewed [plan](../plans/2026-10-09-offline-compensation-candidates.md) SHA256:
`7415dcd19583c206801fd6d1c91d129326179a3f2ac5b52e8922edc0f725d9a2`.
Code baseline: `304e9086cc7072988be4314172b8fab4b9cd454d`.
The plan was untracked at review time. Approval applies to that proposal and the
implementation gates in this report; it does not attest to unimplemented behavior.

## Scope and evidence

Read project guidance, security/Python conventions, FINDINGS, original plan
sections 9–11, the write-intent and offline-verification contracts, and the prior
verification design review. Inspected the actual wire builder/validator,
`validate_write_journal`, intent transition/resolution, and the complete
`verify_local_intents` calculation/publication path in the functional mono-file.
The narrow KB lookup reached the Ghostfolio index and the stable, currently
applicable saved-input-preservation concept; the proposed collision checks match
that known failure mode.

No network, Docker, production, private input, shared Beads, tests or implementation
changes were used. Only this review report was written. Retained count6/count0
captures are implementation validation prerequisites supplied by the plan, not
artifacts independently inspected here.

## Findings and disposition

### R1 — Association cannot prove creation

Severity: high if promoted to delete authority; **addressed by the design**.

`resolve_write_intent` (baseline line 1191) confirms unique matching rows from a
saved snapshot. It does not establish a pre-request absence baseline or prove
that the selected request created those rows. Original I9/section 10's exact
created-ID rollback promise therefore cannot be fulfilled by this journal alone.
Gate2 correctly restricts selection to the recorded accepted subset, while Gate3
keeps creation provenance unproved and deletion unauthorized. Reverse source-date
and wire-array order is valid only as deterministic presentation.

Implementation gate: retain those boundaries in CLI help, documentation and every
artifact. No field or prose may call candidates newly created, safely deletable,
freshly revalidated, or a complete restoration. This delivery must not close any
acceptance criterion requiring actual creation proof, operational rollback or
production recovery; it is the explicitly narrower offline component of I9.

### R2 — Readback codes and recorded identity must be interpreted together

Severity: medium if implemented incompletely; **addressed by the design**.

The existing verifier first adds `EXACT_POSITIVE_READBACK`, then can discover
`JOURNALED_REMOTE_ID_CONFLICT` and set `exactly_present` false without removing
the positive code. Testing only for the positive code would accept a replacement
ID. An absent marker can likewise coexist with the recorded ID under a different
comment; that is conflict, not harmless absence.

Implementation gate: require `exactly_present`, one observed candidate and exact
recorded accepted ID, with conflict checks taking precedence over absence. A
changed/missing marker on the retained ID must suppress the entire candidate
list. Test this separately from same-marker replacement-ID and mixed genuine
absence/presence. Preserve existing verify codes and semantics during extraction.

### R3 — Account uncertainty and retained-history contradictions

Severity: high if omitted; **addressed by the design**.

`write_intent_transition` fences the entire account whenever any intent is
uncertain. `validate_write_journal` validates accepted-ID uniqueness within each
intent, not across intent resolutions. A structurally valid retained journal can
therefore contain contradictory historical associations. Gate2 correctly adds
the account-wide uncertainty blocker and the cross-intent accepted-ID reuse
check before offering any candidates.

Implementation gate: inspect all intents even when the selected digest is
confirmed and unrelated intents have no visible snapshot rows. Either blocker
must suppress all candidates, including otherwise exact rows. Historical reuse
under another digest must be caught even when the marker is identical. Preserve
the journal validator's existing contract; report selection ambiguity locally
rather than silently rewriting or resolving history.

### R4 — Saved evidence has no authenticated chronology

Severity: medium if chronology is inferred; **addressed by the design**.

The journal retains a resolution snapshot hash but no authenticated capture or
settlement ordering. `verify_local_intents` records evaluation time only. A
quiescent intent's unaccepted marker might appear in an older capture or in a
later independently authorized intent. `UNACCEPTED_SELECTED_MARKER_PRESENT` is
appropriately neutral and blocks selection without attributing creation or
cancellation failure. Accepted absence similarly proves only absence in these
bytes, not successful deletion.

Implementation gate: exercise an older presence capture with a later quiescent
resolution and a reused marker in a different intent. Never use operation date,
file mtime, evaluation time or a completion-reference string as proof of freshness
or request completion. Selected uncertainty remains zero-candidate even with all
rows exactly visible.

### R5 — Shared calculation must preserve bounded, private observation

Severity: medium if weakened; **addressed by the design**.

The actual verifier preflights Decimal expansion for all normalized rows before
fingerprinting, caps both expected references and materialized references, and
retains independent recorded-ID evidence. Those protections belong inside the
shared pure observation boundary; a selected-intent shortcut must not bypass
them. Gate1 explicitly retains whole-input validation and both budgets.

Implementation gate: use captured journal/snapshot data, without rereading files,
publishing verify output, invoking resolution, or introducing global mutable
state. Preserve verify's existing result/error contract. Check final encoded
output size separately. Publish only selected-candidate allowlisted evidence;
historical conflict detection must not export unrelated bodies or remote rows.

The new output must reject config/journal/snapshot path and inode aliases before
publication, retain private modes/atomic persistence/target locking, and preserve
previous output on validation, budget and lock failures. Existing verification
reports and journal/binding bytes must survive unchanged. The shared helper
extraction does not authorize unrelated persistence or numerical refactoring.

## Required implementation evidence

The proposed Gate4 matrix is sufficient when it includes the discriminating
cases above. Run the full required offline pytest suite with socket access
forbidden; separately prohibit intent persistence and resolution in command
tests. Demonstrate safe stdout, exact private Decimal strings, deterministic
display order, strict configuration/digest selection, all alias classes, unchanged
verify behavior and zero-candidate reports for every selection blocker.

The retained synthetic count6/count0 check should produce three exact association
candidates then zero, with identical journal bytes and no new request. This is
local selection evidence only. Do not run another lab merely to obtain it, and
do not imply this design review verified those private artifacts.

Review the semantic diff and numstat, commit the intended implementation and
record exact test/CI evidence under the owning issue. Keep the PR open and its
review external. Actual DELETE design still requires separate creation/ownership
proof, fresh live revalidation, exclusive access, quiescence, explicit operator
authorization and wider profile/database/cache recovery evidence.

Knowledge verdict: **Used and sufficient**. The indexed preservation concept was
applicable and checked against the proposed publication contract. Other findings
are already explicit in canonical code/contracts; no new KB contribution is needed.

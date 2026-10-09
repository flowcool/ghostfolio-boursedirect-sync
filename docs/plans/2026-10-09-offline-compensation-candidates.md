# Offline compensation-candidate inspection

Date:2026-10-09. Design owner:`infra-4g8u.47`. Astra design review precedes code.
Florent authorizes continued implementation without PR-review waiting. Production
writes and actual deletion remain prohibited.

## Problem, authority and boundary

Original I9 proposes a rollback plan. The retained journal, however, records exact
submitted bodies and positive row association, not authenticated proof that this
import created each associated row. `resolve_write_intent` can confirm a matching
row already present. Therefore expose `rollback-plan` as **offline compensation
candidate inspection**, never as executable deletion or full database restoration.
No candidate is called newly created. No endpoint, token, network, DELETE request,
shell command, recovery authorization or journal-resolution option is accepted.

The complete retained-journal state machine, exact wire validation, whole-snapshot
normalizer, verification predicate and private publication contract are existing
authority. Reference:[write intents](../design/write-intents.md),
[verification](../design/offline-intent-verification.md), pinned3.81.0
[lab parity](../design/ghostfolio-381-parity.md). Retained synthetic lab count6/count0
captures allow validation without new Docker/network or production requests.
Unknown live origin, original request completion and database/profile/cache
restoration remain operational gates, not assumptions in this local command.

## Gate1 — captured inputs and shared observation

CLI:`rollback-plan --config FILE --input-root DIR --max-bytes N`.
Config exactly:`schema_version: 1`, `journal`, `snapshot`, `wire_sha256`.
The digest must be lowercase64hex and select one existing journal intent. Capture
each file once using existing bounded regular-file/root/no-symlink readers. Strict
keyed YAML and complete journal/body/binding validation apply. All intents and all
snapshot rows remain validated, including unrelated/redacted rows. Exact captured
config/journal/snapshot SHA256s bind provenance; no live/freshness claims.

Extract the existing verify observation calculation into a pure captured-input
helper reused by both commands. Preserve every existing verify result/predicate,
budget and error contract; `rollback-plan` must not call the publishing verify CLI
or overwrite its report. Existing10000 expected/materialized-candidate reference
budgets and4096-or-smaller fixed-point Decimal shape limit remain in force before
formatting, plus explicit input/output bytes. No extra raw financial-body export.

## Gate2 — candidate semantics and conflicts

Select only markers in the selected settled intent's resolution.accepted map.
An `uncertain` selected intent proposes zero candidates, even if matching rows
are visible. Any uncertain intent elsewhere in this account journal is an
account-level blocker and suppresses all candidates: no compensation during an
unsettled request. Report codes, never clear a fence or infer quiescence.

For each selected accepted marker require the existing exact/context-valid unique
readback predicate **and** the journal's exact accepted remote ID. Missing rows
are recorded absent, not proposed and not proof deletion occurred. Duplicates,
replacement IDs, changed/missing marker, wrong account, changed financial values,
inactive/draft or date/financial context defects are blocking observations.
Inspect all historical accepted associations: if a proposed remote ID is accepted
under another marker/digest, report `REMOTE_ID_SHARED_BY_RETAINED_INTENTS` and
suppress all candidates. This catches structurally valid contradictory journal
history rather than guessing which request created it.

For a quiescent selected intent, markers outside its accepted map may legitimately
belong to a later authorized request. If visible in this capture, record
`UNACCEPTED_SELECTED_MARKER_PRESENT` and block the proposal; do not infer chronology
or steal another intent's association. If absent, report as unaccepted, never as
compensatable. A recorded completion reference is data validated by the journal
contract, not new authenticated operational proof.

No partial executable plan: any such blocking ambiguity suppresses the complete
candidate list. Otherwise retain only exactly observed accepted associations;
absent accepted rows yield an explicit missing list alongside any present
candidates. Candidate order is descending source date then descending original
wire-array ordinal as a deterministic **proposal display order**. It does not
claim actual server insertion or POST order, atomic rollback, holdings validity
after deletion, or asset-profile/database restoration.

## Gate3 — report, privacy and preservation

Publish `outputs/rollback-plan-<account-key>.yaml`, schema1, artifact_kind
`offline_compensation_candidates_not_authorization`, engine contract, binding,
selected digest/state, captured input hashes, evaluation time, selection codes,
accepted-absent/unaccepted marker lists and ordered candidate entries. Candidate
entries contain only marker, recorded remote ID, wire ordinal, exact private
financial fingerprint and allowlisted observed evidence already retained by verify.
Exclude raw body/comments, completion reviewer/reference, auth/runtime URLs and
all executable delete instructions. Never serialize unrelated snapshot rows.

Always `deletion_authorized: false`, `import_ready: false`; fixed boundaries
`CREATION_PROVENANCE_NOT_ESTABLISHED`, `FRESH_REMOTE_REVALIDATION_REQUIRED`,
`EXPLICIT_DELETE_AUTHORIZATION_REQUIRED`, `PROFILE_AND_DATABASE_RECOVERY_UNPROVEN`,
`PRODUCTION_WRITES_NOT_AUTHORIZED` remain even for exact synthetic candidates.
`candidate_selection_unambiguous` describes association only. Stdout only counts,
fixed codes/readiness; no ID/marker/value/digest. Readable proposal exits2, invalid
input/publication exits1. Uncertainty/conflicts produce a readable zero-candidate
report, not a mutation or silently successful rollback.

Check output resolved-path/existing-inode collision against config/journal/snapshot
before any publication. Reuse private atomic bytes/fsync/rename and per-target
preparation lock, files0600/directories0700. No journal/binding/verification report
is rewritten. Previous output survives invalid input, budget or lock failure.
The command can create only its local output/lock, not remote state.

## Gate4 — discriminating validation and delivery

Socket/persist/resolver-forbidden tests cover settled full/partial/empty captures,
selected/other uncertain intents, no accepted quiescent markers, quiescent unaccepted
presence, cross-intent accepted-ID reuse, same-marker replacement ID, changed
marker/value/account/context, duplicates, mixed absent/present accepted rows,
exact Decimal and reverse display ordering without creation/chronology claims.
Verify regression tests must remain unchanged in semantics after extraction.
Test strict schema/digest selection/whole-snapshot validation, provenance after
external input change, separate report preservation, all input/hard-link aliases,
lock/byte/Decimal/reference budgets, private permissions and safe stdout.

Run required full pytest. On retained synthetic owned lab journal/count6/count0,
expect3 exact association candidates before compensation and0 after, unchanged
confirmed journal bytes and no new request. This establishes only local selection
behavior, not actual delete authorization or production recovery.
Review semantic diff/numstat, commit atomically, audit reachable Git history, publish
open stacked PR, leave review/merge external. Root end-to-end acceptance stays gated.

Blast radius: versioned command/tests/docs and one private local report/lock.
Rollback: revert scoped implementation commit; retain inputs/journals/observations.
No broker or Ghostfolio state changes. A later actual delete design must separately
prove creation/ownership, fresh live revalidation, exclusive target access,
quiescence, explicit operator authorization and verified wider recovery effects.

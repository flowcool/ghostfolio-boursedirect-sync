# Offline compensation association candidates

`rollback-plan` inspects one retained intent against a saved complete activity
snapshot. It proposes recorded-ID associations for review only. A journal can
associate a pre-existing matching row; it does **not** prove creation. The command
never sends DELETE or any request, grants deletion authority, changes a journal,
resolves uncertainty or asserts freshness/full database restoration.
Authority:[approved plan](../plans/2026-10-09-offline-compensation-candidates.md),
[Astra design review](../reviews/2026-10-09-offline-compensation-candidates-astra.md).

```yaml
schema_version: 1
journal: retained-journal.yaml
snapshot: captured-activities.json
wire_sha256: <exact retained lowercase64hex digest>
```

```sh
.venv/bin/python boursedirect_to_ghostfolio.py rollback-plan \
  --config inputs/compensation.yaml --input-root inputs --max-bytes 1048576
```

References are relative to input-root; config and inputs are captured once as
bounded regular local bytes. Strict schema/key/digest validation, complete journal
validation and whole-snapshot validation precede selection. The pure bounded
observation helper is shared with [verify](offline-intent-verification.md); this
command does not invoke or replace verify's published report.

## Selection meaning

Only markers in the selected settled intent's recorded accepted subset can be
candidates. They require a unique exact/context-valid observed row and the exact
recorded remote ID. The complete financial fingerprint uses exact Decimal values.
An absent accepted row is reported absent, not deletion success. Missing/changed
marker on a recorded ID, replacement ID, duplicates, financial/account/context
conflicts suppress the complete candidate list. So does uncertainty in **any**
account-journal intent. Shared accepted remote IDs across retained intents also
suppress otherwise exact candidates, even for historical identical markers.

For quiescent intents, visible markers outside the recorded accepted subset yield
`UNACCEPTED_SELECTED_MARKER_PRESENT` and zero candidates. They may come from an
older capture or later independent request; no chronology or ownership transfer
is inferred. Unaccepted/absent rows are never proposed for compensation.

Absent accepted rows alone permit a report listing the remaining exact candidates
and an explicit absent list. This is a partial observational proposal, not an
executable deletion plan. Descending source date then descending original wire
ordinal defines deterministic display order, not actual POST/insertion order or
holdings validity after deletion.

## Report and persistence

Private `outputs/rollback-plan-<account-key>.yaml` contains selected digest/state,
binding, captured input hashes, evaluation time, fixed selection codes,
accepted-absent/unaccepted lists and ordered candidate entries. Each entry includes
its marker, recorded remote ID, wire ordinal, financial fingerprint and allowlisted
observed evidence. Raw body, unrelated rows/comments and completion reviewer or
reference are excluded. Stdout exposes counts/codes only. Readable reports exit2;
invalid input/publication exits1.

Every report preserves `deletion_authorized: false`, `import_ready: false` and
boundaries for unestablished creation provenance, required fresh revalidation,
explicit deletion authorization, unproven profile/database recovery and prohibited
production writes. `candidate_selection_unambiguous` concerns association only.

Existing expected/candidate reference caps10000 and preformat Decimal shape cap4096
characters or the smaller byte budget apply to all captured observation data.
Output has its own explicit byte limit. Output path/inode aliases against each
input are rejected before publication. Private atomic fsync/rename under the
target preparation lock preserves previous output on failure; directories0700 and
files0600. Original journals, bindings and verification reports remain unchanged.

## Validation and limits

Socket/persist/resolver-forbidden tests discriminate exact versus replacement IDs,
changed markers, financial/context conflicts, duplicate rows, partial/empty capture,
selected/other uncertainty, historical reused markers/shared IDs, display ordering,
safe stdout, provenance, strict config and private collision/lock/budget handling.
Existing verify tests cover the shared pure observation behavior unchanged.

On2026-10-09 the retained synthetic owned lab's count6/count0 captures yielded3/0
association candidates with byte-identical confirmed journal and no new request.
This is local selection evidence, not live deletion or production recovery proof.
Exact validation is recorded under `infra-4g8u.48`.

This component does not fulfill original I9's actual-created-ID rollback promise.
A future operational deletion design must establish creation/ownership, fresh live
revalidation, exclusive access, quiescence, explicit authorization and wider
asset-profile/cache/database recovery. Reverting this scoped commit restores code;
retain private evidence. No broker or Ghostfolio rollback is needed here.

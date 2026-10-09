# Qualified operator application — independent Astra design review

Date: 2026-10-09. Final decision: **APPROVE C1 and C2** at the final amended
plan pin below. Initial decision: REVISE (two bounded design corrections,
now resolved).
This is a design review, not implementation, PR review, security approval,
source acceptance, or authorization to execute against production.

Reviewed plan: `docs/plans/2026-10-09-qualified-application.md`.
Exact plan SHA256: `eebf4fee5fa462871a8d87216fcb63eea4d491667c6f03ddfa3006d6b95fa83c`.
Full implementation baseline: `04f492526aaefa2cc98ffe642fe0d4fd9b9fb0ca`.
The plan was an untracked draft; no application implementation changes were
present in the reviewed working tree. No tests, service requests, private-input
reads, Beads mutations, or Git mutations were performed by this reviewer.

## Scope and method

Read the project instructions, preparation and operator plans, relevant findings,
source conversion/preparation, frozen-review computation/validation, canonical
wire and acceptance rules, intent transitions, continuous-lock single-event core,
frozen sequence, public preview, fixed HTTPS adapter, and owned runner lifecycle.
Inspected the discriminating preparation, frozen-review, sequence, preview,
transport and core test coverage and the corresponding design contracts.
The assessment concerns the proposed composition and its claims, not fresh
runtime validation of the baseline.

Narrow KB lookup: operations → Ghostfolio → local input preservation.
The indexed preservation concept is applicable and consistent with current code:
hashing captured bytes does not protect the corresponding files from later
publication or permission changes. Existing API knowledge is supporting context;
the pinned repository contracts control this review. No production behavior was
inferred from the older KB version observations.

## Blocking design findings

### R1 — P1: historical configuration/evidence immutability is not established

Evidence: `convert_matched_trades` checks that `currency_evidence` and
`target_security_evidence` are nonempty, but omits both from its output.
`prepare_local_plan` retains raw statement/note hashes, not the preparation-config
hash or complete mapping record. The proposed C1 computes that same artifact and
compares it in full. Gate1 nevertheless requires rejection of changed
mapping/context evidence and discusses raw config changes failing even when
semantic display matches.

Changing only either nonempty evidence reference, an unused mapping, or a
configuration path referring to identical bytes produces the same prepared
artifact. A declaration can pin the newly supplied config, but that pin cannot
prove it was the config used for historical preparation. This is a mismatch
between the advertised evidence boundary and the unchanged artifact schema.
It does not invalidate full raw-document replay or exact DTO comparison.

Required decision: explicitly choose one of these bounded contracts before C1:

- Preserve the existing schema and describe replay as qualification of the
  currently supplied configuration under the exact externally pinned declaration.
  Do not promise detection of a historical config/evidence-only change when its
  original bytes were never bound. Current evidence must remain nonempty and the
  declared config pin must reject any change relative to that declaration.
- If historical immutability is required, add an explicit preparation provenance
  digest/schema migration, regenerate and review affected preparations, and bind
  the original config/evidence bytes through the frozen chain. Do not silently
  treat an old artifact as possessing a missing historical digest.

The first option is sufficient for the stated unsigned, operator-responsible
run model and avoids unnecessary migration. It must be reflected consistently
in the plan, tests and operator documentation.

Required discriminating evidence: changing only a mapping-evidence reference
while keeping prepared bytes unchanged; a stale declaration pin must reject it
before callbacks/state. A fresh externally supplied declaration pin must behave
according to the explicitly chosen contract, with no historical-authenticity
claim. Financial symbol/currency/quantity/fee/source-byte changes must continue
to fail full replay against the original preparation.

### R2 — P1: public run evidence does not preserve qualification for cold replay

Evidence: Gate3 archives exact single-row wire, previous/new readback hashes and
new raw readback after each durable confirmation. It does not specify preservation
of the execution declaration and its external pin, full frozen input bundle,
prepare config/raw sources, or initial raw baseline before dispatch. The baseline
owned runner separately preserves a complete frozen-review bundle before its
first source POST; this capability does not automatically transfer to the public
controller. Gate4 requires source/frozen archive cold replay for the runner only.

After a first confirmed write and a second timeout, journals retain valuable
intent/tombstone evidence. However, changing the original local declaration or
source/config files can make the actual run qualification irreproducible. A hash
of the original baseline cannot reconstruct its bytes. An application archive
must retain the evidence that authorized its own exact attempt, not depend on
mutable input locations remaining unchanged indefinitely.

Required design correction: for a nonempty public run, create its newly owned
UUID archive only after pure preflight, then durably retain a private manifest
and the complete exact captured bundle before the first request callback or
write intent. Include declaration plus external pin, review plus external pin,
review config and four capture roles, prepare config plus pin, ordered raw
statement/note captures, and the original baseline (already one of those roles).
Use keyed roles/aliases, not arbitrary input paths as archive destinations.
Associate the run and its per-event wire/readback chain with that manifest.
All files remain private and ignored; no credentials are retained.

Validate archive/state destinations and captured path/inode collisions before
mkdir/chmod. Archive initialization failure must send no requests. An observer
failure after a durable confirmation must still retain its tombstone, stop the
sequence, and never retry/compensate. Null wire creates no archive/state and does
not require credentials. Retaining hashes does not authenticate the declarations.

Required discriminating evidence: complete offline source/frozen/declaration
replay from retained public-run bytes after original input files are changed;
first-confirmed/second-timeout preserves the initial bundle and first event's
archive; initialization persistence failure yields zero callbacks; later
observer failure yields one confirmed tombstone and no next POST. Include the
existing alias/permission-preservation matrix for archive initialization.

## Accepted design boundaries and implementation obligations

The proposed source replay is necessary: current frozen validation proves
consistency with preparation bytes, not derivation from current raw HTML.
C1 should remain pure and preserve financial refusal behavior, source raw hashes,
stable IDs, ordered note multiplicity, and preparation revision/binding guards.
It must not write ledgers or resolve a revision conflict while validating apply.

The strict externally pinned declaration is an acceptable record of explicit
operator responsibility. It authenticates neither reviewer identity nor the
truth/freshness of version, timezone, security, recovery, source/history or
exclusive-access statements. Basic API compatibility and exact financial
readback remain distinct from real history/fee acceptance. Actual source owner25,
root G6/G7 and external pre-merge security review remain open until real evidence.
No synthetic confirmation for actual private data or production run is authorized.

Keep the trusted owned-lab callback wrapper separate from the qualified public
controller. The latter must independently perform complete source/frozen/
declaration/financial/binding preflight before any injected request callback or
state mutation. Prebuild all independent chronological single-row bodies. Capture
immutable bytes and copy mutable bindings before callbacks can change caller maps.
A trusted injected callback is not proof of transport-origin identity; only the
public route constructs the fixed environment-bound HTTPS adapter.

The public no-op branch must occur before adapter construction/credential lookup,
state or archive setup and observers. It reports a saved diagnostic, not a fresh
remote observation or fence clearance. Keep all dry-run truth-table cases from
package A; parse/inspect execution-only inputs only in the effective execution
branch. State explicitly whether execute-plus-export rejection refers to that
branch so DRY_RUN overrides cannot accidentally inspect execution declarations.

Preserve the existing conservative delivery core: both per-event locks,
fences/tombstones before GET, exact baseline comparison, durable uncertainty
before POST, one POST without retry, complete returned-row acceptance, and full
readback transition before confirmation. A confirmed prefix survives later
transport or persistence failure. No-op and HTTP status alone cannot report
successful remote execution. Local locking remains no cross-host exclusivity
or transaction guarantee.

Input preservation must cover every captured role, all four writable lock/journal
paths, state ancestors, archive ancestors/root and permission changes. Reusing
`private_directory` without ancestor checks would not implement the plan.
No malicious concurrent local filesystem actor is assumed by these checks;
avoid claiming atomic filesystem snapshot or race-proof sandbox guarantees.

The owned 3.81.0 runner should invoke the qualified controller with explicitly
synthetic evidence tied to newly owned resources and its original fixture bytes.
Its local HTTP callback does not constitute a live HTTPS-adapter acceptance test.
Require exact three POSTs/three confirmations/count six, repeat zero, six owned
compensations/count zero, resource absence, retained uncertainty where injected,
and cold replay. Ordinary pytest remains socket-forbidden.

## Disposition

Amend R1's exact evidence claim and R2's public archive contract, then re-pin the
plan for a short design recheck. The remainder of C1/C2 is suitable for implementation
under the existing no-production-write boundary. Implementation still requires
its complete test/isolated-lab evidence and external reviews; this report grants
none of those results in advance.

Knowledge verdict: **Used and sufficient**. Narrow indexed lookup reached the
applicable input-preservation lesson; the remaining conclusions are local design
findings retained in this canonical report. No new KB concept is needed.

## First amendment recheck

Amended plan SHA256:
`fac0d24cf7bfaa598d723c185485a720a919b60bb5e1d1fe5300ab484765cfa4`.
Implementation baseline remains unchanged.

**R1 resolved.** Gate1 now explicitly qualifies the current declaration-pinned
configuration, describes absent historical config/evidence provenance, and
requires stale declaration pins to reject changed config bytes. This satisfies
the recommended schema-preserving option above. **C1 is approved for
implementation against this amended contract.**

**R2 remains open for C2.** The amended Gate3 still specifies only the
post-confirmation per-event archive. C2 remains REVISE until complete run
qualification capture before dispatch and corresponding cold-replay/failure
checks are specified. No new concern was introduced by the R1 amendment.

## Final amendment recheck — approved

Final approved plan SHA256:
`ce47d3e56613b65472426fe4aae105c2938e8c3a1c0d6974eb0f90a2d58f3706`.
Full implementation baseline:
`04f492526aaefa2cc98ffe642fe0d4fd9b9fb0ca`.

**APPROVE C1 and C2 for implementation. R1 and R2 are resolved.**
This final recheck supersedes the earlier REVISE disposition for this exact
amended plan only; the earlier findings remain as the decision record.

R1's current-config qualification boundary is retained. Gate3 now requires
private ownership/role-hash manifest and every exact captured qualification input
to be durably retained before any callback or intent. It explicitly excludes
credentials, uses generated filenames, retains partial failed archives, and
requires cold replay after originals change. Gate4 adds zero-callback archive
initialization failure and first-confirmed/second-timeout retention tests.
Per-event evidence belongs to that initialized run archive and manifest; the
post-confirmation observer remains subordinate to durable core confirmation.
These requirements resolve R2 without granting evidence an authorization role.

Gate2 now limits execute-plus-export rejection to the effective execution branch
(`DRY_RUN=0` plus `--execute`), preserving package A behavior under dry-run
override. No additional design blocker was found in this bounded amendment.

This approval authorizes neither production execution nor fabricated actual-data
confirmations. External security/PR review and the actual financial/source/history
acceptance gates remain separate. No implementation was reviewed or tested here.
The parent session owns implementation, verification, issue reconciliation and
committing this report. Knowledge verdict remains **Used and sufficient**.

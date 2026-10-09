# Trusted owned-lab frozen sequence orchestration

Date:2026-10-09. Design owner:`infra-4g8u.57`. Baseline:`3715ff22873b`.
This closes the manual sequencing gap between the frozen validator and the tested
single-event core. No production transport, credential flow or apply CLI. Runtime
callbacks are trusted owned-lab adapters only. The caller owns resource identity,
fixture authenticity and operational exclusivity; hashes supply no such authority.
Read the whole frozen computation, wire ordering, intent/journal and single-event
core plus disposable runner and tests before coding. Existing numeric/financial
policy and persistence protocol remain unchanged.

## Gate1 — complete preflight before callbacks or state

Add callable `dispatch_frozen_lab_review(state_root, binding, review_raw,
review_sha256, config_raw, captures, max_bytes, request, observe_confirmation)`.
Validate the frozen report first through the existing helper; validate exact journal
binding and equality to report/prepared account_key/target_account_id. Reject any
holdings shortage or nonempty unresolved adoption before dispatch. Existing
production/destination/security blockers remain present and readiness false: this
trusted owned fixture path does not claim to satisfy production approval.
Parse preparation from the same captured bytes, derive only recomputed new
markers and prebuild all canonical one-row wires in the validated batch's existing
chronological order. Reject inconsistency against the full recomputed batch and
size/shape errors before any request, lock/persistence or observation callback.
Never dispatch from an earlier object or reread inputs. Capture baseline bytes
from that same validated snapshot before any callback can mutate the caller map.
Source declarations/current-time limits remain the frozen helper's contract.

All-existing/null wire is a no-request/no-state/no-observer result with
accepted_events0 and captured readback, readiness false. Do not describe that
captured readback as fresh remote evidence or the no-op as uncertainty resolution.
A holdings-shortfall report is computationally valid but rejected by orchestration.

## Gate2 — exact sequential durability and failure

For each prebuilt wire call `dispatch_single_lab_intent` with the preceding
positively confirmed raw readback as baseline. Its binding locks, initial GET,
durable uncertain fence, single POST, complete acceptance and final exact GET
remain authoritative. Do not duplicate or relax the state machine. Locks are
held per event; there is no whole-sequence transaction or distributed exclusion.
A foreign/local writer between events makes the next baseline GET fail closed.
Keep settled tombstones and account-level uncertainty fences; never retry POST.
A new invocation of the same frozen proposal is not a resume mechanism: existing
tombstones reject it, and uncertain state blocks the account. Continuation requires
a newly reviewed current capture; absent evidence never clears uncertainty.

Only after the core returns confirmed evidence invoke trusted
`observe_confirmation(ordinal, wire, baseline_raw, readback_raw)` once. This
callback allows the owned controller to archive one-row provenance/readback and
milestones before a later failure, preserving the existing runner's evidence.
Callbacks are not financial authority and may not change prepared inputs or
future wires. Build all wires independently before callbacks; avoid returning
shared mutable orchestration objects to callbacks. An observer exception stops
immediately with a fixed privacy-safe code, retaining the already confirmed
journal/tombstone; no next event or automatic compensation occurs in the helper.
Transport/persistence/core failures propagate existing fixed codes and stop the
loop immediately. No batch POST, retry, resolution override or deletion is added.
Return accepted_events count, final confirmed readback and false readiness only.

## Gate3 — integrate the existing owned controller

Replace the runner's manual dispatch loop with this callable; retain its bounded
owned HTTP adapter, seed/source separation, per-POST uncertainty assertion,
private initial full proposal, per-event exact wire/response/provenance/readback,
three confirmed journals, refreshed snapshot/history repeat and finally owned
compensation/resource cleanup. The request adapter may archive a response for an
attempt but cannot call that evidence confirmed. Confirmation observer owns
successful per-event archives; journals still retain partial/failure evidence.
The frozen capture archive and external fixture pin stay unchanged. Fixture
controller ownership/auth/cleanup are not moved into application code.

## Gate4 — failure and owned evidence

Socket-forbidden synthetic tests cover all three chronological one-row calls and
exact baseline chaining; report tamper/binding conflict/shortfalls/future source
refused before request/state/observer; zero-new no-op; first/second core failure;
observer failure after confirmation; inter-event baseline change; uncertain rerun
and confirmed tombstone refusing another POST. Adversarial trusted observers must
not alter a later prebuilt body or bound baseline. Existing runner first-intent and
second-POST-timeout cases retain completed event0 archives and durable uncertainty;
add observer failure proving confirmed journal plus no later source POST and
finally cleanup. Reuse existing single-event protocol tests without duplication.
Run full pytest, diff/numstat/privacy checks, then explicitly rehearse the owned
pinned3.81.0 lifecycle:3sourcePOST/3confirmed/count6/zero-new repeat/compensation6/
count0/resourcesabsent. Cold frozen replay remains valid after teardown.

Commit scoped implementation, push authorized parent then child sequentially,
open stacked PR and leave external review/merge untouched. Blast radius callable
lab orchestration/runner/tests/docs and newly owned resources. Code rollback by
commit revert; retain captures/journals. Helper never compensates remote effects.
Actual history/adoption and production authorization/recovery remain separate gates.
Astra must approve the exact plan before implementation.

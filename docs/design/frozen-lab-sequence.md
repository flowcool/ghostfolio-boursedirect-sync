# Frozen owned-lab sequence

`dispatch_frozen_lab_review(state_root, binding, review_raw, review_sha256,
config_raw, captures, max_bytes, request, observe_confirmation)` is a callable
trusted owned-lab adapter only. No apply CLI, endpoint, credentials or production
permission is added. The fixture controller remains responsible for ownership,
source authenticity, access and cleanup. Readiness stays false.

Full frozen validation, exact account binding and shortage/adoption rejection
precede state or callbacks. Preparation and initial baseline come from the same
captured bytes. All independent one-row canonical bodies are built and compared
with the chronological validated batch before the first core call. The binding is
copied locally; later caller-map mutation cannot replace captured bodies/baseline.
Null wire returns accepted_events0 and captured readback without requests/state;
that captured evidence is not a fresh remote listing or an uncertainty resolution.

Each body goes through the existing single-event core, using the prior confirmed
raw readback as baseline. Its per-event locks, initial GET, durable uncertain
journal, exactly one POST and complete acceptance/final GET remain authoritative.
The sequence is not a transaction and cannot exclude external writers. Inter-event
semantic drift rejects the next baseline before another POST. Same-proposal reruns
are not automatic resume: confirmed tombstones or uncertainty reject replay.

After durable core confirmation, the trusted observer receives ordinal, a fresh
wire-dictionary copy and immutable before/after bytes. This preserves per-event
archives even when a later event fails. Observer exceptions become the fixed
`LAB_SEQUENCE_OBSERVER_FAILED` code without private exception chaining, stop the
loop and retain the confirmed tombstone. Transport/core/persistence failures stop
immediately under their existing codes. The helper never retries or compensates.
Trusted callbacks are not external security principals or financial authority.

The owned runner uses the orchestrator, retains exact attempt wire/response and
confirmed provenance/readback archives, then runs its existing zero-new review and
bounded finally cleanup. Attempt archives alone do not prove confirmation.
See the [approved plan](../plans/2026-10-09-frozen-lab-sequence.md). Rollback is a
scoped code revert retaining evidence/journals, not remote compensation.

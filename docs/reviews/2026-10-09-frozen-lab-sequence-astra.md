# Frozen lab sequence — Astra design gate

Date: 2026-10-09. Verdict: **APPROVE** for the scoped trusted owned-lab
orchestration design. No blocking design finding remains.

- Plan: `docs/plans/2026-10-09-frozen-lab-sequence.md`.
- Exact plan SHA256: `bd4fffc9e1ad89d7c4bb889620a1a8e6ca29aca9558d3bca808b772d341901b0`.
- Full committed baseline: `3715ff22873b0be8934c37d249866aa61c63a479`.
- Design owner: `infra-4g8u.57`.

This is a pre-implementation design review, not a PR review, implementation
acceptance, human approval of financial inputs, or production write permission.
Approval applies to the exact plan above against the recorded baseline. The
implementation and owned runtime evidence required by Gate4 remain outstanding.

## Evidence reviewed

The review followed the committed computation and persistence chain in
`boursedirect_to_ghostfolio.py`: restricted YAML and private atomic publication;
prepared-artifact validation; complete remote normalization and adoption;
chronological holdings; exact numeric wire construction and canonical wire
validation; import-response comparison; journal validation, account fences,
tombstones and resolution; target/account locking; bounded semantic snapshots;
the complete single-event dispatch state machine; and frozen report recomputation
and validation. The entire `scripts/disposable_acceptance.py` was inspected,
including owned resource creation, transport, lifecycle, compensation and teardown.

Supporting contracts reviewed: frozen validation, offline preparation/adoption,
wire, write intents, single-event dispatch and disposable acceptance. Relevant
tests were read in `test_frozen_review.py`, `test_lab_dispatch.py`,
`test_write_intents.py` and `test_disposable_acceptance.py`. Project guidance,
the original import plan and the global plan-quality rule informed the scope.
No private captures, credentials, runtime evidence or Beads state were accessed;
no tests, network operations or lab resources were executed in this design review.

## Design assessment

1. **Preflight and authority — approved.** Gate1 uses the complete recomputed
   report, binds account namespace and target, rejects shortages and unresolved
   adoption, and derives every single-row payload from the same captured
   preparation. Comparing the reconstructed sequence with the validated canonical
   batch preserves chronological day/marker ordering. This closes the manual
   sequencing gap without making hashes evidence of source authenticity or write
   authorization. All-existing input returns only captured evidence and does not
   inspect or resolve retained uncertainty.

2. **Durability and failure — approved.** Gate2 delegates each event to the
   existing core, whose locks cover initial GET through durable confirmation.
   Its account fence and retained digest/marker checks run before transport; its
   exact transition check includes every prior semantic row and the independently
   accepted new ID. Passing the preceding confirmed raw readback into the next
   event detects intervening semantic drift at that event's initial GET. Per-event
   locks do not establish a sequence transaction or cross-host exclusion; the
   plan correctly leaves operational exclusivity with the owned controller.
   Neither a transport failure nor a persistence failure authorizes a retry.

3. **Observer and evidence preservation — approved.** Calling the observer only
   after core success keeps confirmation authority in the durable journal. An
   observer failure therefore means a confirmed event with incomplete auxiliary
   archives, followed by immediate stop; it must never be rewritten as uncertain
   or retried. The private frozen bundle and per-event archives preserve evidence
   across later failure and teardown. The existing runner remains responsible
   for bounded transport, fixture provenance, owned compensation and cleanup.

## Implementation verification points

These make the existing plan gates concrete; they are not new design blockers.

- Prebuild and validate all one-row bodies before the first core call. Test a
  later-event defect to establish zero callbacks and zero state mutation, rather
  than proving only first-event rejection. Keep the source report, prepared data,
  ordering and initial baseline detached from later mutations of the caller's
  capture map. Observer-visible wire dictionaries must be copies or immutable
  views; baseline/readback bytes must be bound locally before callback execution.
- Verify the observer sees the confirmed journal, receives the exact preceding
  baseline and new readback, and cannot alter a later body. Its exception must
  expose only the fixed safe code, with no callback exception chain. No subsequent
  core call, source POST, automatic resolution or helper compensation may occur.
- Preserve completed event0 archives in the second-POST-timeout case. An archived
  attempt response is not confirmation. In the observer-failure case require a
  retained confirmed tombstone, no later source POST and owned finally cleanup.
  Keep the full pytest and pinned 3.81.0 lifecycle gates, including three source
  POSTs/three confirmed intents/count6, zero-new repeat, compensation6/count0,
  absent owned resources and cold replay after teardown.

Rollback remains a scoped code revert while retaining private captures and
journals. Code rollback does not compensate remote effects; only the existing
owned controller has the bounded lab cleanup role. No endpoint, credential input,
apply CLI, production transport or production readiness is introduced.

Knowledge verdict: **Used and sufficient**. A narrow indexed Ghostfolio lookup
reached the applicable import acceptance/date and saved-input preservation
concepts, both current at review time. The committed project contracts remain
authoritative. No new portable operational knowledge was established.

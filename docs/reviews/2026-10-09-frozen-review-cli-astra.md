# Frozen-review CLI — Astra design review

Date: 2026-10-09. Scope: independent design gate for the local `check-review`
command. This is not a PR or implementation review. No private inputs, service,
owned runtime bundle, network endpoint, or Beads state was accessed or changed.

Reviewed plan: `docs/plans/2026-10-09-frozen-review-cli.md`.
Exact plan SHA256:
`2fdff50431f48de4855c3017ecc6a656c1a3411acb2abb63a24e12d3aa14e687`.
Inspected code baseline:
`2007c1b49b30025768191a8c025023facfb6182f`.
The inspected source and existing frozen/review test files have no diff against
that baseline. Applicable AGENTS/CLAUDE guidance, Python/security rules, original
gated proposal, frozen/review contracts and relevant preservation knowledge were
also consulted. The repository and CI identify Python 3.13 as the verified runtime.

**Verdict: APPROVE. No blocking design finding.** A bounded capture wrapper around
the existing complete validator is sufficient. The approval applies to the exact
plan above; it grants neither production write permission nor financial readiness.
Implementation tests and retained-bundle verification remain required acceptance
evidence and were not executed as part of this design review.

1. **Capture boundary — adequate as designed.** Read the configuration and report
   through `read_local_bytes`; validate the exact positive integer budget before
   either read. Parse the captured configuration with
   `review_capture_configuration`, resolve its four references against the input
   root, and capture each role once. Pass those original byte values and the
   externally supplied report pin to `validate_frozen_review`. Do not derive the
   pin from the report, substitute report provenance for actual input capture, or
   read files again for validation. Relative CLI config/report paths follow the
   existing working-directory convention; role references follow the input root.
   Gate4 correctly requires these conventions to be documented explicitly.

2. **Reader scope — preserve the actual existing guarantees.** The complete
   reader rejects a symlink at the supplied file path, resolves containment under
   the resolved root, opens read-only with `O_NOFOLLOW | O_NONBLOCK`, checks the
   opened descriptor for a regular file and reads at most the budget plus one
   byte. It closes the descriptor on failure. It does not reject every ancestor
   symlink or supply an atomic, adversary-resistant filesystem snapshot. Reusing
   it unchanged is appropriate for this local saved-file command. The plan's
   capture-consistency and authenticity limitations must remain explicit; do not
   broaden documentation into a stronger filesystem guarantee.

3. **Validation and output — adequate as designed.** The existing validator checks
   the external lowercase SHA256 pin and compares the complete restricted-YAML
   report against recomputation, preserving scalar types and sequence order.
   The computation retains bounded numeric processing, current-clock eligibility,
   adoption/history checks and financial-shortfall blockers. Build the small
   result solely from the returned recomputed artifact. `review_verified: true`
   means this captured chain verified; `import_ready` remains false. Null wire for
   all-existing activities and diagnostic wire with shortages are both legitimate
   validation outcomes. Neither is permission to send anything. Count-only output
   plus computed fixed blocker codes avoids returning identifiers, holdings
   values, source paths or wire content.

4. **No publication — essential and covered by the plan.** Do not call
   `review_local_snapshot`: after computation it creates private directories,
   acquires a target lock and publishes a report. Call the pure validator directly
   from the new read-only wrapper and give the CLI branch its own immediate
   return. Existing `main` handling maps coded validation errors and ordinary
   local input failures to exit1 without stdout; valid diagnostic results use
   exit2. Argparse keeps its existing syntax-error behavior. No persistence,
   transport, credential lookup, journal, permission or lock operation belongs
   on this path. The preservation regression with a common input/output root
   discriminates the actual local-write risk documented in the KB.

5. **Verification and rollback — proportional and sufficient.** The planned
   socket-forbidden synthetic cases cover new activities, adoption/null wire,
   shortages, external-pin mismatch, changed exact captures and provenance,
   one capture per role, unsafe or excessive files, early budget refusal and
   output privacy. Patching publication/lock/directory/permission/credential
   boundaries after fixture construction and comparing bytes and modes on both
   success and failure will distinguish a read-only wrapper from accidental reuse
   of a publishing command. Existing frozen tests already cover typed comparison,
   YAML policy, numeric bounds and clock drift. Full pytest plus offline replay of
   the retained owned bundle after teardown is sufficient for this CLI change;
   another Docker or network rehearsal would add no command-specific evidence.
   A scoped commit revert is a complete code rollback because this command must
   create no artifacts or remote mutations.

Knowledge lookup: applicable. The indexed
`operations/ghostfolio/saved-input-report-preservation.md` concept is stable and
within its freshness window; its owning source contracts and existing regression
tests agree with the inspected baseline. Knowledge verdict: **Used and sufficient**.
No new portable lesson requires capture; this review records repository-local
design and leaves implementation, commit, CI and PR delivery to the owning session.

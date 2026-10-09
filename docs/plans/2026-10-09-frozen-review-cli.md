# Offline frozen-review operator command

Date:2026-10-09. Design owner:`infra-4g8u.55`. Scope: expose the approved frozen
computation as a read-only local check; no production apply or authorization.
Baseline:`2007c1b49b30` (resolve full commit in the review). Applicable source is
`read_local_bytes`, `review_capture_configuration`, `compute_offline_review`,
`validate_frozen_review`, `main`, their existing tests and the frozen/review docs.
All financial computation remains unchanged. This is I11 operator delivery under
Florent's autonomous implementation permission, with Astra design gate before code.

## Gate1 — bounded actual-input capture

Add callable `check_local_frozen_review(config_path, review_path, review_sha256,
input_root, max_bytes)` and CLI `check-review --config FILE --review FILE
--review-sha256 HEX --input-root DIR --max-bytes N`. Report and configuration must
both be regular bounded local files inside the root. Reuse `read_local_bytes`
unchanged; resolve each of the four role references against input_root and read
once. Validate exact positive integer budget before any read. Use captured bytes
for full validation, never reconstruct a pin from the report. The hash argument
is a nonsecret externally supplied content pin, not an approval credential.
Existing local reader restrictions and current-clock frozen validation apply.
No online request, credential/environment access, lock, publication, directory
creation, chmod, journal mutation or permission change. It is not an atomic
filesystem snapshot; the content pin/full comparison reject mismatched captures.
Do not claim raw source authenticity or current remote freshness.

## Gate2 — safe operator result and refusal

Call `validate_frozen_review` on the captured chain. Success returns only
`review_verified:true`, new/owned/adopted counts, holdings-shortfall count,
`import_ready:false` and computed fixed blocker codes; no target identifiers,
security names, paths, raw data, wire or exact balances. All-existing/null wire
and blocked-shortfall diagnostic reports can verify; neither authorizes dispatch.
Success exits2, consistent with the existing diagnostic CLI. Invalid data or pin
exits1 with no stdout and fixed errors under existing main handling. Argparse
syntax errors remain its existing usage behavior. No apply command is introduced.

## Gate3 — discriminating offline verification

Socket-forbidden synthetic tests prove success/new3, all-adopted/null wire and
shortfall diagnostics; pin failure and exact capture/provenance tamper; each
reference read once; missing/outside-root/symlink/nonregular/oversized paths;
invalid byte budget before reads; output/privacy counts only. Input/output/state
bytes and modes stay unchanged on successful and failed runs, including a common
root with an existing review inside outputs. Patch writers/locks/chmod/mkdir and
credential/network transport to forbid hidden side effects after fixtures exist.
Reuse frozen numeric/type/alias/time tests rather than duplicate financial policy.
Run full required pytest and semantic diff/numstat/privacy audit before commit.
Exercise this CLI against the retained owned frozen bundle after resource teardown,
with unchanged archive bytes and no network; no new Docker rehearsal is needed
because this command cannot dispatch and does not change the runner.

## Gate4 — delivery and rollback

Document the exact CLI/root/path/pin/exit conventions in README and frozen contract.
Open a stacked PR and leave review/merge external; do not wait to do other approved
work. Retain actual history/adoption and production approval/recovery gates.
Blast radius: one local capture wrapper, CLI registration, synthetic tests/docs.
Rollback: revert scoped implementation commit; there are no created artifacts or
remote mutations to compensate. Astra records exact plan hash before code.

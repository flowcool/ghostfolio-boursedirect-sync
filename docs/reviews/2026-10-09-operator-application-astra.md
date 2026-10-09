# Operator application design review

Date: 2026-10-09. Reviewer: independent Astra design-review agent.

**Verdict: APPROVED for packages A and B. Package C is not approved by this
review. No blocking design finding remains for A/B.** This is preimplementation
design review, not implementation, security-merge, PR or production approval.

Reviewed plan: [`2026-10-09-operator-application.md`](../plans/2026-10-09-operator-application.md).
Exact plan SHA256:
`87438b887a74628f0fc81e60219d73d381b2d90662088de3ada13348874424ff`.
Committed implementation baseline:
`47a87a35737a4036325858cfb4996d4942b8e1ec`.
The plan was an uncommitted new file at review time; the digest identifies the
reviewed bytes independently of its eventual commit. Approval does not extend to
subsequent material changes or to production execution.

## Scope and evidence inspected

The review followed the actual local chain rather than treating the original
proposal's historical missing components as current blockers:

- `CLAUDE.md`, `FINDINGS.md`, Python/security rules and the original manual-import
  proposal, particularly I7/I8/I11 and the execution/recovery boundaries.
- Complete bounded local capture, private atomic publication, output/input alias
  guard, full frozen-review recomputation and `check-review` CLI implementation.
- Canonical wire validation, bounded JSON handling, the single-event dispatch
  core, frozen sequence and retained fixture capture/observer integration.
- Existing exact-origin GET transport, CLI exception boundary, relevant frozen,
  dispatch, snapshot and owned-runner regression tests and their design contracts.

No runtime archive, account document, credential or live endpoint was inspected.
No test or disposable lab was run for this design-only review. Existing tests
were read as contract evidence, not claimed as a new passing execution result.

## Package A: offline preview and private proposal

The proposed command is a useful operator boundary over existing full validation.
It must capture the config, report and four actual referenced roles once and use
`validate_frozen_review`'s recomputed result. Comparing only the external pin or
calling `check-review` and then reopening files would not satisfy this design.
The pin remains byte integrity, not authenticity or approval.

The dry-run truth table is sound: absent/`1` prevents execution; `0` without
`--execute` still previews; `0` with `--execute` fails at the explicit application
gate before reads or side effects. Other environment spellings fail. Reading
`DRY_RUN` is allowed; looking up destination credentials or constructing a request
adapter on these paths is not. Valid diagnostic preview exits 2 without accepted
events, a journal, a lock or any readiness claim.

Export is an explicitly requested local publication within dry-run mode. It
preserves the exact recomputed new-only batch bytes and does not simulate server
acceptance. Shortages or unresolved adoption reject export; null wire rejects
instead of producing an empty batch. Pure preview may retain shortage diagnostics.
The permanent production blockers remain visible. The manual batch proposal must
not be described as inheriting the single-event fencing/readback protocol or as
permission to upload blocked real data.

The plan incorporates the known captured-input replacement failure at the new
publication boundary. Before mkdir, chmod or publication, validate containment,
existing parent directories, destination kind and every captured config/report/
role path and inode alias. The implementer additionally confirmed refusal of all
symlink ancestors, nonregular existing targets and invalid existing parents,
before permission changes. Only the outputs root may be created; nested parents
must already exist. The resolved root must retain the documented ignored-output
boundary. Do not infer preservation merely from hashes or atomic rename.

These conditions make no-lock proposal publication appropriate within the existing
trusted local filesystem model. They do not promise an atomic multi-file capture
or protection against an adversarial concurrent filesystem writer. Validation
failures must preserve prior output and source bytes/modes. A filesystem failure
after rename may leave the new proposal visible with uncertain crash durability;
it must not be reported as a successful export or treated as remote application.
Rollback is code revert with private evidence retained.

## Package B: bounded HTTPS callback

The fixed request callback matches the existing single-event core without moving
its authority into transport. The factory may validate and privately capture the
exact allowlisted HTTPS origin and environment bearer once, but must neither
connect nor exchange credentials. No CLI path invokes it in A/B.

Preconnection validation must enforce the positive exact-integer budgets, fixed
GET/POST method/path/body pairs and one canonical event. Use the existing bounded
JSON/numeric guard before canonical wire reconstruction so a short exponent token
cannot cause unbounded decimal expansion. A size limit alone is insufficient.
No other mutation or arbitrary endpoint belongs in this adapter.

The proposed verified TLS, identity encoding, exact status/content-type checks,
bounded raw read and fresh connection per call are compatible with the core.
Transport returns raw bytes; the core remains responsible for complete snapshot,
acceptance and exact transition validation. HTTP201 does not become success on its
own. The existing socket timeout is per blocking operation, not a global deadline.

Creation, send, response/header/read and close failures must produce fixed safe
exceptions without private exception chaining, remote bodies, token or origin.
The implementer confirmed separate close-error handling and no retry. A failed
close after POST must remain a conservative failure under the already persisted
uncertainty fence. Preserve the original error when cleanup also fails, or return
a fixed safe cleanup code; neither outcome may allow retry or false confirmation.
Keeping the older `snapshot` implementation unchanged is a reasonable scope bound.

## Acceptance and remaining boundary

The planned acceptance is appropriate: forbidden sockets/credentials/intents in
preview; complete pin/provenance tamper and capture-once checks; exact private
export, alias/escape/type failures and prior-state preservation; strict transport
inputs, TLS/header/byte budgets, every fault stage and secret-free exceptions.
The transport must also be exercised through the real single-event core with
fake HTTPS responses, including lost POST response and retained account fencing.
An adapter-only happy-path test would not cover that composition.

Run the required full offline pytest suite after each package. A private mirror
of retained owned frozen evidence can prove exact preview/export bytes without
touching the original archive or uploading anything. Existing owned-runner tests
cover the earlier chain; they are not evidence of a real HTTPS rehearsal of this
new adapter. No such rehearsal is needed for A/B's stated acceptance.

A/B may be implemented and shipped as this explicit interim operator delivery.
The future execution controller must receive a separate exact design review;
this report does not remove permanent readiness blockers, rename the lab helper
into production authority, satisfy G6/G7, authorize a production write or permit
shared-service recovery actions. The existing pre-merge security review rule for
new credential/HTTP code remains applicable; this design review is not that gate.

Knowledge verdict: **Used and sufficient**. The narrow indexed Ghostfolio lookup
reached the fresh input-preservation, import/date and authentication concepts.
Their applicable constraints were checked against the owning repository contracts
and current baseline. The session-bearer choice is appropriate to the explicitly
interactive scope; the corpus's scheduled-token guidance does not require adding
an authentication POST here. No new portable lesson or corpus mutation is needed.

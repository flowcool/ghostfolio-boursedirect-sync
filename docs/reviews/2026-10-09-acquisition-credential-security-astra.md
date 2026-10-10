# Acquisition credential-security gate

Date: 2026-10-09. **APPROVE the OFFLINE A merge credential-security gate**
for PR27 commit `9ca8210b3f50a526b9a3eeb4a45400e42504dd7d`.
This is a targeted independent security gate, not general PR review, external
CodeRabbit approval, or production authorization. No blocking finding in scope.

Inspected `collector/core.mjs`, `collector/tests/core.test.mjs`, the network
bootstrap, `docs/design/acquisition-core.md`, security rules and the original
Astra review's final approved A scope. HEAD matched the requested commit and
the worktree was initially clean.

- Authentication authority follows a case-normalized principal in the fixed
  per-user namespace, independently of portfolio/output roots. Exclusive mkdir
  locking and retained unfinished attempts fence cooperating invocations.
- `releasePrincipal` revokes the handle before rmdir/open/fsync/close. Every
  journal read/mutation rejects that handle thereafter; repeated release cannot
  remove a successor's lock. The four fault-injection regressions check both
  journal preservation and successor-lock protection.
- Permit consumption validates phase, page/frame epochs, exact request fields,
  nonce, lifetime and no redirect, then durably publishes consumption before
  returning continuation authority. Unknown source roles remain disabled;
  failed publication returns no request permission. Success requires consumed
  requests and unfinished attempts remain fenced across sessions.
- OTP/TOTP inputs use the environment-shaped helper boundary, with mode conflict,
  clock, age, same-step and near-expiry checks. The command schema carries no
  credentials. No secret acquisition, logging or persistence path was added.
- Private files use ownership/mode, no-follow and single-link checks; publication
  uses exclusive temporary files, file and parent fsync. Public diagnostics map
  only literal allowlisted codes and otherwise return `ACQUISITION_FAILED`.
  There is no browser, transport or production enrollment entry point here.

The mutable handle, source characterization, request observations and environment
object are trusted caller inputs at this pure-helper boundary. They do not prove
browser ownership, credential provenance or observed broker success. Callers must
use `diagnostic` rather than expose raw filesystem exceptions. These are explicit
integration obligations, not offline-A merge blockers.

Failed lock removal, interrupted enrollment/acquisition, and uncertain journals
can require manual recovery; there is deliberately no stale-lock retry or reset.
Changed HOME, independent hosts, intentional deletion and hostile same-user state
mutation are outside the documented cooperation guarantee. Retaining these
bounded limitations is preferable to clearing authentication uncertainty.

Validation: the parent reports **953 Python / 76 Node tests passing**, including
four release regressions failing before the correction and passing afterward.
This reviewer inspected those regressions but did not independently reproduce
that complete run. A direct targeted invocation of
`node --import ./tests/no-network.mjs --test tests/core.test.mjs` in this worktree
stopped before tests with `ERR_MODULE_NOT_FOUND` for the uninstalled `yaml`
dependency. No dependency installation, network, Docker, real credentials or
shared Beads tests were performed. That local setup limitation is not evidence
of an implementation failure and does not supersede the parent's exact-head run.

**B browser integration remains HOLD** under its separate capability/design gate.
This approval grants no broker credential provisioning, seed retrieval, live
enrollment/authentication, collection or Ghostfolio writes. Parent owns commits,
Beads reconciliation, external checks and merge authorization.

Knowledge verdict: **Used and sufficient**. Narrow indexed lookup reached the
stable `operations/ghostfolio/saved-input-report-preservation.md` concept
(verified 2026-10-09; stale after 2026-12-31), supporting private publication and
alias preservation checks. Lookup occurred during review rather than at task
start; no new portable knowledge or corpus modification resulted.

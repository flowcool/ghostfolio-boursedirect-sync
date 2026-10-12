# Bourse Direct working agreement

## Working mode: outcome first

Beads owns scope, authority, acceptance and live work state, routed with
`project=ghostfolio-boursedirect-sync`. This agreement owns execution policy.
It supersedes older process prescriptions in plans, reviews and contracts;
financial, credential and transport invariants remain in force.

Start with the owning issue and its latest findings. Identify the next missing
user-visible result and finish the smallest working path to it. For acquisition,
that means the delivered entrypoint connects, identifies the correct accounts
and saves usable documents. Technical primitives and green tests support this
result; they do not establish actual acquisition or delivery.

Reuse existing code, runtime and successful evidence. Add a helper, abstraction,
contract or independent ticket only when a concrete failure or the next acceptance
criterion needs it. Keep in-scope fixes in the owning ticket. Collect review fixes
into a coherent batch before the next verification/review cycle. Optional cleanup,
sibling alignment and general hardening follow working acceptance unless their
absence demonstrably threatens correctness, credentials or the authorized run.

## Validation proportional to the change

- Guidance, prose, labels and ticket edits: inspect the semantic diff, local links,
  line endings and whitespace. Run `python3 scripts/check-docs.py` for agent/docs
  entrypoint edits. Application suites and browser labs are unnecessary here.
- Local logic changes: run the affected offline regressions, including a case
  that distinguishes the reported failure from success. Broaden only for changed
  shared behavior, an unexplained failure or a concrete integration concern.
- Authentication, credential transport, financial conversion or recovery changes:
  check the changed boundary and its relevant refusal/uncertainty cases. Use a
  disposable native integration check when unit tests cannot prove that boundary.
  Reuse unchanged browser, vault, accounting and cleanup qualification.
- Before delivering a runtime-changing batch, require one full offline verification
  on the final runtime inputs and the required final-head CI/external review.
  Successful CI can supply the full suite; do not duplicate it locally or rerun it
  for subsequent prose-only edits. Repository-required review coverage still applies.

Record command, result and relevant input hashes using the existing keyed YAML
when runtime verification needs reuse. Name the actual dependency that invalidates
saved evidence; a new commit SHA alone does not invalidate unchanged runtime proof.
`bash scripts/verify-local.sh` is the full fallback, not a per-edit ritual. Automated
CI stays enabled. Tests use synthetic inputs and isolated state, never real
credentials, broker authentication, production or the shared Beads database.

## Functional and security boundaries

- Functional Python, no custom classes or type hints; follow
  `.claude/rules/python-conventions.md`. The document importer consumes saved HTML
  without fetching its assets. Interactive acquisition is a separate approved path.
- Preserve exact Decimal/date/currency/fee semantics, source-to-note matching,
  account bindings, direct-child columns/blank slots, idempotency, holdings controls
  and uncertain-result journals.
  Unknown financial operations block their affected account/period. A laboratory
  success does not prove complete production history or authorize financial writes.
- Credentials stay in the approved vault/environment path; personal inputs,
  outputs, journals and runtime receipts remain private and off Git. Preserve the
  existing secret confinement, origin, redirect and one-attempt authentication guards.
  Ghostfolio origins reject userinfo, query and fragment; preserve preview-by-default
  application and exact saved-wire/source replay before separately authorized writes.
- Unexpected credential-bearing requests or uncertain authentication outcomes stop
  the attempt without retry. Denied unrelated public subresources need not abort a
  known safe form if the current reviewed policy explicitly permits continuation.
  This instruction does not itself grant a new request role or change runtime policy.
- Use the relevant contract through the [design index](docs/design/index.md) when
  changing behavior. Read `.claude/rules/security.md` for external transport or
  credentials, and `.claude/rules/delegation.md` for execution boundaries.

## Access, authority and delivery

For acquisition resumption or lab operations, read the
[connection procedure](docs/operations/source-connection.md), then use its existing
check/status entrypoints and private receipts. Resume the first missing stage.
Historical success remains evidence; a fresh session needs its actual session state.
Keep the qualified browser/image unless a demonstrated fault, security requirement
or unavailable artifact requires replacement; qualify only the affected dependency.

Florent authorizes direct operation of the dedicated acquisition lab under its
existing daemon/resource ownership and rollback checks. Shared host services and
production wiring remain infra-owned. Carry recorded approvals across sessions;
ask only for genuinely new authority or indispensable input. Broker attempts,
production deployment, financial writes and destructive cleanup retain their
separate explicit gates. Existing publication authority governs pushes/releases.

Commit authorized changes atomically after proportionate verification. CodeRabbit
review is triggered externally; required CI and completed review cover the final
head before guarded merge. Resolve confirmed correctness/security findings; explain
and defer optional suggestions rather than converting each into a delivery gate.

Record material decisions, failures, blockers and acceptance milestones in Beads;
combine routine successful checks into one evidence note per coherent batch.
Reconcile Beads/Git at terminal close or handoff, not after every edit. Close an
acceptance owner only with its actual result or an explicitly approved scope change.

For engineering skills, use the existing Beads and domain routing in
[docs/agents/issue-tracker.md](docs/agents/issue-tracker.md),
[triage-labels.md](docs/agents/triage-labels.md) and
[domain.md](docs/agents/domain.md).

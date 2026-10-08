# Legacy duplicate-candidate quarantine proposal

## Problem and observed evidence

Read-only saved-source analysis found three source trades with one existing
target-account candidate each when comparing type, quantity and unit price.
All candidates share the source calendar day in UTC and Europe/Paris, but none
uses UTC midnight. Two fees agree exactly; one differs. Evidence is retained in
ignored private keyed YAML. This is diagnostic similarity, not adoption proof.

The current exact financial fingerprint correctly rejects nonmidnight matches
when fees agree. A fee difference can instead leave no exact fingerprint match
and classify a likely existing trade as new. Later readiness gates currently
prevent delivery, but this classification must not become a duplicate-write
path when those gates are eventually satisfied.

## Scope and rationale

Add a conservative quarantine before classifying an unowned source trade as new.
Compare existing target-account BUY/SELL rows with the same symbol, data source,
type, quantity and unit price. A remote UTC calendar day within one day of the
source day is a potential legacy duplicate regardless of fee, price currency,
active flag or midnight context. The one-day bound catches timezone crossings
without assuming a historical timezone. Unsupported context must block rather
than erase evidence. Do not loosen owned-marker, exact-adoption or holdings gates.

An exact financial match continues through the existing strict adoption path.
When no exact match exists but a potential legacy duplicate does, fail with a
safe code. Do not emit or persist a new-activity wire artifact, normalize a date, change
fees, adopt a row, or create a remote activity. This deliberately can block a
legitimate repeat trade. Resolving such a block needs a separately reviewed
source-bound contract; there is no automatic override in this amendment.

Unrelated account, security, type, quantity, price or data source does not trigger
the quarantine. A trade more than one UTC calendar day away remains outside this
narrow rule. This rule is a bounded safety improvement, not a proof that absence
of a candidate establishes absence of every historical duplicate. Existing
in-memory numeric wire validation before reconciliation may remain; a quarantine
error must stop before an output artifact is replaced or an intent is created.

## Phases and gates

1. Independent Astra design review of this proposal; amend until approved.
   Keep real validation owner open. No implementation before approval.
2. Create one implementation issue and one dependent independent review issue.
   Implement the local pure-function guard and synthetic socket-forbidden tests.
   Include exact-fee/date regressions, mismatched fee, midnight crossing,
   inactive/unsupported context, and negative isolation cases.
3. Run the required complete test suite and semantic/whitespace diff checks.
   Independent PR review follows implementation sequentially. Commit and push
   under existing project authorization; merge only after review and passing CI.
4. Re-run private diagnostic classification against the existing immutable
   capture. No snapshot rewriting, manufactured history assertion or production
   write. Any remaining mapping/date/history gate stays explicitly unresolved.

## Acceptance, rollback and limits

The implementation issue owns the duplicate-quarantine regressions and unchanged
strict-adoption behavior. The review issue owns independent financial/security
assessment and the PR report. Real account/mapping/history evidence remains owned
by `infra-4g8u.25`; synthetic tests cannot satisfy those criteria.

Blast radius: offline classification and synthetic tests only. No new dependency,
network access, credential handling, production mutation or apply command.
Rollback: revert the scoped implementation commit; preserve ignored private
captures, preparation artifacts and journals. Review the exact revert diff and
run the required suite. No remote rollback is necessary.

# Execution and delegation — Bourse Direct

This project-local policy follows the global working agreement. Sibling projects
own their own instructions; file equality is not a delivery prerequisite.
[AGENTS.md](../../AGENTS.md) owns outcome-first execution and validation.

## Ownership and review

Codex owns implementation and technical decisions. Work sequentially; delegate
only on Florent's explicit request or when an applicable skill requires independent
review. Use the cheapest capable available model for authorized delegation.
Astra requires Florent's explicit nominal request. Its absence does not block normal
engineering decisions: use main-thread analysis and the required CodeRabbit PR review.
CodeRabbit triggering is externally managed. Keep completed historical reviews as
evidence for the scope they inspected; qualify changes rather than re-reviewing
unchanged foundations. PR-review subagents are outside this project's workflow.

## Infrastructure boundary

Operate the dedicated acquisition lab under its existing explicit authority,
private daemon/resource receipts and verified rollback access. Reuse its SSH/Docker,
vault and browser mechanisms. Shared service changes, production deployment,
secret rotation and network exposure belong to infra through a scoped handoff.
Broker authentication and Ghostfolio financial writes retain separate authority.

## Convergence

Use the existing owning contract for a concrete behavior change. Amend it when
necessary to implement the next accepted result. Create another design artifact
only for a materially different decision that the existing contract cannot express.
Keep implementation and acceptance evidence together in the owning Beads issue;
optional generalization follows demonstrated working acceptance.

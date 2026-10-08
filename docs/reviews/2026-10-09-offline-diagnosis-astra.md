# Astra design review: reproducible offline diagnosis

Baseline: `5411b7030ec7113c894c58486943b81ff46ee59a`.
Independent reviewer: Codex GPT-6 Astra. Verdict: **APPROVE** amended plan.
Public code/contracts/plan only; no private inputs, network, mutations or tests.

Initial required finding: a valid captured input can occupy the diagnosis output
path when input-root includes outputs. Atomic replacement would overwrite it.
The amended plan rejects resolved output/input collisions before publication and
requires preservation tests. Comparison/output budgets fail without truncation;
keyed remote evidence avoids duplication; evaluation-time context is explicit.

Implementation invariants: shared validation retains identity/account/numeric/
readiness checks; the legacy predicate is unchanged; exact similarity is never
adoption. Enumerate owned markers separately across all rows, including nontrade,
other-account and duplicate markers. Never consume candidates or silently resolve
multiplicity. Original timestamps and allowlisted exact decimal values remain
private; raw comments/full records never enter the report. Validate the whole
snapshot before publication. No history assertion, holdings verdict, wire artifact,
adoption, write intent or external action is authorized.

Tests must discriminate exact/near/absent matches, inclusive day boundaries,
serialized values, unsupported/inactive context, foreign/duplicate ownership,
shared candidates/order, provenance, permissions/locking, input/output collisions,
budgets and preservation of previous outputs/inputs/journals. Existing review and
quarantine tests must pass unchanged.

This is design approval, not implementation verification or source-acceptance
evidence. The PR remains open; CodeRabbit triggers and merging are external.
KB verdict: **Used and sufficient**; indexed saved-snapshot knowledge applies.

## Behavior

Describe the problem and resulting behavior. Keep this PR focused on one change.

## Release impact

<!-- Version bump (none/patch/minor/major), breaking or operational change,
migration steps, rollback. Write "None" if there is no impact. Required, in
plain words, when the PR is labeled breaking-change or compat. -->

## Verification

- Command:
- Expected result:
- Observed result:

Use synthetic inputs and isolated state. Do not attach secrets, statements or
contract notes.

## AI assistance

State whether AI assisted this change and what the author verified.

## Review

Follow the invoked skill for pre-PR review. Record independent Standards and
Spec reports when `code-review` applies. Add the security note when
`security-review` applies. Pullfrog reviews the final code head.

- [ ] Merge `main` into the branch before the first push.
- [ ] Require a completed Pullfrog review of the final code head and green CI.
- [ ] Read the general review and all threads. Address every remark, including
      cleanup, as required by AGENTS.md, and record the review link and
      reviewed head SHA. Repeat after each new commit.

Run `pr-ship` from the main session after these review checks. Keep publication
and live-write authority separate. Docs-only PRs require green CI.

Review evidence: <!-- completed review URL and reviewed commit SHA -->

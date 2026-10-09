# Build and release guarantees

This repository ships no container image and no release artifact yet: the
importer is an offline command-line tool. Every pull request, whatever its base
branch (work is delivered as stacked PRs) and including documentation-only
changes, runs the offline test suite on Python 3.13 and a whitespace check
(`offline-tests.yml`). CodeQL analyzes Python independently. Dependency Review
rejects newly introduced moderate or worse dependency vulnerabilities, including
development scope. Required checks must pass before merging.

Runtime requirements pin the complete dependency closure. Dependabot proposes
weekly Python and Actions updates (a Python release is proposed once 14 days
old; security updates ignore the cooldown). Never auto-merge dependency changes
without the required checks. The disposable Docker acceptance lab
(`scripts/disposable_acceptance.py`) is opt-in and never started by CI.

When the `collector/` Node.js tests gain a package manifest, add an `npm`
ecosystem to `dependabot.yml` and `javascript-typescript` to CodeQL.

## Release notes

`release.yml` groups GitHub's generated notes by label. `pr-release-labels.yml`
adds `feature`, `fix`, `documentation`, `maintenance` and `breaking-change` from a
conventional PR title; it is advisory and never a required check. It runs on
`pull_request_target` (base-branch workflow and script, write token, also for fork
PRs) and must never check out or execute the PR head. A
`breaking-change` or `compat` PR needs a filled "Release impact" section.

## CodeRabbit

`.coderabbit.yaml` enables automatic reviews for every base branch and draft
PRs, so stacked PRs are reviewed. Reviews beyond the plan's included hourly
allowance use usage-based billing once the trial ends; manage it in the
CodeRabbit billing settings. A CodeRabbit review is not a substitute for CI.

## Rollback

Revert a maintenance merge through a PR and wait for all required checks.
Repository administrators can temporarily disable a ruleset if a broken required
workflow prevents its own repair; restore it after the repair passes. No GitHub
change deploys anything.

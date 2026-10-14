# Bourse Direct → Ghostfolio — agent guide

## Product

Community Docker connector. It imports Bourse Direct (PEA, PEA-PME) operations
into Ghostfolio. It is Docker-first. Every setting comes from ENV. It runs
unattended with `docker compose up -d`. The target contract is the sibling fork
`../ghostfolio-ibkr-sync`: `CRON`, `DRY_RUN` on by default, `APPRISE_URLS`,
additive and deduplicated import. Before you add a mechanism, cite the line of
ibkr or degiro that does the same thing. If no sibling line exists, stop and ask.

Keep public files free of personal hosts, paths, account identifiers and private
work-tracker IDs.

## Current plan: v1 rebuild (option B)

- The v1 is a new branch on the ibkr skeleton. The previous work stays in Git
  (tag `legacy-wip`). v0.1.1 is a preview-only legacy release.
- Track A (first priority): BillCollector downloads the notices with Playwright,
  in the flowcool fork, and publishes them to Paperless. BillCollector owns the
  Bourse Direct login and the vault access.
- Track B (in parallel): an importer reads the PDF notices ("avis d'opéré")
  from Paperless, read only.
- The connector imports only what Ghostfolio shows exactly: buy, sell, coupon.
  It stops on a security for each operation that changes the number of shares.
  It stops on a separate TTF line; the operator enters the TTF manually. It
  ignores custody fees and shows a message.
- The only spec is the active OpenSpec change under `openspec/changes/`. The
  archived change `2026-10-14-unattended-notice-import` is history only.

## Method (same as ibkr)

- **Spec first.** No code without an OpenSpec change that Florent approved. A
  spec has 1 500 words or fewer. It describes visible behavior and error codes,
  never internal mechanisms. Do not specify recovery tools, lab tools, release
  process or docs layout. When reality is different from the spec, stop and
  report. Do not change the spec silently.
- **No bead before the spec.** After approval: one epic for the change and one
  bead per task. Each bead gives the spec path, requirement, scenario,
  acceptance command and files to touch.
- **One bead = one fresh session.** Claim, implement, prove, close, stop. Do not
  start the next bead. Budget about 150 tool calls; above that, stop and report.
- **Done = the scenario replayed for real.** Put the command and its output in
  the closing note. Green unit tests are not done. No review beads: CodeRabbit
  reviews the PRs. A decision bead never delivers code.
- **Tests:** offline pytest, one real anonymized notice for each operation type
  and each error code. No synthetic protocol proofs. No tests for docs or CI.
- **Git:** one branch and one PR per bead. Merge when CI is green and CodeRabbit
  finished its review of the head commit, or on Florent's explicit go. A PR that
  changes only `openspec/`, `docs/` or `*.md` needs CI green only. Wait with
  `~/.agents/bin/pr-gate <n> --repo flowcool/ghostfolio-boursedirect-sync`, never
  a `sleep` loop. Fix or answer each actionable comment. In Claude Code, the
  implementing agent runs the PR lifecycle itself, without a subagent.
- **Operation beads.** A bead that acts on real state (Ghostfolio write, NAS)
  runs only from an `Operation plan:` in its design that Florent validated. In
  this repository, the only ceremony is the first real Ghostfolio write. A
  failed or uncertain step: record it and stop.
- **Ask Florent only for:** a Bourse Direct fact missing from the spec, a
  Ghostfolio write, a scope change. One question at a time, in plain French,
  with your recommendation.

## Budgets

- The main Python file has 2 500 lines or fewer.
- No new compose file and no lab without Florent's approval.
- No release before one real run.
- Docs: README, one spec, AGENTS.md. History stays in Git. No new plan, review
  or contract files.

## Writing style

Use ASD-STE-100 (Simplified Technical English) in specs, README, bead first
lines and messages to Florent: short sentences, one idea per sentence, active
voice, no internal jargon.

## Safety invariants

- The importer has no broker login and no vault access. BillCollector owns the
  Bourse Direct login and its lock rule (stop after 2 consecutive failures).
- Secrets come from ENV only: the Ghostfolio token and the Paperless token.
  Never put a secret in Git, logs, Beads, tests or reports.
- Paperless is read only. The importer never writes to Paperless.
- Personal data stays off Git: `inputs/`, `outputs/`, `state/`, `tmp/`, `audit/`.
- Ghostfolio: `DRY_RUN=1` by default. Writes are additive only, never update or
  delete. Real writes need Florent's go.
- Money: `Decimal`, exact dates, EUR. An unknown operation is skipped and
  reported; the other operations continue.

## Durable work state

- Beads project metadata: `project=ghostfolio-boursedirect-sync`.
- Root epic: "v1 rebuild (option B)". Find it with
  `bd list --metadata-field project=ghostfolio-boursedirect-sync --type epic`.
- Private pointers (bead IDs, decision document) live in `CLAUDE.local.md`,
  which Git ignores.

## Code

Functional Python, no classes, no type hints:
[python conventions](.claude/rules/python-conventions.md),
[security rules](.claude/rules/security.md). The legacy code stays in place
until the rebuild replaces it.

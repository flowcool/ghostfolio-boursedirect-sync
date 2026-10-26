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

- The v1 adopts the complete applicable common core from ibkr v3.0.0
  (Florent, 2026-10-22). Follow its modules and typed functions; classes describe
  data. Before coding, read the active design for the source commit, coverage
  and BD adaptations. Cover every applicable implemented runtime and release
  requirement. Review later source updates separately. No shared library or
  automatic core projection.
  The previous work stays in Git (tag `legacy-wip`). v0.1.1 is a preview-only
  legacy release.
- Track A (first priority): BillCollector downloads the notices with Playwright,
  in the flowcool fork, and publishes them to Paperless. BillCollector owns the
  Bourse Direct login and the vault access.
- Track B (in parallel): an importer reads the PDF notices ("avis d'opéré")
  from Paperless, read only.
- The connector imports only what Ghostfolio shows exactly: buy, sell, coupon.
  It stops on a security for each operation that changes the number of shares.
  It does not track the TTF (only on statements, never in Ghostfolio). It
  ignores custody fees and shows a message.
- The only spec is the active OpenSpec change under `openspec/changes/`. The
  archived change `2026-10-14-unattended-notice-import` is history only.

## Method (same as ibkr)

- **Spec first.** No code without an OpenSpec change that Florent approved. A
  spec has 1 800 words or fewer. It describes visible behavior and error codes,
  never internal mechanisms. Do not specify recovery tools, lab tools, release
  process or docs layout. When reality is different from the spec, stop and
  report. Do not change the spec silently.
- **No bead before the spec.** After approval: one epic for the change and one
  bead per task. Each bead gives the spec path, requirement, scenario,
  acceptance command and files to touch.
- **One bead = one fresh session.** Claim, implement, prove, close, stop. The
  implementation beads may proceed offline before an upstream source or live
  acceptance gate is available. Keep those gates separate and do not start the
  next bead in the same session. Budget about 150 tool calls; above that, stop
  and report.
- **Done = the scenario replayed for real.** Put the command and its output in
  the closing note. Green unit tests are not done. Keep review evidence in the
  owning bead. A decision bead never delivers code.
- **Tests:** offline pytest, one real anonymized notice for each operation type
  and each error code. No synthetic protocol proofs. No tests for docs or CI.
- **Review:** follow the invoked implementation skill. When it requires
  `code-review`, run independent Standards and Spec subagents before the PR.
  Fix actionable findings and record both reports in the owning bead. Apply
  `security-review` when its trigger matches the change. This pre-PR review
  does not replace Pullfrog's review of the final PR head.
- **Git:** one branch and one PR per bead. Merge when CI is green and Pullfrog
  finished its review of the head commit, or on Florent's explicit go. A PR that
  changes only `openspec/`, `docs/` or `*.md` needs CI green only. Open the PR
  yourself, then run `~/.agents/bin/pr-ship <n> --repo
  flowcool/ghostfolio-boursedirect-sync` in one call, never a `sleep` loop: it
  waits, merges on `ready` and hands back any other verdict (exit 2: re-run).
  Fix or answer each actionable comment, then re-run. Run the PR lifecycle in
  the main session. Publication and live-write authority remain separate.
- **Operation beads.** A bead that acts on real state (Ghostfolio write, NAS)
  runs only from an `Operation plan:` in its design that Florent validated. In
  this repository, the only ceremony is the first real Ghostfolio write. A
  failed or uncertain step: record it and stop.
- **Ask Florent only for:** a Bourse Direct fact missing from the spec, a
  Ghostfolio write, a scope change. One question at a time, in plain French,
  with your recommendation.

## Budgets

- The application package has 2 500 lines or fewer across all its Python files.
  This replaces the main-file limit. Tests and packaging metadata are excluded.
- Reuse the existing infrastructure lab. A dedicated BD test container is
  permitted in principle (Florent, 2026-10-22). Its exact target, commands and
  writes use the permanent lab authority below. Keep lab tooling in infra.
  No separate lab or new compose file without approval.
- Build the candidate image once. Require empty and golden lab scenarios to
  pass on its digest. Publish that exact image without rebuilding. No mandatory
  RC channel. Reuse applicable IBKR checks. Publication and production writes
  need Florent's go.
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

The target is the installed Python package `ghostfolio_boursedirect_sync`.
Docker runs `python -m ghostfolio_boursedirect_sync`. Use typed module-level
functions. Frozen dataclasses and typed dictionaries describe data only.
Application code passes strict mypy and Ruff; tests keep relaxed typing.
Follow the latest stable Python, Node and base-image releases without version
ceilings. Renovate proposes updates. Keep image digests and Action SHAs for
reproducible checks. Integrate updates after compatibility tests, security scans
and the required review. Keep Python CI and the native image on the same release.
Keep `Decimal` for money and position decisions when adapting ibkr code.
See
[python conventions](.claude/rules/python-conventions.md),
[security rules](.claude/rules/security.md). The legacy code stays in place
until the rebuild replaces it.

## Shared Ghostfolio labs

Use the permanent lab authority in the global working agreement and the
canonical Infra lab runbook. It covers both labs, including test writes,
configuration and resets. Keep reservations, separate credentials, retained
proof, stop on uncertainty without automatic resend, and final stop verification.
Broker access, production, publication and removal of containers or proof
retain separate authority. This scope overrides generic write-approval rules
for these two labs only.

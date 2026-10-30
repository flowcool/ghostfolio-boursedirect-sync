# Bourse Direct → Ghostfolio — agent guide

## Product

Community Docker connector. It imports Bourse Direct (PEA, PEA-PME) operations
into Ghostfolio. It is Docker-first. Every setting comes from ENV. It runs
unattended with `docker compose up -d`. The target contract is the sibling fork
`../ghostfolio-ibkr-sync`: `CRON`, `DRY_RUN` on by default, `APPRISE_URLS`,
additive and deduplicated import. Before you add a mechanism, cite the line of
ibkr or degiro that does the same thing. If no sibling line exists, stop and ask, except for BD adaptations already
approved in the current spec.

Keep public files free of personal hosts, paths, account identifiers and private
work-tracker IDs.

## Product scope (v1, released)

- The v1 adopts the complete applicable common core from ibkr v3.0.0
  (Florent, 2026-10-22). Follow its modules and typed functions; classes describe
  data. Before coding, read the
  [archived design](openspec/changes/archive/2026-10-30-pdf-notice-importer/design.md)
  for the source commit, coverage and BD adaptations. Cover every applicable
  implemented runtime and release requirement. Review later source updates separately. No shared library or
  automatic core projection.
  The previous work stays in Git (tag `legacy-wip`). v0.1.1 is a preview-only
  legacy release.
- Collection is outside this project. `billcollector-recipes` owns the Bourse
  Direct recipe, `BillCollector` owns the engine, the broker login and the vault
  access, and Infra deploys the collector and the Paperless delivery.
- This project owns the importer. It reads the PDF notices ("avis d'opéré")
  from Paperless, read only.
- The connector imports only what Ghostfolio shows exactly: buy, sell, coupon.
  It stops on a security for each operation that changes the number of shares.
  It adds actually charged TTF to one BUY in the same source account, notice,
  date and ISIN. Ambiguity suspends affected BUYs. It ignores custody fees
  and shows a message. Follow the current spec for fee-only corrections.
- The current behavior contract is
  [notice-import](openspec/specs/notice-import/spec.md). Completed changes under
  `openspec/changes/archive/` are history only.

## Project boundaries (Florent 2026-10-30)

Each scope has one owner agent. Work only in the repositories and runtime of
your own project. This project: `ghostfolio-boursedirect-sync`.

| Beads `project` | Agent | Owns |
| --- | --- | --- |
| `infra` | Claude, `~/claude_project/infra` | Production deployment (Komodo, GitOps `flowcool/mylittlemess`), image and catalog pins, schedules, collector task configuration, hosts and NAS outside the labs, Paperless configuration and permissions, SOPS secrets, backup, monitoring. |
| `BillCollector` | Codex | The engine only (`flowcool/BillCollector`): generic actions, scheduler, vault and TOTP, throttles, delivery, recipe schema, engine contract, upstream engine contributions. |
| `billcollector-recipes` | Codex | Every provider recipe end to end (`flowcool/billcollector-recipes`): portal exploration, selectors, history window, qualification on the exact engine revision, catalog release, upstream recipe contributions. |
| `ghostfolio-ibkr-sync`, `ghostfolio-degiro-sync`, `ghostfolio-boursedirect-sync` | Codex | Connector code, spec, lab tests, PRs and releases. The Ghostfolio financial operation, under Florent's GO. |

- **Routing.** For a need in another scope, search the open issues of the owner
  first. If no issue covers it, create one with
  `--metadata '{"project":"<owner>"}'`, the evidence, the exact need and its
  acceptance. Link it `related` to your issue. Never edit, deploy or test the
  code or runtime of another project.
- **Usual routes.** Portal, selector or history window: `billcollector-recipes`.
  Missing engine action, throttle, vault or delivery defect: `BillCollector`.
  Deployment, pin, schedule, task configuration, Komodo stack, NAS file,
  Paperless workflow or permission: `infra`. Importer behavior: the connector.
- **Release boundary.** A development project stops at a qualified release: an
  immutable image digest or catalog tag, with its proof. Infra deploys it.
- **Labs: free use on agentvm.** Create, configure, reset, restart, redeploy and
  scratch lab stacks under `stacks/a/` (Komodo server `a`). To add your own
  lab, open a `flowcool/mylittlemess` PR limited to `stacks/a/<lab>/` and its
  `komodo/sync.toml` entry; merge it on green CI. Separate authority remains for
  production, a login to a real broker or portal (Florent GO per provider),
  production secrets in a lab, and removal of proof. Reserve a shared lab and
  stop it after use (Infra runbook `docs/runbooks/ghostfolio-lab.md`).
- **Lab gate before merge.** Test the PR image in the lab before merge when the
  PR changes financial logic, deduplication or activity identity, Ghostfolio
  authentication, transport or writes, the state or journal format, a recipe,
  or a major dependency or base image. Connectors run the empty and golden
  Ghostfolio labs. Recipes and the engine run an isolated collector lab with
  synthetic fixtures. Other PRs need CI only.
- **Lab gate at release.** Every release passes the same lab scenarios on its
  exact digest. Promote that digest without a rebuild. Reuse the pre-merge proof
  when the digest is identical.

## Method (same as ibkr)

- **Spec first.** No code without an OpenSpec change that Florent approved. A
  spec has 1 800 words or fewer. It describes visible behavior and error codes,
  never internal mechanisms. Do not specify recovery tools, lab tools, release
  process or docs layout. When reality is different from the spec, stop and
  report. Do not change the spec silently.
- **OpenSpec to work items.** After approval: one parent item for the change
  and one implementation item that lists all tasks (spec path, requirement,
  scenario, acceptance command, files to touch per task). `tasks.md` tracks the
  tasks; a task ticks its box in a commit, not in a new item. A task that needs
  an operation or a decision keeps its own item.
- **Continue authorized work.** Continue through the approved implementation,
  review and release preparation in the same session. Reuse the owning item and
  valid evidence. Split work only for an independent deliverable, a repository
  boundary or a new authorization. Hand off only with a concrete reason.
- **Done = the scenario replayed for real.** Put the command and its output in
  the closing note. Green unit tests alone are not done. Apply the
  rule below for an error case absent from the complete available archive.
  Keep review evidence in the owning bead.
  A decision bead never delivers code.
- **Tests:** offline pytest, one real anonymized notice for each operation type
  and each observed error code. After the complete available archive is checked,
  an absent error case does not block delivery. Keep its logged error, exit code
  and write protection. Verify these with explicit derived-data regressions;
  never claim a real financial observation or alter an original PDF.
  No synthetic protocol proofs. No tests for docs or CI.
- **Review:** Pullfrog is the only reviewer. No pre-PR review subagents.
  Apply `security-review` when its trigger matches the change.
  Before every code merge, wait for Pullfrog's complete review of the latest
  head. Read its general review body and all comment threads. Address each
  remark, including cleanup outside inline threads. Record the outcome and
  reviewed SHA. A green status alone is insufficient. After a new commit,
  repeat this review gate before running `pr-ship`.
- **Git:** one branch and one PR per change. Sub-items (beads), steps and review
  fixes are commits in that PR; never open separate or stacked PRs for them.
  Merge when CI is green and Pullfrog
  finished its review of the head commit, or on Florent's explicit go. A PR that
  changes only `openspec/`, `docs/` or `*.md` runs only local-link and whitespace checks.
  Do not run application tests, image builds or scans, dependency review or CodeQL
  for such a PR. Code PRs retain those checks and the current CodeQL error and
  medium-or-higher security thresholds. The required `analyze` job enforces them. Open the PR
  yourself, then run `~/.agents/bin/pr-ship <n> --repo
  flowcool/ghostfolio-boursedirect-sync` in one call, never a `sleep` loop: it
  waits, merges on `ready` and hands back any other verdict (exit 2: re-run).
  Fix or answer each actionable comment, then re-run. Run the PR lifecycle in
  the main session. Publication and live-write authority remain separate.
- **Operation beads.** A bead that acts on real state (production Ghostfolio
  write) runs only from an `Operation plan:` in its design that Florent validated. In
  this repository, the production gate is the first production Ghostfolio write. A
  failed or uncertain step: record it and stop.
  Production host or NAS files for this service belong to Infra.
- **Ask Florent only for:** a Bourse Direct fact missing from the spec, a
  production Ghostfolio write, a scope change. One question at a time, in plain French,
  with your recommendation.

## Budgets

- Application code has no line-count budget. Reuse the applicable IBKR module
  boundaries and typed functions. Keep review, reconciliation, transport and
  orchestration in their own modules; do not compress them into one file.
- Use the labs under the Project boundaries rules above. A dedicated BD test
  container is allowed as an agentvm lab.
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
- Ghostfolio: `DRY_RUN=1` by default. Add new activities; never delete. The only
  update is the approved BUY fee-only correction in the current spec. Preserve
  every other field and logical identity. Confirm exact readback; stop on
  uncertainty without resend. Production writes need Florent's go. Shared labs
  use their permanent authority below.
- Money: `Decimal`, exact dates, EUR. An unknown operation is skipped and
  reported; the other operations continue.

## Durable work state

- For the proposed IBKR v4 behavior, read
  [operator-actions-and-reconciliation](openspec/changes/operator-actions-and-reconciliation/proposal.md).
  It awaits contract approval; the current published contract remains above.
- Beads project metadata: `project=ghostfolio-boursedirect-sync`.
- Rebuild epic: "v1 rebuild (option B)". Include completed work with
  `bd list --metadata-field project=ghostfolio-boursedirect-sync --type epic --all`.
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
[security rules](.claude/rules/security.md). The legacy implementation remains
in Git at `legacy-wip`.

## Shared Ghostfolio labs

Use the permanent lab authority in the global working agreement and the
canonical Infra lab runbook. It covers both labs, including test writes,
configuration and resets. Keep reservations, separate credentials, retained
proof, stop on uncertainty without automatic resend, and final stop verification.
Broker access, production, publication and removal of containers or proof
retain separate authority. This scope overrides generic write-approval rules
for these two labs only.

# Bourse Direct → Ghostfolio — agent guide

## Product

Community Docker connector that imports Bourse Direct (PEA, PEA-PME) activities
into Ghostfolio. Docker-first, every setting through ENV, runs unattended with
`docker compose up -d`. Target contract = the sibling forks
`../ghostfolio-ibkr-sync` and `../ghostfolio-degiro-sync`: `CRON`, `DRY_RUN`
default on, `APPRISE_URLS`, additive deduplicated import. Read sibling code
before designing any mechanism they already have.

v0.1.1 is a preview-only legacy release. v0.2 is a rebuild driven by the active
OpenSpec change under `openspec/changes/`. That change is the only spec.
`docs/design/`, `docs/plans/`, `docs/reviews/` and `docs/archive/` are history:
do not read them unless the active change cites them.

## Working mode: fast-track

This mode replaces the global per-step ceremony. Safety invariants below still apply.

- **Spec first.** No code without an OpenSpec change approved by Florent. When
  reality contradicts the spec (page differs, field missing), stop and report.
  Never invent Bourse Direct behavior; never amend the spec silently.
- **OpenSpec → Beads.** After approval, one epic labelled `openspec:<change>`
  and one bead per task. Each bead is self-contained: spec path, requirement,
  scenario, acceptance command, files to touch. Closing a bead ticks its task in
  `tasks.md`; archive the change when every task bead is closed, before the
  `Release` bead.
- **Release.** A change that touches shipped code ends with a `Release` bead
  after its last task: archive, replay on `main`, semver tag on Florent's go,
  image pullable; the epic closes only after it (global runbook, release gate).
- **One bead = one fresh session.** Claim the bead, implement, prove, close,
  stop. Do not start the next bead. Do not arm `autonomous-run` or a goal across
  beads. Budget about 150 tool calls; above that, stop and report the state.
- **Done = the bead's scenario replayed for real** (command + observed output in
  the closing note). Green unit tests are not done.
- **Tests:** offline pytest for parsing and mapping, on anonymized real
  fixtures. No tests for lab tooling, docs or CI. No full-suite rerun for prose edits.
- **Beads:** one closing note with evidence per bead; no per-step `bd-finding`.
  Out-of-scope discovery → one new bead `discovered-from` the current one.
- **Git:** one branch and one PR per bead. Merge only when CI is green AND
  CodeRabbit has finished its review of the head commit, or on Florent's
  explicit go. A PR that changes only `openspec/`, `docs/` or `*.md` needs CI
  green only. Wait with `~/.agents/bin/pr-gate <n> --repo
  flowcool/ghostfolio-boursedirect-sync` (in Codex, inside one exec cell, see the
  global runbook), never a `sleep` loop. Then fix or answer each actionable
  CodeRabbit comment; a pushed fix needs a finished review again. Still open
  findings after a second round, or timeout: leave the PR open and the bead
  `in_progress`, stop and report to Florent.
- **Docs:** README and user docs required by the spec only. No new plan,
  review or contract files.
- **Subagents:** only on Florent's explicit request, except the PR lifecycle:
  after the code is proven and pushed, one cheaper subagent without history
  creates the PR, waits with `pr-gate`, answers minor comments, resolves threads,
  writes the bead close note and merges when allowed. It never edits code and
  returns only the verdict and the threads that need a code change (global
  Delegation rule).
  In Claude Code the implementing agent runs this lifecycle itself, without a
  subagent: a nested PR subagent stops right after creating the PR.
- **Ask Florent only for:** a Bourse Direct fact missing from the spec, a real
  broker login, a Ghostfolio write outside the lab, a scope change. One question
  at a time, in plain French, with your recommended answer.
- **Decision beads.** Work only the bead's numbered decision list, inside its
  authorization envelope. Start each question with `Décision n/N`; anything
  else (new question, spec, contract or code change, action outside the
  envelope) is `HORS CHEMIN`: note it in the bead and stop (global runbook,
  decision beads).
- **Operation beads.** A bead labelled `operation` acts on real state (host, container,
  Ghostfolio, Bourse Direct, journal, shared volume).
  Execute it only from the `Operation plan:` in its design, validated once by
  Florent: numbered phases, each with exact command, target, expected proof,
  authorization envelope, stop conditions and rollback. No plan: stop; an
  offline bead labelled `operation-plan` writes it. Live steps run repository
  code only, versioned and tested, never a `tmp/` script; a missing tool is a
  code bead first. A failed or uncertain step is `HORS CHEMIN`: record the
  evidence in the bead and stop (global runbook,
  operation beads).

## Safety invariants

- Bourse Direct locks the account after three failed logins: one login attempt
  per run at most. On failure or uncertain outcome, stop, record it, never retry
  automatically. A scheduled run refuses while a failed attempt is unresolved.
- Secrets come from ENV only (Bitwarden CLI `BW_*`, Ghostfolio token). Never in
  Git, logs, Beads, tests or reports.
- Personal data stays off Git: `inputs/`, `outputs/`, `state/`, `tmp/`, `audit/`.
- Ghostfolio: `DRY_RUN=1` by default; writes are additive only (never update or
  delete); test writes go to a lab instance; production writes need Florent's go.
- Money: `Decimal`, exact dates, EUR. An unknown operation is skipped and
  reported; the other operations continue.

## Durable work state

- v0.2 execution: epic `infra-q0jz`, one child bead per task of
  `openspec/changes/unattended-notice-import/tasks.md`, chained in task order.
  Task 6.1 (`infra-q0jz.13`) owns final real-import validation after development.
  Spec originally approved and merged in PR #72 (`infra-2fji`).
- Audit that set this mode: `infra-uze3` (closed).

## Code

Functional Python, no classes, no type hints:
[python conventions](.claude/rules/python-conventions.md). Real broker access and
the acquisition lab: [connection procedure](docs/operations/source-connection.md).

# ghostfolio-boursedirect-sync

Read [CLAUDE.md](CLAUDE.md), then the scoped Beads issue and the owning contract
selected through the [design index](docs/design/index.md).
Global working agreement applies. Beads owns live work state.

## Architecture and validation

- `boursedirect_to_ghostfolio.py` is a functional mono-file document importer
  with offline inspection, note-matching, internal financial conversion and stable
  ledger identities
  and local `prepare`/`review` artifacts, exact wire bytes, uncertainty journals
  and conservative chronological holdings checks. Qualified `apply` requires
  separately pinned operator records and source replay; it defaults to preview.
  No classes or type hints; follow `.claude/rules/python-conventions.md`,
  `.claude/rules/security.md` and `.claude/rules/delegation.md` (fleet delegation,
  model right-sizing, infra handoff, convergence discipline).
- Only local saved HTML is read; scripts, links and assets are never fetched.
  Optional Ghostfolio `snapshot` uses one exact-allowlisted HTTPS GET only;
  session credentials come from environment, never an authentication POST.
  Qualified application adds fixed single-event import POSTs under separate
  external permission, with complete pre-request private archive and no retries.
- Decimal controls, direct-child column parsing and blank slots are mandatory.
  Unknown operations block the affected period. `prepare` remains not import-ready
  until remote adoption and isolated API/date/number gates are proved.
- Runtime dependencies: `requirements.txt`; development: `requirements-dev.txt`.
- Required logic verification: `.venv/bin/python -m pytest -q`. Tests use synthetic
  inputs and forbid sockets. Never point tests at real Ghostfolio or shared state.
- Preserve verification results in keyed YAML with command, exit code and hashes
  of the relevant code/runtime inputs. Reuse matching successful evidence across
  sessions; run only new or affected checks and checks needed to resolve failures.
  `bash scripts/verify-local.sh` is the full documentation, Python, collector and
  whitespace gate when reusable evidence is unavailable. Inspect each required
  exit code before committing, closing work or making a dependent mutation.
- Real inputs, configuration, output and journals are ignored; never commit
  personal account data. Logs contain codes and counts only.
- Chromium: use the latest available stable Chrome for Testing for new runtime
  work, resolve it once, and record the exact version, download hash and image ID
  used by the qualification run. When an old image is unavailable, qualify the
  current release and continue; historical pins describe historical evidence.
- This repository owns vault/CLI adapters and acquisition control code. Infra
  supplies verified access facts and host/secret/network wiring. Reuse existing
  CLI artifacts and provisioning mechanisms before adding another delivery layer.

## Pull request workflow

- Florent's external workflow owns PR review and CodeRabbit triggers; do not
  trigger the bot or substitute agent review for the required external review.
  This agent owns merges and releases under Florent's authorization. Preserve
  merge ancestry, required checks and explicit security/release gates.
- Do not spawn PR-review subagents. Run local verification and record exact CI
  evidence; CodeRabbit supplies PR review externally. Historical independent
  reviews remain valid evidence for the exact heads they inspected.
- Future design reviews follow the reviewer and authorization policy in
  `.claude/rules/delegation.md`. Historical Astra verdicts remain valid for their
  exact reviewed scope; design review is separate from PR review.
- No Ghostfolio writes are authorized. Public v0 publication is authorized;
  private documents, runtime evidence and credentials must remain off Git.

## Autonomous technical ownership

Florent authorizes the agent to complete the agreed project scope autonomously,
including technical reviews and bounded infrastructure delegation under their
existing explicit authority. Follow `.claude/rules/delegation.md` for reviewer
and model selection. Resolve technical choices, review findings and
recoverable laboratory failures without repeating permission requests. Carry
existing approvals across sessions through their Beads evidence. Ask Florent
only for genuinely new authority or indispensable information. Production,
financial writes, publication/push and destructive-operation gates still apply.

## Durable work state

- Root epic: `infra-4g8u`, metadata `project=ghostfolio-boursedirect-sync`.
- Source-acceptance owner: `infra-4g8u.4`; offline-probe owner: `infra-4g8u.7`.
- Design: [probe contract](docs/design/offline-probe.md),
  [source matrix](docs/design/source-contract.yaml),
  [preparation contract](docs/design/offline-preparation.md).
- Independent review: [Astra report](docs/reviews/2026-10-08-manual-document-import-astra.md).

Interactive broker source acquisition is authorized under the
[acquisition amendment](docs/design/online-source-inspection.md); unattended
scraping remains outside the design. No production writes or pushes without
applicable explicit authorization. Later financial/API behavior must pass the gates.

## Agent skills

For engineering-skill workflows, read the shared Beads tracker, triage-label,
and domain-doc rules in `docs/agents/`:
[`issue-tracker.md`](docs/agents/issue-tracker.md),
[`triage-labels.md`](docs/agents/triage-labels.md), and
[`domain.md`](docs/agents/domain.md).

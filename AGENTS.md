# ghostfolio-boursedirect-sync

Read [CLAUDE.md](CLAUDE.md), [FINDINGS.md](FINDINGS.md), and the
[reviewed plan](docs/plans/2026-10-08-manual-document-import.md).
Global working agreement applies. Beads owns live work state.

## Architecture and validation

- `boursedirect_to_ghostfolio.py` is a functional mono-file offline inspection
  tool with note-matching, internal financial conversion, stable ledger identities
  and local `prepare` review artifacts.
  No classes or type hints; follow `.claude/rules/python-conventions.md`
  and `.claude/rules/security.md`.
- Only local saved HTML is read; scripts, links and assets are never fetched.
- Decimal controls, direct-child column parsing and blank slots are mandatory.
  Unknown operations block the affected period. `prepare` remains not import-ready
  until remote adoption and isolated API/date/number gates are proved.
- Runtime dependencies: `requirements.txt`; development: `requirements-dev.txt`.
- Required logic verification: `.venv/bin/python -m pytest -q`. Tests use synthetic
  inputs and forbid sockets. Never point tests at real Ghostfolio or shared state.
- Real inputs, configuration, output and journals are ignored; never commit
  personal account data. Logs contain codes and counts only.

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

# CLAUDE.md — ghostfolio-boursedirect-sync

The manual-document importer design includes an offline statement-inspection probe.
Complete activity-import viability requires saved source evidence; synthetic parser
tests cannot establish it. See the [probe contract](docs/design/offline-probe.md).

Start here: **[`FINDINGS.md`](FINDINGS.md)**, then the
[manual document import proposal](docs/plans/2026-10-08-manual-document-import.md).
Latest evidence supersedes earlier pending checkpoints. No CSV/Excel export is confirmed.
Read the numbered approval and source gates before any implementation.

## Candidate shape (conditional on the reviewed source gates)

| Fact | Value |
|---|---|
| Data source | Candidate: manually saved monthly HTML statements plus contract-note enrichment; no broker scraping or automated login |
| Existing blocks | picsou `bourse-direct-auth`, `wadael/BourDirConnect` — **positions only**, reference material |
| Auth | Manual broker session only; importer uses no broker credentials. TOTP used; SMS/TOTP both enabled; three incorrect passwords block the account |
| Ghostfolio core | Selective audited helper reuse; replace IBKR identity/orchestration, enforce explicit mapping, exclude historical cash overwrite |

## Conventions (inherited from IBKR)

- `.claude/rules/python-conventions.md`, `.claude/rules/security.md`.

## Git

Commit authorized local changes atomically after verification. Push only on
Florent's explicit request. Never version private inputs, outputs or configuration.

## Durable work state

- Root epic: `infra-4g8u`, metadata `project=ghostfolio-boursedirect-sync`; independent sibling of IBKR epic `infra-8tt`.
- Plan: [manual document import](docs/plans/2026-10-08-manual-document-import.md).
- Independent review: [Astra report](docs/reviews/2026-10-08-manual-document-import-astra.md).
- Review owner: `infra-4g8u.2` (Astra); user scope approval owner: `infra-4g8u.3`; source feasibility owner: `infra-4g8u.4`.
- Offline-probe owner: `infra-4g8u.7`; source matrix: [source-contract.yaml](docs/design/source-contract.yaml).
- Beads owns current status and dependency gates; do not duplicate them in repository guidance.

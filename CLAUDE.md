# CLAUDE.md — ghostfolio-boursedirect-sync

The approved strict document-import scope includes offline statement/note inspection,
internal EUR trade conversion, stable ledger identity and private `prepare` review plans.
See [preparation](docs/design/offline-preparation.md); remote adoption and API delivery
remain gates, and no apply command exists.
Pure [adoption helpers](docs/design/offline-adoption.md) operate on saved snapshots.
The [remote schema contract](docs/design/remote-schema-compatibility.md) distinguishes
legitimate nulls from missing evidence and quarantines unsupported financial context.
The [offline review CLI](docs/design/offline-review-cli.md) binds saved snapshot,
adoption/history evidence and exact new-activity wire bytes in a private artifact.
The [offline diagnosis CLI](docs/design/offline-diagnosis.md) reports saved legacy
candidates and conflicts without adoption/history assertions or a wire artifact.
Pure [wire helpers](docs/design/offline-wire.md) produce exact numeric UTC review
bytes and compare POST acceptance; they do not send requests or grant readiness.
Local [write intent helpers](docs/design/write-intents.md) persist uncertainty
before a future dispatch; empty readback cannot clear the account fence.
The [isolated API evidence](docs/design/ghostfolio-api-lab.md) covers basic pinned
DTO/date/numeric/account behavior, not complete uncertain-write recovery or a
production destination. Always preserve those readiness boundaries.
The [recovery bench](docs/design/ghostfolio-recovery-lab.md) proves isolated
delayed/lost/partial-write fencing and bounded lab cancellation; production
quiescence and the remaining financial/security gates are separate obligations.
Complete activity-import viability requires saved source evidence; synthetic parser
tests cannot establish it. See the [probe contract](docs/design/offline-probe.md).

Start here: **[`FINDINGS.md`](FINDINGS.md)**, then the
[manual document import proposal](docs/plans/2026-10-08-manual-document-import.md).
Latest evidence supersedes earlier pending checkpoints. No CSV/Excel export is confirmed.
Read the numbered approval and source gates before any implementation.
Florent authorized interactive online source collection; see the
[acquisition amendment](docs/design/online-source-inspection.md). The original
manual-only proposal remains a historical reference.

## Candidate shape (conditional on the reviewed source gates)

| Fact | Value |
|---|---|
| Data source | Offline importer consumes monthly HTML plus contract-note enrichment; interactive online G1 collection is explicitly authorized under the acquisition amendment |
| Existing blocks | picsou `bourse-direct-auth`, `wadael/BourDirConnect` — **positions only**, reference material |
| Auth | User-assisted or explicitly authorized interactive session; secrets from os.environ only. TOTP used; SMS/TOTP both enabled; three incorrect passwords block the account |
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

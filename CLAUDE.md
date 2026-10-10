# CLAUDE.md — ghostfolio-boursedirect-sync

The document importer inspects saved HTML, prepares local review artifacts and
retains durable uncertainty before qualified application. Remote history,
financial/API behavior and production execution remain separate evidence gates.

Before changing importer, acquisition, review or application behavior, use the
[design index](docs/design/index.md) to select and read the owning contract.
Beads owns current acceptance evidence and dependency gates.

For source feasibility or provenance, consult [`FINDINGS.md`](FINDINGS.md).
For the original scope rationale or numbered approval gates, consult the
[manual document import proposal](docs/plans/2026-10-08-manual-document-import.md).
Current contracts and recorded acceptance evidence govern later amendments;
historical pending checkpoints are not current status. No CSV/Excel export is confirmed.
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

- `.claude/rules/python-conventions.md`, `.claude/rules/security.md`,
  `.claude/rules/delegation.md`.

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

## Agent skills

### Issue tracker

Work is tracked in the shared Beads tracker, scoped with
`project=ghostfolio-boursedirect-sync`. See `docs/agents/issue-tracker.md`.

### Triage labels

The default canonical triage labels are used with Beads. See
`docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See
`docs/agents/domain.md`.

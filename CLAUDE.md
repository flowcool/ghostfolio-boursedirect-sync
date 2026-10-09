# CLAUDE.md — ghostfolio-boursedirect-sync

The approved strict document-import scope includes offline statement/note inspection,
internal EUR trade conversion, stable ledger identity and private `prepare` review plans.
See [preparation](docs/design/offline-preparation.md); remote adoption and API delivery
remain gates. The [operator application](docs/design/operator-application.md)
provides default offline apply preview and optional private exact JSON proposals;
execution remains explicitly gated.
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
The [frozen review boundary](docs/design/frozen-review-validation.md) recomputes
complete typed reports; `check-review` exposes it as a read-only operator check.
An external report hash proves bytes, not approval or source authenticity.
The [frozen lab sequence](docs/design/frozen-lab-sequence.md) preflights all
single-row bodies and chains confirmed events with durable observer evidence;
it remains a trusted owned fixture path, without production transport or authority.
The [bounded HTTPS adapter](docs/design/https-request-adapter.md) supports fixed
GET and canonical one-event POST via environment session bearer; its factory does
not connect. Qualified `apply` invokes it only after complete source/report/
declaration preflight. Its existence is not permission.
The [single-event lab core](docs/design/single-event-lab-dispatch.md) holds both
locks through trusted injected GET/POST/readback and exact transition confirmation;
its protocol is shared by the separately qualified application controller and
does not itself grant financial readiness or production authority.
The [offline verify command](docs/design/offline-intent-verification.md) observes
retained journals and saved snapshots without resolution, fence mutation or
capture-freshness claims; recorded settlement remains distinct from row presence.
The [offline compensation candidate command](docs/design/offline-compensation-candidates.md)
selects exact recorded-ID associations only; it establishes neither creation
provenance nor deletion authority and sends no requests.
The [isolated API evidence](docs/design/ghostfolio-api-lab.md) covers basic pinned
DTO/date/numeric/account behavior, not complete uncertain-write recovery or a
production destination. Always preserve those readiness boundaries.
The [recovery bench](docs/design/ghostfolio-recovery-lab.md) proves isolated
delayed/lost/partial-write fencing and bounded lab cancellation; production
quiescence and the remaining financial/security gates are separate obligations.
The [3.81.0 parity bench](docs/design/ghostfolio-381-parity.md) repeats selected
API and uncertain-write scenarios at the observed destination version; it remains
isolated evidence, not production authorization or complete delivery acceptance.
The [synthetic import lifecycle](docs/design/synthetic-import-lifecycle.md) joins
saved document preparation to exact lab acceptance/readback and a zero-new second
review. Qualified application is implemented separately; real legacy history
and external run permission remain gates.
The opt-in [portable disposable runner](docs/design/disposable-acceptance.md)
reproduces that fixture lifecycle using newly owned local Docker resources only;
ordinary pytest/CI never starts it and no production endpoint option exists.
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

Pure current-config preparation replay: [contract](docs/design/preparation-source-replay.md).

Qualified application and complete private run archive: [operator workflow](docs/design/qualified-application.md).

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

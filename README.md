# ghostfolio-boursedirect-sync

Offline preparation and reconciliation tools for a Bourse Direct → Ghostfolio
document importer. The implemented `inspect` command reads monthly statement
HTML, preserves aligned ledger slots and checks cash controls with Decimal.
Optional `--notes` inputs inspect daily contract notes and match trades exactly.
Inspection does not submit activities or contact either service. A pure internal
[conversion helper](docs/design/internal-trade-conversion.md) validates matched
EUR trades and explicit mappings; identity, adoption and API delivery are separate
gates.

Read [FINDINGS.md](FINDINGS.md), the [reviewed plan](docs/plans/2026-10-08-manual-document-import.md)
and the [probe contract](docs/design/offline-probe.md). Beads epic `infra-4g8u`
owns approval, source acceptance and delivery gates. Parser tests on synthetic
documents do not prove complete historical import viability.

## Run locally

Python 3.13 is the verified bench interpreter. Install runtime dependencies for
inspection, or development dependencies to run tests:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python boursedirect_to_ghostfolio.py inspect \
  tests/fixtures/statement-synthetic.html --input-root tests/fixtures \
  --max-bytes 100000 --max-depth 32
```

Pull requests run versioned `tests/` on Python3.13 in GitHub Actions with read-only
repository permission and pinned action commits. Local full discovery may also
include ignored private exploration tests; those are not part of public CI.

The last command exits **2**, with a safe JSON summary: one buy, two sells, cash
controls reconciled, import readiness blocked. Exit **1** means unreadable or
inconsistent input. Input size/depth budgets are explicit; the example budgets
are for the synthetic bench, not established broker-document limits.

Save original statement and contract-note HTML locally under ignored `inputs/`
with private permissions. Do not put account documents in Git or Beads. PDFs,
pasted plain text and an authenticated URL cannot replace the saved HTML inputs.
Saved note layout and exact enrichment are evidenced for one month; explicit EUR
and security mappings are evidenced for that private sample. Complete historical
coverage and legacy adoption remain gates. Florent approved a
strict BUY/SELL first version with unsupported periods blocked and existing
Ghostfolio acquisitions used for adoption; that importer is not delivered yet.
Florent has also authorized agent-led interactive collection through a private
browser; its [acquisition amendment](docs/design/online-source-inspection.md)
defines authentication, document privacy and infrastructure boundaries.

The scaffold license is retained verbatim from the IBKR sibling; this probe uses
original code and does not copy sibling functions.

For a saved statement and its daily notes:

```sh
.venv/bin/python boursedirect_to_ghostfolio.py inspect \
  inputs/statement.html --input-root inputs --max-bytes 1048576 --max-depth 32 \
  --notes inputs/note-day-a.html inputs/note-day-b.html
```

The JSON contains matching counts and blocker codes. Account mismatches and
invalid notes fail with exit 1; missing, extra or ambiguous matches block with
exit 2. Exact matching never infers currency or silently discards duplicate trades.
Even complete matching leaves `import_ready=false`: there is no activity export
or Ghostfolio write command. The limits above are example local budgets.


## Prepare an offline review plan

`prepare` validates all supplied statements and daily notes using explicit keyed
YAML configuration. Run from this repository so private artifacts remain covered
by `.gitignore`. The entirely synthetic bench example is runnable:

```sh
.venv/bin/python boursedirect_to_ghostfolio.py prepare \
  --config tests/fixtures/import-config-synthetic.yaml --input-root tests/fixtures \
  --max-bytes 100000 --max-depth 32
```

For real inputs, copy the example to ignored `inputs/import-config.yaml` and
replace synthetic account bindings, paths, ISIN mappings and evidence. Generate
one UUIDv4 account key, persist it, and do not rotate it between runs. Validate
execution and target-symbol currencies explicitly. Do not place tokens/passwords
in this configuration. Any unsupported operation blocks its entire period.

The command exits 2 and writes a private internal review artifact under ignored
`outputs/` plus keyed source-revision state under `state/`, both with private
permissions. Repeating equivalent inputs preserves identities; source corrections
and account-binding changes require review. Target/account locks prevent concurrent
local preparation. These artifacts contain private financial details and are
**not Ghostfolio API payloads**. They remain `import_ready=false` because existing
actual activity adoption, historical holdings and destination validation remain
unverified. The isolated API/date/number and recovery evidence describes synthetic
laboratories only.
No `apply` command exists. See the [preparation contract](docs/design/offline-preparation.md).

Pure offline [adoption helpers](docs/design/offline-adoption.md) validate complete
saved Ghostfolio snapshots and propose explicit reconciliation of existing manual
activities. The offline `review` CLI joins these helpers without contacting Ghostfolio.
The [pinned disposable API bench](docs/design/ghostfolio-api-lab.md) establishes
basic numeric/date/marker behavior, account namespace requirements and bounded
activity deletion. It also demonstrates that HTTP201 can create nothing and that
bare date strings shift under the server timezone. Full uncertain-write recovery,
actual historical holdings and destination validation remain gates;
these observations do not make preparation artifacts import-ready.

Pure [wire review](docs/design/offline-wire.md) and
[durable intent](docs/design/write-intents.md) helpers now enforce exact numeric
bytes and uncertainty fences. The [recovery bench](docs/design/ghostfolio-recovery-lab.md)
demonstrates delayed/lost/partial outcomes in an owned disposable instance.
[Chronological holdings](docs/design/chronological-holdings.md) checks saved
history conservatively. Private actual destination snapshots were captured with
read-only GET requests; source mappings are evidenced for the sample, while legacy
dates, one fee discrepancy, explicit adoption and complete acquisition history
remain blocking. No production activity was written. See [actual evidence](FINDINGS.md#17-source-bound-mappings-and-legacy-duplicate-quarantine)
and the [legacy duplicate quarantine](docs/plans/2026-10-09-legacy-candidate-quarantine.md).

## Reconcile against a saved snapshot

For an initial [offline diagnosis](docs/design/offline-diagnosis.md) without
inventing a complete-history assertion or adoption resolutions:

```sh
.venv/bin/python boursedirect_to_ghostfolio.py diagnose \
  --config inputs/diagnosis-config.yaml --input-root inputs --max-bytes 1048576
```

It saves a private candidate/discrepancy report with exact input provenance. Exact
matches are observations, and missing matches never declare new imports. No wire,
adoption, holdings verdict or write intent is emitted. Success exits 2 with readiness
false. The strict review below requires the separately established evidence.

Save a complete Ghostfolio activity-list JSON and reviewed acquisition-history
evidence privately. The [review command contract](docs/design/offline-review-cli.md)
describes configuration and explicit manual-adoption resolutions.

```sh
.venv/bin/python boursedirect_to_ghostfolio.py review \
  --config inputs/review-config.yaml --input-root inputs --max-bytes 1048576
```

It writes a private reconciliation artifact and exact new-activity wire body,
with readiness false. Stdout contains counts and blockers only. It never fetches,
sends or changes Ghostfolio; there is no apply command.

## Save a read-only Ghostfolio snapshot

The optional [GET-only snapshot command](docs/design/readonly-snapshot.md) requires
an explicit private HTTPS allowlist and an existing session bearer supplied by
environment. It does not exchange a Security Token or renew credentials.

```sh
.venv/bin/python boursedirect_to_ghostfolio.py snapshot \
  --config inputs/snapshot-config.yaml --input-root inputs \
  --max-bytes 1048576 --timeout 30
```

It makes one GET and saves private raw activity JSON. No import/update/delete or
authentication POST exists. Actual read-only evidence used the authorized private
runtime route described in [FINDINGS.md](FINDINGS.md#16-actual-destination-read-only-evidence);
the public HTTPS command is tested with fake responses and forbidden real sockets.

This is an offline diagnostic tool, not a delivered automatic sync. Unsupported
periods and uncertain legacy matches block; no `apply` command exists. Personal
documents, configuration, outputs and journals stay ignored and private. Independent
agent PR reviews and synthetic CI are the validation evidence while the repository
is private; CodeRabbit is not assumed to run in that state.

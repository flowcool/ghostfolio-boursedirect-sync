# ghostfolio-boursedirect-sync

Offline source-characterization tools for a candidate manual Bourse Direct →
Ghostfolio importer. The implemented `inspect` command reads monthly statement
HTML, preserves aligned ledger slots and checks cash controls with Decimal.
Optional `--notes` inputs inspect daily contract notes and match trades exactly.
It does not create activities or contact either service.

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

The last command exits **2**, with a safe JSON summary: one buy, two sells, cash
controls reconciled, import readiness blocked. Exit **1** means unreadable or
inconsistent input. Input size/depth budgets are explicit; the example budgets
are for the synthetic bench, not established broker-document limits.

Save original statement and contract-note HTML locally under ignored `inputs/`
with private permissions. Do not put account documents in Git or Beads. PDFs,
pasted plain text and an authenticated URL cannot replace the saved HTML inputs.
Saved note layout and exact enrichment are evidenced for one month; historical
coverage and explicit price currencies remain source gates. Florent approved a
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

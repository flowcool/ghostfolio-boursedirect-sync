# Issue Tracker: Beads

Issues and live work state for this repository live in the shared Beads tracker.
Use the `bd` CLI, always scoped with
`project=ghostfolio-boursedirect-sync`. Beads is canonical for issue status,
dependencies, claims, and material work findings.

## Conventions

- Find ready work: `bd ready --exclude-type epic --metadata-field project=ghostfolio-boursedirect-sync`
- Read an issue: `bd show <id>`
- Create an issue with a problem-and-impact description, verifiable acceptance
  criteria, topical labels, and
  `--metadata '{"project":"ghostfolio-boursedirect-sync"}'`
- Claim an implementation issue before editing: `bd update <id> --claim`
- Record material findings with `bd-finding` (install the operator-provided
  structured-comment helper on `PATH`; it is agent tooling, not an importer
  runtime dependency). On the current operator host it is installed at
  `/home/flow/.agents/bin/bd-finding`.
- Model execution order with `bd dep add`; use epics as umbrellas rather than
  active implementation work
- Close only after each acceptance criterion has exact evidence:
  `bd close <id> --reason="..."`

## When a skill says "publish to the issue tracker"

Create a Beads issue following the conventions above.

## When a skill says "fetch the relevant ticket"

Read the referenced record, then its relevant comments and direct dependencies.
For backlog navigation, capture scoped JSON into ignored project-local `tmp/`
and print only IDs, titles, statuses and dependency IDs first. Read descriptions
and evidence only for selected issues. Keep full JSON available locally rather
than printing recursive records into a truncated transcript.

Example (each command must succeed before consuming its output):

```bash
set -euo pipefail
mkdir -p tmp
bd list --metadata-field project=ghostfolio-boursedirect-sync --json > tmp/issues.json
python3 -c 'import json; rows=json.load(open("tmp/issues.json")); print("\n".join(str((r["id"], r["title"], r["status"])) for r in rows))'
```

## Triage labels

Use the canonical labels in `triage-labels.md` as Beads labels.

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
- Record material findings with `/home/flow/.agents/bin/bd-finding`
- Model execution order with `bd dep add`; use epics as umbrellas rather than
  active implementation work
- Close only after each acceptance criterion has exact evidence:
  `bd close <id> --reason="..."`

## When a skill says "publish to the issue tracker"

Create a Beads issue following the conventions above.

## When a skill says "fetch the relevant ticket"

Read the referenced record with `bd show <id>`, then inspect its comments and
dependencies.

## Triage labels

Use the canonical labels in `triage-labels.md` as Beads labels.

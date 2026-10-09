# Domain Docs

How engineering skills consume this repository's domain documentation.

## Before exploring

- Read root `GLOSSARY.md` if it exists.
- Read any root `docs/adr/` records that affect the area under investigation.
- Read the applicable `docs/design/` contract for importer, acquisition, review,
  or application work.

If a glossary or ADR directory is absent, proceed silently. Create them only
when the relevant domain-modeling work resolves a term or a decision.

## Layout

This is a single-context repository. Any future glossary is `GLOSSARY.md` at
the repository root; architecture decisions are under `docs/adr/`. Do not add
a `GLOSSARY-MAP.md` or per-component glossary unless the repository becomes a
genuine multi-context monorepo.

## Vocabulary and decisions

Use glossary terms consistently in issue titles, tests, and design proposals.
If a proposed change conflicts with an applicable ADR or design contract,
surface that conflict explicitly rather than silently overriding it.

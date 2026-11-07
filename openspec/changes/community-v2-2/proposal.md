# Proposal

## Why

Users with downloaded notices still need Paperless. The public installation
files also require undocumented setup. v2.2 must provide a usable independent
installation without changing the financial rules.

## What Changes

- Add a read-only PDF folder through `NOTICE_DIR`. Select exactly one source.
  Paperless remains supported and becomes optional.
- Identify folder documents by content hash. Keep financial event identities,
  duplicate checks, review, coverage and unreadable write blocks.
- Use printed trade or payment dates for `IMPORT_CREATE_FROM`. An unknown
  folder date stays unreadable and held. Add no local done marker. Allow an
  optional read-only `NOTICE_WAIVER_FILE` for digest-bound document stops.
- Plan report items 2–8 as tasks only: portable released-image Compose;
  consistent examples; one current installation route; independent Paperless
  setup; security and privacy; public support; community discovery.
- Require a timed first simulation, source parity, renamed-copy protection,
  unreadable write blocks and exact-digest qualification before release.

## Operation Scope

Use the same saved original-notice corpus as the released
[manual reconciliation change](../manual-reconciliation-coverage/proposal.md).
Folder storage adds no notice family. Replay those originals through both sources.

| Observed operation | In scope / out of scope |
| --- | --- |
| ACHAT COMPTANT, ACHAT ETRANGER | In: existing BUY rules |
| VENTE COMPTANT, VENTE ETRANGER | In: existing SELL rules |
| COUPONS | In: existing net DIVIDEND rules |
| TAXE TRANSACT FINANCIERES | In: charged TTF attributed to one BUY |
| DROITS DE GARDE | In: information; no activity |
| DIVISION | Out: execution; retain the security hold |
| DET DROIT DE SOUSCRIPTION, INDEMNISATION, ESPECES SUR OST, ATTRIBUTION, RETRAIT TITRES FISCALISE | Out: import/correction; retain unsupported findings |

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `notice-import`: folder source only. Apply the released manual-reconciliation
  and creation-cut-off deltas with the main spec.

## Non-goals

Broker login; collector or managed Paperless deployment; CTO or arbitrary accounts;
OCR; new notice families; FX conversion; statements or opening balances;
automatic corporate actions; expanded correction authority; a web UI; a shared
connector library; licensing changes; public-history rewrites; a large campaign
before installation acceptance.

## Impact

Future implementation touches acquisition, configuration, review evidence,
coverage, packaging and public guidance. This PR contains planning text only.
The coordinator approved the source limits and digest-bound waivers. Document
user-owned removal of permanently unreadable files and its coverage loss.
Measure installation time before setting a duration target. Implementation,
release, production writes and external announcements remain separate steps.

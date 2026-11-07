# Design

## Context

See [proposal](proposal.md) and [delta](specs/notice-import/spec.md).
BD baseline: `b586346f13f84a5efcd73760b85bcf0ef557aa44`.
Read its main spec together with both released, unarchived deltas.
This proposal does not consolidate them.

## Goals / Non-Goals

Add source selection before shared parsing and financial selection.
Keep typed functions and data records. Add no broker access, second review
store or source completion database. Items 2–8 remain tasks only.

## Decisions

Sibling references use IBKR
`f9a2b113539674296667e45dd28fddaff1ecb1c5`.
The [earlier adoption map](../archive/2026-10-30-pdf-notice-importer/design.md)
pins the financial mechanisms already present in BD.

| Part | Reuse |
| --- | --- |
| Startup, identity, selection, writes | Existing BD `config.py`, `sync.py`, `ghostfolio.py`; pinned IBKR mechanisms in the adoption map |
| Review and coverage | BD `activity_review.py`, `notice_coverage.py`; same journal and guards |
| Packaging | IBKR `compose.yaml:3,26–35`; BD release scripts |
| Installation and limits | IBKR `docs/getting-started.md:14,63,79,85,127`; `README.md:73,146` |
| Public support and history | IBKR `CONTRIBUTING.md:5–11`; `CHANGELOG.md:5` |

Folder acquisition has no sibling equivalent. It is the proposed BD adaptation.
Use `NOTICE_DIR` rather than another mode variable. Reject mixed configuration
to prevent unintended imports. Keep Paperless behavior conditional on its mode.

Add `notice_source.py` and `folder.py` as acquisition functions. Replace integer-only
source references across shared reporting with typed source references. Use
SHA-256 for folder document identity; retain `BD#v3` event identity. Never generate
fake Paperless IDs. Check complete acquisition before dispatch. Compare acquired
files again before writes; stop on changed evidence.

Propose shallow `.pdf` selection and 20 MiB per file to bound reads. Reject links
and special files. Keep review storage outside the source. Keep content evidence
stable under rename. A source switch can invalidate consent; it cannot clear
pending financial uncertainty.

No folder waiver is safer than filename or sidecar consent. Folder stops remain
held. Supported-row parity excludes transferring Paperless-specific waivers.

## Risks / Trade-offs

Unreadable historical folder files block writes because no trusted date remains.
Byte-different copies change document evidence; logical duplicate guards remain.
Qualification must prove unchanged financial output and review protection.

## Migration Plan

Keep Paperless ENV valid. Add folder mode without historical conversion.
Validate the published-image route after implementation. Qualify one digest in
both labs. Roll back to the prior image and ENV; retain journals and accepted
activities. Image rollback cannot undo financial writes.

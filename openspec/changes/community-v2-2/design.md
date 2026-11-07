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

Folder acquisition and its waiver file have no sibling equivalent. They are
coordinator-approved BD adaptations.
Use `NOTICE_DIR` rather than another mode variable. Reject mixed configuration
to prevent unintended imports. Keep Paperless behavior conditional on its mode.

Add `notice_source.py` and `folder.py` as acquisition functions. Replace integer-only
source references across shared reporting with typed source references. Use
SHA-256 for folder document identity; retain `BD#v3` event identity. Never generate
fake Paperless IDs. Check complete acquisition before dispatch. Compare acquired
files again before writes; stop on changed evidence.

Use shallow `.pdf` selection and 20 MiB per file to bound reads. Reject links
and special files. Keep review storage outside the source. Keep content evidence
stable under rename. A source switch can invalidate consent; it cannot clear
pending financial uncertainty.

Reuse the document-local waiver semantics in BD `app.py:108–117`. In folder
mode, optional `NOTICE_WAIVER_FILE` supplies exact digest/code pairs. Choose
plain UTF-8 text: each nonempty line has `sha256:<64 lowercase hex digits>`,
one ASCII space, then `share_count_change` or `unknown_operation`. Blank lines
are allowed. Reject duplicate pairs and all other content. Limit to 65,536 bytes.
Read once before service access; reject malformed, missing, unreadable, oversized
or unsafe files with `invalid_configuration`. Reject any nonempty waiver setting
in Paperless mode. Never write this file or create completion markers.

Require an absolute path outside `NOTICE_DIR` and separate from the review path.
Reject links, non-regular files, resolved-path overlaps and existing inode aliases.
Extend the existing review input-preservation checks in `activity_review.py:97–117`
to protect the waiver file. A waiver clears only its matching document stop code;
other documents, unreadable findings and financial guards remain effective.
Unknown digests are ignored and counted. Rename preserves the digest; changed
bytes require new consent. Paperless tags do not transfer between sources.

Document user-owned recovery for a permanently unreadable notice: move it out of
`NOTICE_DIR` and record the move. This hides it from coverage. The importer never
moves it. Keep the no-duration-target rule until installation time is measured.

## Risks / Trade-offs

Unreadable historical folder files block writes because no trusted date remains.
Byte-different copies change document evidence; logical duplicate guards remain.
Qualification must prove unchanged financial output and review protection.

## Migration Plan

Keep Paperless ENV valid. Add folder mode without historical conversion.
Validate the published-image route after implementation. Qualify one digest in
both labs. Roll back to the prior image and ENV; retain journals and accepted
activities. Image rollback cannot undo financial writes.

## Approved IBKR runtime and documentation alignment

Use IBKR `f9a2b113539674296667e45dd28fddaff1ecb1c5` as read-only evidence.
`entrypoint.sh:4–6,32` supplies revision validation and scheduler flags.
`ghostfolio_ibkr_sync/__main__.py:11–26` supplies logging and the urllib3 cap.
`app.py:962–969,798–808` supplies per-run identity, simulation and timezone logs.
`notify.py:redacted_source_failure` supplies the diagnostic boundary. BD uses
fixed allowlisted codes and context, never arbitrary exception text.
The approved `feat/retro-startup-banner:entrypoint.sh:4–16` pattern supplies
static art. Generate `BD SYNC` once with pyfiglet 1.0.4 slant. Keep five art
lines, an ASCII subtitle and no runtime renderer. Identity retains its approved
em dash; the art and subtitle stay ASCII.
IBKR `compose.yaml:3–6,14` supplies restart policy and timezone defaults.
Its README tag policy and `docs/` split supply the public documentation pattern.
Keep BD's digest-pinned operator bundle and unreleased v2.2 installation route.

Acceptance uses the entrypoint process boundary, CLI log streams, app failure
finalization and ENV/Compose key parity. No financial rule changes or lab writes
belong to this alignment. The existing lab owner retains qualification.
Rollback reverts these additive commits and retains all source and lab evidence.

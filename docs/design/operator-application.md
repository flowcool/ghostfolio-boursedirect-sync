# Operator application preview

`apply --config FILE --review FILE --review-sha256 HEX --input-root DIR
--max-bytes N [--export outputs/FILE.json] [--execute]` is an offline application
preview. DRY_RUN absent or1 forces preview;0 without execute still previews.
Other spellings fail. Explicit execute withDRY_RUN0 delegates to the separately
[qualified controller](qualified-application.md); without its externally pinned
declaration it refuses with `APPLICATION_EXECUTION_GATE_REQUIRED`. This document
describes the preview/export branch; its authority never permits dispatch.

The command captures six bounded local files once, validates the externally pinned
complete frozen review and prints only counts/blockers/dry_runtrue/readinessfalse.
It never reads destination/broker credentials, constructs network transport,
creates write intents or records simulated acceptance. Success diagnostic exit2
also covers all-existing/null-wire and holdings shortfalls; refusal exit1 has no
stdout. Configuration/report paths follow the current directory; role references
follow input-root. A pin proves bytes, not source authenticity or human approval.

Optional export is exact new-only numeric JSON, a private **manual import proposal**.
Shortfalls/unresolved adoption and null wire reject export. Before mkdir/chmod or
publication, the command verifies ignored outputs-root containment, all symlink
ancestors/leaves, directory/file types and every captured file path/inode alias.
Only the outputs root can be created; existing nested parents are required.
Publication uses0600 file and0700 outputs/immediate parent, atomic rename/fsync;
no lock or journal is involved. Validation refusals preserve source/prior-output
bytes and modes. A post-rename filesystem failure can leave a new visible file
with unproven crash durability and does not report success.

Exporting does not upload or authorize upload, validate fresh remote state, or
inherit the single-event application's acceptance/fence protocol. Unsupported
source periods, actual legacy/adoption/history and production/security/recovery
remain gates. Retain proposals under ignored outputs; never version them.
Rollback scoped code revert; retain private evidence and outputs. No remote effect
is caused by the preview/export branch. [Approved design](../plans/2026-10-09-operator-application.md).

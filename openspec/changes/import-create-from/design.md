# Design

The approved BD adaptation adds a creation boundary. Neither sibling has this
notice-specific boundary. Reuse IBKR v3.0.0 `403b4ccf` config.py:75,95 for ENV
validation, app.py:203-208 for security exclusion and sync.py:580,960 for selection.
Reuse current BD `app.run_sync`, review proposals and `notice_coverage.report`.

Keep original parsing and identity unchanged. Retain the printed date of each
unsupported row. Historical stops cannot block recent creations. They still
protect historical review and remain visible in coverage. Filter historical
creation candidates before duplicate assignment and position simulation.
Historical rows do not supply simulated holdings. Existing holdings do.

Keep historical rows available to configured review. Do not infer correction
authority from the cut-off. Without review, historical mapping and matching
failures cannot stop recent creation. Coverage still resolves the entire source.

For a parse failure only, read the existing Paperless document resource through
the configured-origin GET helper. Use its `created` document date, never `added`
or a filename. Accept only a valid ISO calendar date. Missing or invalid evidence
cannot exempt the notice. Transport and authorization failures remain failures.
This date source is an approved BD adaptation; no previous importer date trust
exists for unreadable originals. The captured document uses this field as its
notice date. It is not part of financial identity.

Count all historical supported source rows, including repeated copies. Count
documents with only historical dated rows, plus exempt unreadable documents.
Keep unreadable totals separate from write-blocking unreadable totals.

Acceptance: real anonymized notice text at `app.run_sync`, strict ENV validation,
coverage and existing review tests. Replay all captured originals and complete
production activities offline. Require exactly two absent recent BUYs, no false
creation, no correction and exit 0. Qualify the exact image in both reserved labs
with creation and repeat. Retain all evidence and stop both owned instances.

Rollback: revert this change and restore the prior ENV. Keep review journals and
all accepted activities. This change cannot reverse a confirmed financial write.

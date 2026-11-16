# Design

## Context

See the proposal for scope. The existing `app.py` emits all three messages. `notices.py` rejects malformed coupon headers. `outcome.py` reports missing reconciliation counts as unavailable.

## Goals / Non-Goals

Change diagnostics only. Keep financial values, source selection, identities, failure codes, and write guards unchanged. Add no setting or runtime dependency.

## Decisions

Reuse `ghostfolio-ibkr-sync/ghostfolio_ibkr_sync/outcome.py:149-160`. It emits reconciliation counts only when results exist. BD already adapts this mechanism in `outcome.py::log_account_evidence`. Distinguish a disabled review from an unavailable result there and in the existing review summary. Derive disabled state from the configured profile and review file, not from empty counts.

Reuse the approved BD custody-fee adapter in `app.py`, backed by the current specification's information classification. Change its log level only.

Reuse the approved BD parser in `notices.py::parse_text`. Add narrowly scoped recognition for the missing-ISIN coupon case. Carry a fixed reason while preserving the exact `notice_unreadable` error classification. Keep raw source text outside logs. No sibling parses BD notices; this extends the existing approved BD adapter rather than introducing an importer mechanism.

Test at the existing parser and run-output interfaces. Parser tests verify the fixed reason and rejection. Run tests verify levels, summaries, exit codes, and blocked writes. Existing real anonymized fixtures cover custody fees and the missing-ISIN coupon. Derived cases cover unreliable dates and other malformed inputs.

## Risks / Trade-offs

- A malformed header can resemble an absent ISIN. Require a recognized coupon row; other malformed rows keep their original diagnostic.
- Added exception detail can change code comparisons. Preserve the canonical error string and check the historical cut-off and coverage paths.
- Profile `off` permits manual review with a file. Never label that combination disabled.

## Migration Plan

No data migration. Rollback is a revert of the diagnostic change. No production action belongs to this change. Publication follows the existing repository process if requested.

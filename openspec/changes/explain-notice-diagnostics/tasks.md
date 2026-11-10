# Tasks

The specification is `specs/notice-import/spec.md`. All tasks use the existing parser and run-output interfaces. Confirm these test boundaries with the operator before writing tests.

## 1. Run diagnostics

- [x] 1.1 Replay one real anonymized BUY in isolated simulation without a TTY. Use the existing Compose service and the spec command. Retain the exact fields and no-write evidence. Reuse the existing IBKR startup core without adding a startup mechanism.
- [x] 1.2 Implement the informational custody-fee scenario with a failing run-output test first. Touch `ghostfolio_boursedirect_sync/app.py` and the existing custody-fee tests. Verify INFO level, document reference, row count, unchanged activity selection, and exit status with `.venv/bin/python -m pytest -q tests/test_notice_checks.py tests/test_pdf_sell.py`.
- [x] 1.3 Implement disabled, unavailable, and measured review states with one failing test and one implementation at a time. Touch `ghostfolio_boursedirect_sync/app.py`, `ghostfolio_boursedirect_sync/outcome.py`, and existing outcome/review tests. Verify profile off with and without a file, failure before review, and measured zeros with `.venv/bin/python -m pytest -q tests/test_failure_notification.py tests/test_activity_review.py`.

## 2. Missing source identity

- [x] 2.1 Implement the fixed missing-ISIN reason with parser and run-output tests, one failing case at a time. Touch `ghostfolio_boursedirect_sync/notices.py`, the existing unreadable-source logging path in `app.py`, and existing coupon/cut-off tests. Replay the retained real coupon and explicit derived dates. Verify the original failure code, historical exclusion, coverage failure, private-data omission, and blocked writes with `.venv/bin/python -m pytest -q tests/test_pdf_coupon.py tests/test_import_cutoff.py`.

## 3. Delivery verification

- [x] 3.1 Run Ruff and strict mypy during implementation. At the end, run the full offline suite once and replay the exact changed diagnostics from retained source fixtures. Review necessity, scope, and protections. Record commands, results, and the atomic commit in the owning issue. If publication is requested, use the existing CI and Pullfrog process; qualify labs only if implementation changes a financial or write-related gate. Do not create release tooling or change production.

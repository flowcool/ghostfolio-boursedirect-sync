# Tasks

The coordinator approved this change under Florent's delegation, subject to
A1-A9. Mark implementation tasks only after their acceptance passes. Each task refers to [the delta](specs/notice-import/spec.md).
Application paths below start at `ghostfolio_boursedirect_sync/`.
Keep code, tests and README changes together in each slice.

Use retained `reconciliation.json` and unchanged originals as private evidence.
The pre-correction capture contains 24 fee differences, four probable coupons
and 11 absent rows. The post-correction capture contains ten restored rows;
EMEIS remains unresolved. Anonymize account and holder fields in committed
fixtures. Do not commit private captures, identities or original PDFs. Mark
constructed target states and boundary tests as derived data. Do not claim
that the broker supplied those states.

Use existing Infra lab tooling, reservations and retained proof. No production
write, broker access, stable release or deployment follows from these tasks.
Apply `security-review` during implementation for review input and file handling.

## 1. Preserve the existing import path

- [x] 1.1 Replay one real BUY in simulation without TTY. Requirements: Simulation by default; Reviewed manual history corrections. Scenario: Approval, restart and repeat, before approval. Files: `app.py`, `config.py`, `models.py`, `tests/test_pdf_buy.py`, `README.md` only where needed. Reuse current IBKR startup; add no new startup layer. Acceptance: `docker compose run --rm -T --no-deps importer` with absent DRY_RUN shows exact BUY fields, DRY RUN, exit 0 and no financial request. Record source and runtime pins before changes. Reuse valid existing startup proof when inputs and implementation are unchanged.

## 2. Review manual trade fees

- [x] 2.1 Expose fee differences before ordinary duplicate suppression. Requirements: Manual trade fee correction from the notice; Reviewed manual history corrections. Scenario: Twenty-four fee differences. Files: `sync.py`, `activity_review.py`, `activity_reconciliation.py`, `tests/test_activity_review.py`, `tests/test_activity_reconciliation.py`, `README.md`. Acceptance: `uv run python -m pytest tests/test_manual_history.py -k manual_fee`. Replay all 24 retained differences in simulation. Show exact notice fees and every existing hold. Cover BUY/SELL, large and cent differences, numeric equality, competing pairs, missing review file and unchanged full comments. No profile bypasses manual approval for this new kind.
- [x] 2.2 Apply approved fee-only proposals through existing dispatch. Requirements: Reviewed manual history corrections; Manual trade fee correction from the notice. Scenarios: Approval, restart and repeat; Twenty-four fee differences. Files: `activity_review.py`, `ghostfolio.py`, `tests/test_fee_correction.py`, `tests/test_correction_recovery.py`, `README.md`. Acceptance: `uv run python -m pytest tests/test_fee_correction.py tests/test_correction_recovery.py` with real BUY/SELL notice fixtures and derived target states. Confirm fee-only PUT, all preserved fields, all-approved sequential execution, fixed D=150 seconds, exact readback and zero update on repeat. Inject uncertain readback in the unit fixture; restart retains the hold without resend. Preserve journal compatibility.

## 3. Review manual coupons

- [x] 3.1 Discover mutually unique manual coupons within 31 calendar days in configured `TZ`. Requirements: Manual coupon net and date alignment; Reviewed manual history corrections. Scenarios: Four probable payments; Window and ambiguity. Files: `activity_review.py`, `activity_reconciliation.py`, `sync.py`, `tests/test_activity_reconciliation.py`, `README.md`. Acceptance: `uv run python -m pytest tests/test_manual_history.py -k manual_coupon` with fixtures for the four retained notice cases. Display exact date/net/quantity/fee/currency changes, including SAAB SEK. Verify complete two-way candidate uniqueness, recognized identity precedence, ±31/32-day edges, source holds, profile isolation and import protection with or without review enabled.
- [x] 3.2 Apply reviewed coupon normalization through the same executor. Requirements: Manual coupon net and date alignment; Reviewed manual history corrections. Scenarios: Four probable payments; Approval, restart and repeat. Files: `activity_review.py`, `ghostfolio.py`, `tests/test_activity_review.py`, `tests/test_correction_recovery.py`, `README.md`. Acceptance: focused unit tests on each real notice fixture with derived pre-correction activities. Integrated native qualification belongs only to 5.1. SAAB must read back activity EUR while preserving the same SEK market profile. Stop this slice if the qualified API cannot do that. Confirm each exact net/date, quantity 1, fee 0, preserved ID/owner/tags/comments and no POST/DELETE. Repeat unchanged: no correction. Changed source, decisions or target evidence cannot bypass review or pending recovery.

## 4. Report notice coverage

- [x] 4.1 Add the report-only ENV mode and complete-notice inventory. Requirements: Settings from ENV only; Full available-notice coverage report. Scenarios: Eleven absent rows and corrected history; False creations and unreadable evidence. Files: `config.py`, `models.py`, `app.py`, `paperless.py`, `sync.py`, `activity_reconciliation.py`, `tests/test_notice_coverage.py`, `README.md`. Acceptance: `uv run python -m pytest tests/test_notice_coverage.py` with `NOTICE_COVERAGE=1`, including DRY_RUN=0 and existing yes/pending state. Confirm every page/done-tagged notice, correct account scope, copy deduplication, exact counts and detailed local rows. Review state and financial state stay unchanged. Incomplete acquisition stays a failure. Normal creation counts must not classify the 20 explained representations or four probable payments as absent. Replay the full private pre/post captures; retain every failure and unknown.
- [x] 4.2 Add interval quantity diagnosis and redacted actions. Requirements: Notice-backed position comparison and alerts; Exit code, summary and notification. Scenarios: Position changes before and after backfill; Repeated redacted alert. Files: `activity_reconciliation.py`, `outcome.py`, `notify.py`, `app.py`, `tests/test_notice_coverage.py`, `tests/test_notify.py`, `README.md`. Acceptance: `uv run python -m pytest tests/test_notice_coverage.py tests/test_notify.py`. Fixture report shows UCB +2/APAM -18 then zero after restored trades. Unsupported transformations remain unverifiable. No opening BUY for EMEIS/Millennium. Use unit transport fixtures to prove grouped reason/count summaries, changed/cleared groups, the 168-hour reminder, failed delivery, clock rollback, failure precedence and no timeout resend. Document notices-only limits and UTC boundaries.

## 5. Qualify the approved candidate

- [x] 5.1 Run integrated acceptance on the exact candidate digest in the existing empty and golden labs. Requirements: all delta requirements and existing import/recovery guards. Scenarios: all real and explicitly derived cases above. Files: tests and README only as needed; align approved contract pointers and stale correction restrictions in `AGENTS.md` and `openspec/config.yaml` before enabling the new behavior. Acceptance: `uv run python -m pytest`, `uv run ruff check .`, `uv run mypy`, ONE integrated native acceptance in the reserved empty and golden labs, on the exact candidate digest, covering real BUY/SELL/coupon notices, all-approved correction chains at D=150 seconds, exact readback before each next PUT, injected uncertainty and restart without resend, SAAB EUR with preserved SEK profile, report mode and repeat. Retain request-bound background completion evidence to qualify the delay. Also verify exact unrelated-field/cash preservation and zero report-mode financial requests. Include post-history idempotence: ten restored rows and earlier quantity repairs stay correct; deleted wrong-symbol rows stay absent. Never recreate them from uncertain aliases. Reuse existing release owners and exact-digest gates. Stop and verify owned labs; retain proof. Code delivery needs current CI and Pullfrog review. Stable publication and production remain separate decisions.

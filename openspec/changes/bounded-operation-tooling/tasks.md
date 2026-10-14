# Tasks

Explicit tooling authorization overrides the rebuild-specific BUY-first/no-tooling task defaults. All checks below are offline; add relevant README guidance per slice.

## 1. Preparation

- [ ] 1.1 Deliver schema/preflight and safe receipts; verify `tests/test_operation_run.py -k preflight` for target drift, capabilities, interpreter and authority refusal.
- [ ] 1.2 Deliver verified backup/install/selective rollback; verify `tests/test_operation_run.py -k deployment` for inventories, aliases, hashes and protected journals.

## 2. Product boundaries

- [ ] 2.1 Deliver bounded auth/recovery ENV launcher; verify `tests/test_operation_run.py -k recovery` for request limits, secrecy and persistence uncertainty.
- [ ] 2.2 Deliver Compose delegation and complete preservation readback; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` across every phase with mocked adapters; retain source/test/requirement trace. Require delivered `infra-a3ri` for import.

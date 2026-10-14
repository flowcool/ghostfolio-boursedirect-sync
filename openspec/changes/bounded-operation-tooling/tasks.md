# Tasks

One-hour offline automation slices; include README guidance.

## 1. Preparation

- [ ] 1.1 Deliver schema/preflight/single-use receipts; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k preflight` including crash/reuse.
- [ ] 1.2 Deliver backup/restore verification; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k backup` including ownership/mode/alias/hash corruption.
- [ ] 1.3 Deliver install/rollback digest transitions; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k deployment` preserving journals.

## 2. Existing product boundaries

- [ ] 2.1 Deliver checked-origin/network auth/stdin launcher; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k recovery` including secrecy.
- [ ] 2.2 Deliver Compose delegation; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k compose` scopes; retain separate `infra-a3ri` prerequisite.
- [ ] 2.3 Deliver pre-POST delta proof/post-comparison; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` across phases/cash/zero-tolerance; retain requirement/source/test receipts.

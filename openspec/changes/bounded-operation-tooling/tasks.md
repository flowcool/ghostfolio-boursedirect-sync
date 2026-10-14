# Tasks

One-hour offline slices; include README guidance.

## 1. Preparation

- [ ] 1.1 Deliver schema/preflight/single-use receipts; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k preflight` including crash/reuse.
- [ ] 1.2 Deliver backup/restore verification; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k backup` including ownership/mode/alias/hash corruption.
- [ ] 1.3 Deliver install/selective rollback; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k deployment` preserving post-import journals.

## 2. Existing product boundaries

- [ ] 2.1 Deliver auth/stdin-to-child-ENV launcher; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k recovery` including Docker-config/argv/log/file secrecy.
- [ ] 2.2 Deliver Compose delegation; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k compose` scopes; retain separate `infra-a3ri` prerequisite.
- [ ] 2.3 Deliver preservation/aggregate comparison; verify `.venv/bin/python -m pytest -q -s tests/test_operation_run.py` across all phases/cash/authorized deltas; retain requirement/source/test receipts.

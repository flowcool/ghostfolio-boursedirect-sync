---
description: Python conventions for ghostfolio-boursedirect-sync
globs: ["*.py"]
---

- Type the application package fully. Use strict mypy and Ruff, as in the approved ibkr source. Tests keep relaxed typing. Types must not change financial behavior.
- Logging: `log.warning` for operational skips, `log.error` for failures, `log.debug` for verbose
- Never log a token or credential
- Errors: `raise RuntimeError(...)` with explicit message, never silent `return` on failure
- Adopt the complete applicable IBKR core pinned in the active design. Read its coverage table before coding. Preserve each applicable protection and test. Record source references and reasons for BD adaptations there. Keep shared data records in `models` to avoid import cycles. The Docker image installs the package and runs `python -m ghostfolio_boursedirect_sync`.
- Tests: `pytest` in `tests/` (offline, pure functions, requests mocked; dev-only deps in `requirements-dev.txt`, never in the image). A logic change ships with a test from real anonymized notice text. Run the relevant tests before committing a logic change.
- Use module-level functions. Frozen dataclasses and typed dictionaries describe settings, financial records and external JSON. Keep behavior in functions.
- Keep `Decimal` for money and position decisions. Adapt ibkr float comparisons to the exact BD contract.
- Use the Python release selected by the native image and CI. Run `.venv/bin/python -m ruff check ghostfolio_boursedirect_sync`, `.venv/bin/python -m mypy --strict ghostfolio_boursedirect_sync` and the relevant offline pytest checks after logic changes. Docs-only changes need no runtime tests.

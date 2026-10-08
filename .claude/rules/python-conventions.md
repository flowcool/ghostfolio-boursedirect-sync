---
description: Python conventions for ibkr_to_ghostfolio.py
globs: ["*.py"]
---

- No type hints — match existing style
- Logging: `log.warning` for operational skips, `log.error` for failures, `log.debug` for verbose
- Never log a token or credential
- Errors: `raise RuntimeError(...)` with explicit message, never silent `return` on failure
- Mono-file: do not create additional modules without strong justification
- Tests: `pytest` in `tests/` (offline, pure functions, any future requests mocked; dev-only deps in `requirements-dev.txt`). Run `.venv/bin/python -m pytest -q` before commit. A logic change ships with a meaningful test; Ghostfolio integration checks require a disposable isolated instance, never production or shared state.
- No classes — functional style with module-level functions

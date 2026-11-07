## 1. Creation boundary

- [x] 1.1 Validate optional ISO `IMPORT_CREATE_FROM` and exclude older creation rows. Requirement: Creation cut-off. Scenarios: Boundary and default; Historical false creations. Files: config.py, models.py, app.py, tests/test_import_cutoff.py, real anonymized fixtures, README.md. Check: `.venv/bin/python -m pytest tests/test_import_cutoff.py`; real BUY simulation through the existing cycle.
- [x] 1.2 Keep historical review and full coverage. Retain unsupported-row dates. Requirement: Creation cut-off. Scenarios: Historical review and coverage; Historical stop. Files: notices.py, models.py, app.py, tests/test_import_cutoff.py. Same check plus existing review and coverage tests.
- [x] 1.3 Exempt only unreadable notices with a proved older Paperless document date. Requirement: Unreadable documents block writes. Scenarios: Historical unreadable notice; Missing or current date. Files: paperless.py, app.py, tests/test_import_cutoff.py. Same check; prove fail-closed HTTP and invalid metadata cases.

## 2. Qualification

- [x] 2.1 Replay current read-only capture and all 75 originals. Require two absent BUYs only, zero false creations/errors/corrections, exit 0. Save private evidence. Run strict mypy, Ruff and full pytest once after focused tests pass.
- [x] 2.2 Qualify one exact candidate in empty and golden labs with repeat. Reserve, retain proof, stop and release. Complete independent code review, one PR, green CI and Pullfrog head review through pr-ship. No publication or production action.

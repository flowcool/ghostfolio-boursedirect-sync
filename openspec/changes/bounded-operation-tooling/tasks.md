# Tasks

One-hour proposals; no delivered helpers/code/propagation. BD includes README.

## Upstream dependencies

- [ ] 1.1 IBKR canonical adapter-bound exchange; offline auth regressions.
- [ ] 1.2 IBKR canonical Decimal/count/unique-ID decoder; offline completeness regressions.
- [ ] 1.3 IBKR canonical created-row comparator; offline exact-match regressions.
- [ ] 1.4 Optional IBKR adapter adoption after 1.1–1.3; offline cash/import regressions.
- [ ] 1.5 Optional DEGIRO independent reviewed adoption after 1.1–1.3; `scripts/check_core.py --source ../ghostfolio-ibkr-sync`/offline adapter regressions.

Upstream acceptance: `.venv/bin/python -m pytest -q`; separate project approvals required.

## Bourse Direct delivery

Future checks use `.venv/bin/python -m pytest -q -s tests/test_operation_run.py -k NAME`.

- [ ] 2.1 After 1.1–1.3, pinned BD projection/adoption; check `projection`.
- [ ] 2.2 Deliver dedicated AT1/peer/stdin transport; check `recovery`.
- [ ] 2.3 Deliver preflight/install/digests/mutation receipts; check `preflight`, including crash/reuse.
- [ ] 2.4 After infra-a3ri, Compose/call-pre-intent-guard/daily-capture fence; check `compose`.
- [ ] 2.5 Exact native-cash/activity proof/diagnostics; check `preservation`, then acceptance without `-k`.

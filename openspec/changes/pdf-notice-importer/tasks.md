# Tasks

Each task is one bead, one branch and one PR. "The run command" and "notice
documents" are defined in the spec. A task that needs a real PDF of a type that
is not yet in Paperless waits for that PDF. Tests use anonymized text of real
PDFs only. Paperless is read only; no task writes to it.

Follow the IBKR modules, source commit and function references in design.md.
Record and justify each BD adaptation there before coding. Selective reuse
can start before ibkr 3.0.0 stable. Review any later source update separately.
Use the installed Python 3.14 package `ghostfolio_boursedirect_sync`, with typed
functions and data records. Pass strict mypy and Ruff as well as each task's
offline tests. Preserve Decimal and all BD spec rules when adapting source code.
These checks accompany each code task; they are not separate tooling tasks.
The architecture approval does not authorize live runs, financial writes or
publication. Keep the existing real-PDF and first-write authorization gates.

## 1. First real BUY in simulation

- [ ] 1.1 Gate the real BUY PDF first. Confirm that it has exactly one labelled
  account field. Remove spaces once and require full equality with
  `BD_ACCOUNT_REF`. Measure `QUANTITE x COURS - BRUT` exactly and report the
  result. If either gate fails, stop and report. Add the application package
  and `pyproject.toml`. Adapt `Dockerfile`, `entrypoint.sh`, `requirements.txt`,
  `requirements-dev.txt` and `compose.yaml` from the pinned ibkr source.
  Install the package; Docker runs `python -m ghostfolio_boursedirect_sync`.
  Keep the legacy source only until task 1.3; the image must not run it.
  Include `poppler-utils`, without a browser, Node or Bitwarden.
  With the minimum required settings, read the notice documents
  from Paperless, select the account, read the BUY row, mapping file and the
  single Ghostfolio account, then log the simulated BUY. Add one offline test
  from the anonymized text of the real BUY PDF. Verify that `compose.yaml` has
  no `BW_` variable. Verify `.venv/bin/python -m ruff check ghostfolio_boursedirect_sync`,
  `.venv/bin/python -m mypy --strict ghostfolio_boursedirect_sync` and
  `.venv/bin/python -m pytest -q`.
  Adapt CI to install and check the new Python 3.14 package and image.
  Update or retire only the legacy checks and jobs that require the removed
  browser or vault runtime. Keep security coverage for the new runtime.
  Keep the remaining legacy tests runnable until task 1.3. Install their
  existing test dependencies; do not skip failures without a proven cause.
  Run the run command without `DRY_RUN` for each configured
  account service. With the real BUY PDF as the only notice document, it shows
  `DRY RUN`, one BUY line and exit code 0.
- [ ] 1.2 Add the settings checks, `paperless_auth_failed`,
  `paperless_unreachable`, `source_field_missing`, the exact single Ghostfolio
  account match and the other-account count. Add the README quick start and
  settings table. The README and `compose.yaml` show one service per Bourse
  Direct account. They use only the ENV names of the spec. The legacy names
  (`GHOST_ACCOUNT_ID`, `BD_SOURCE_ACCOUNT_REF`) and all `BW_*` variables stay
  absent. Verify the scenarios "Missing Paperless token", "Ambiguous
  Ghostfolio account", "Wrong Paperless token", "Paperless down", "Source
  field missing" and "Notice of another account".
  Keep `DRY_RUN` limited to 0, 1 or absent. Require one exact target-account
  match. Error logs must not include raw response bodies.
- [ ] 1.3 Remove the files that only the legacy code uses: `scripts/`,
  `collector/`, `compose.lab.yaml`, `compose.broker-inspection.yaml`,
  `docs/verification/` and the remaining legacy tests. Remove CI calls that
  remain after task 1.1. Remove `boursedirect_to_ghostfolio.py` after its
  selected parser logic is covered in the package.
  Start this task only after task 1.1 is merged.
  Verify: CI is green, and the sum of lines in all application-package Python
  files is 2 500 or fewer. Tests and packaging metadata do not count.

## 2. Notice checks

- [ ] 2.1 Add the amount checks (BUY, SELL and coupon) and `notice_unreadable`
  with the block of all writes, with offline tests from altered anonymized
  text. Verify the scenarios "Altered amount" and "Unreadable document".

## 3. Security resolution

- [ ] 3.1 Add the Ghostfolio lookup by ISIN, `unresolved_security` and the list
  of mapping lines to paste. Add the README mapping section. Verify the scenario
  "No EUR lookup result".

## 4. Sells, coupons and duplicates

- [ ] 4.1 For each real PDF type used, record whether it shows a broker notice
  reference. Add the `BD#v3#` comment with that reference as the document
  namespace, or with the first 16 hex characters of the original PDF SHA-256
  when it does not. Add `owned_activity_conflict`, the manual match with exact
  price and `possible_duplicate`, with offline tests. Two identical rows in one
  notice give two activities. Verify in simulation with the run command: a real
  BUY that matches a manual Ghostfolio activity shows a duplicate.
  Adapt identity parsing to BD v3; do not copy the IBKR namespace or its
  source-specific identifiers. Keep legacy BD rows readable for matching.
- [ ] 4.2 Add SELL rows, the sell guard on the running position and
  `custody_fee_ignored`, with an offline test (two sells that together exceed
  the position). Verify the scenarios "Sell without a position" and "Sell
  notice with a custody fee".
  Use Decimal and chronological rows, with SELL first on equal dates.
  When writes are enabled in task 6.1, only confirmed buys can support sells.
- [ ] 4.3 Add COUPONS rows and the dividend match (exact `BD#`, or 3 days and
  same net amount without `BD#`, else `possible_duplicate`). Verify the scenarios "Real coupon in
  simulation" and "Coupon already in Ghostfolio".
  Keep quantity 1, net unit price and fee 0. Do not copy Flex action partition,
  gross amounts or withholding logic.

## 5. Stops

- [ ] 5.1 Add `share_count_change`, `unknown_operation` and the
  `PAPERLESS_DONE_TAG` check. Verify the scenario "Division and coupon in one
  notice".
- [ ] 5.2 Add the README lines: notices do not show the TTF, Ghostfolio cost
  prices exclude it, and the done tag clears only the blocking rows. Verify
  the scenario "Stop cleared".

## 6. Import, notification and schedule

- [ ] 6.1 Add the import with `DRY_RUN=0`, the strict readback
  (`import_unconfirmed`), the summary line and the exit codes. This is the
  first real Ghostfolio write: it runs only from an operation plan that Florent
  validated. Verify the scenarios "Second run" and "Unexpected import response"
  (the second one with mocked Ghostfolio responses in an offline test: empty
  list and changed quantity).
  Also reject partial, repeated and extra results and changed account, symbol,
  data source, date, type, price, fee or currency. Adapt the accepted-subset
  helper to require full exact confirmation. Stop all writes without retry
  on `import_unconfirmed`; never project an omitted buy into real holdings.
- [ ] 6.2 Add the failure notification and `CRON`, with the README sections and
  one README line on the notice copies in Paperless and paperless-gpt. Verify
  the scenarios "Failure notification" and "Invalid schedule".
  Adapt the isolated notification worker and validated numeric CRON mechanism.
  Never notify in simulation, including failures and invalid settings.

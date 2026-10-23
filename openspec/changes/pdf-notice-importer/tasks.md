# Tasks

Each task is one bead, one branch and one PR. "The run command" and "notice
documents" are defined in the spec. A task that needs a real PDF of a type that
is not yet in Paperless waits for that PDF. Tests use anonymized text of real
PDFs only. Paperless is read only; no task writes to it.

Adopt the complete applicable IBKR v3.0.0 core mapped in design.md.
Read its pinned source and coverage before each task. Preserve applicable
protections and tests, and record reasons for BD adaptations before coding.
Review later source updates separately. Do not mark a coverage row complete
until its BD scenario passes.
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
  single active Ghostfolio account. Read and validate the complete existing
  activity list before logging the BUY. Adapt the separate indexing and
  selection functions; keep network requests outside selection. Carry exact
  Decimal values through JSON reads and decisions. Add one offline test
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
  Adopt URL validation, redirect rejection and the 120-second account-read
  timeout. Reject incomplete, masked and invalid activity evidence with
  `activities_unavailable`; reject excluded targets. Verify "Unsafe activity
  evidence" and "Excluded target" with the real BUY fixture and mocked API.
  Check active flags, tags, current assetProfile precedence and legacy-only
  SymbolProfile compatibility. Exclude inactive/non-YAHOO holdings and manual
  matches. Verify "Future activity"; defer future source rows without writes.
- [ ] 1.3 Remove legacy-only scripts and `collector/`, `compose.lab.yaml`,
  `compose.broker-inspection.yaml`,
  `docs/verification/` and the remaining legacy tests. Remove CI calls that
  remain after task 1.1. Retain the current package/image/security checks and
  any adopted publication tooling. Remove `boursedirect_to_ghostfolio.py` after its
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
  namespace, or sorted normalized notice rows when absent. Preserve multiplicity;
  exclude file metadata and formatting. Verify "Regenerated notice" from the
  retained pair. Deduplicate source copies before dispatch. Add
  `owned_activity_conflict`, the manual match with exact
  price and `possible_duplicate`, with offline tests. Two identical rows in one
  notice give two activities. Verify in simulation with the run command: a real
  BUY that matches a manual Ghostfolio activity shows a duplicate.
  Adapt identity parsing to BD v3; do not copy the IBKR namespace or its
  source-specific identifiers. Keep legacy BD rows readable for matching.
  Reject unsupported or malformed reserved BD identities with `invalid_identity`
  before writes. Verify "Invalid identity" and "Moved identity". Index occupied
  BD identities across visible accounts, including inactive rows. Only the target
  account supports manual matches and holdings. Independent rows continue.
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
  first production Ghostfolio write: it needs an operation plan that Florent
  validated. Before production writes, qualify the candidate image digest in
  the existing infra empty/golden lab. Infra owns the BD launch/evidence
  adaptation; retain its target checks, snapshots, credential isolation and
  stop verification. Prove first creation, duplicate rerun, mixed legacy rows,
  chronological sells, exact readback and uncertain-result stop. Do not use
  IBKR cash/Flex assertions as BD proof. Verify "Second run" and
  "Unexpected import response"
  and "Delayed confirmation" with offline responses based on real notice rows.
  An empty POST response may succeed only after a complete exact GET confirms it.
  Wait five seconds after an uncertain response; never repeat that POST.
  Also reject partial, repeated and extra results and changed account, symbol,
  data source, date, type, price, fee or currency. Adapt the accepted-subset
  helper to require full exact confirmation. Stop all writes without retry
  on `import_unconfirmed`; never project an omitted buy into real holdings.
  Once the writer exists, rerun every startup/source/identity/amount/stop blocker
  with DRY_RUN=0 and prove zero POSTs. Until then, DRY_RUN=0 refuses before HTTP.
  Adapt the separate accepted-state function and structured preview evidence.
  Preserve exact Decimal values in the full preview and readback.
- [ ] 6.2 Add the failure notification and `CRON`, with the README sections and
  one README line on the notice copies in Paperless and paperless-gpt. Verify
  the scenarios "Failure notification" and "Invalid schedule".
  Adapt the isolated notification worker and validated numeric CRON mechanism.
  Never notify in simulation, including failures and invalid settings.
  Retain one fixed-code summary, bounded worker lifetime, secret-free worker
  ENV and notification failure isolation. Keep schedule and one-off image checks.

Existing release work adopts IBKR serialization, native amd64/arm64 checks,
immutable versions and digest verification. Build the candidate once, qualify
both existing lab scenarios on its digest, then publish the exact tested image
without rebuilding. No RC channel is required. Publication and production
activation retain separate GO. Keep tooling outside the behavior spec.

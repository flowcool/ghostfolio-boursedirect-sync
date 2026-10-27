# Tasks

Each task is one bead, one branch and one PR. "Run" and notice documents
are defined in the spec. Reuse retained real PDFs for offline and
lab acceptance before Paperless integration is available. Tests use anonymized
text of real PDFs. For an error case absent from the complete available archive,
verify the logged code, exit and write protection with explicit derived-data
regressions. No original for that absent case is required. Never alter original
PDFs or claim a real financial observation. Paperless is read only.

Adopt the complete applicable IBKR v3.0.0 core mapped in design.md.
Read its pinned source and coverage before each task. Preserve applicable
protections and tests, and record reasons for BD adaptations before coding.
Review later source updates separately. Do not mark a coverage row complete
until its BD scenario passes.
Use the installed Python package `ghostfolio_boursedirect_sync`, with typed
functions and data records. Pass strict mypy and Ruff as well as each task's
offline tests. Preserve Decimal and all BD spec rules when adapting source code.
These checks accompany each code task; they are not separate tooling tasks.
The shared labs use permanent scoped authority, including test writes/resets.
Reserve instances, isolate credentials, retain evidence, stop on uncertainty
without resend, then stop and verify. Production and publication retain separate
authority. Saved-PDF lab acceptance does not prove Paperless integration.

## 1. First real BUY in simulation

- [ ] 1.1 Gate the real BUY PDF first. Confirm that it has exactly one labelled
  account field. Remove spaces once and require full equality with
  `BD_ACCOUNT_REF`. Measure `QUANTITE x COURS - BRUT` exactly and report the
  result. Apply task 2.1 rounding when the product has fractional cents.
  If either gate fails, stop and report. Add the application package
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
  Adapt CI to install and check the new Python package and image.
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
- [x] 1.3 Remove legacy-only scripts and `collector/`, `compose.lab.yaml`,
  `compose.broker-inspection.yaml`,
  `docs/verification/` and the remaining legacy tests. Remove CI calls that
  remain after task 1.1. Retain the current package/image/security checks and
  any adopted publication tooling. Remove `boursedirect_to_ghostfolio.py` after its
  selected parser logic is covered in the package.
  Start this task only after task 1.1 is merged.
  Verify: CI is green, and the sum of lines in all application-package Python
  files is 2 500 or fewer. Tests and packaging metadata do not count.

## 2. Notice checks

- [x] 2.1 Add the amount checks (BUY, SELL and coupon) and `notice_unreadable`
  with the block of all writes, with offline tests from altered anonymized
  text. Compare HALF_UP(abs(quantity) * source price, EUR 0.01) exactly to BRUT.
  Preserve source quantity/price. Infer missing COURTAGE as zero only for BUY
  with explicit TVA=0 and Debit=BRUT; report `brokerage_zero_inferred`.
  Verify "Altered amount", "Rounded gross", "Omitted brokerage" and
  "Unreadable document" against retained notices; reject unproven omissions.

## 3. Security resolution

- [x] 3.1 Add the Ghostfolio lookup by ISIN, `unresolved_security` and the list
  of mapping lines to paste. Add the README mapping section. Verify the scenario
  "No EUR lookup result".

## 4. Sells, coupons and duplicates

- [x] 4.1 For each real PDF type used, record whether it shows a broker notice
  reference. Add the `BD#v3#` comment with that reference as the document
  namespace, or sorted normalized notice rows when absent. Preserve multiplicity;
  exclude file metadata and formatting. Verify "Regenerated notice" from the
  retained pair. Deduplicate source copies before dispatch. Add
  `owned_activity_conflict`, the manual match with exact
  price and `possible_duplicate`, with offline tests. Maximize exact manual
  matches first, then minimize total date distance. Cover competing matches
  and source copies without reserving manual rows for invalid or occupied
  sources. Two identical rows in one notice give two activities. Verify in simulation with the run command: a real
  BUY that matches a manual Ghostfolio activity shows a duplicate.
  Adapt identity parsing to BD v3; do not copy the IBKR namespace or its
  source-specific identifiers. Keep legacy BD rows readable for matching.
  Reject unsupported or malformed reserved BD identities with `invalid_identity`
  before writes. Verify "Invalid identity" and "Moved identity". Index occupied
  BD identities across visible accounts, including inactive rows. Only the target
  account supports manual matches and holdings. Independent rows continue.
- [x] 4.2 Add SELL rows, the sell guard on the running position and
  `custody_fee_ignored`, with an offline test (two sells that together exceed
  the position). Verify the scenarios "Sell without a position" and "Sell
  notice with a custody fee".
  Use Decimal and chronological rows, with SELL first on equal dates.
  When writes are enabled in task 6.1, only confirmed buys can support sells.
- [x] 4.3 Add COUPONS rows and the dividend match (exact `BD#`, or 3 days and
  same net amount without `BD#`, else `possible_duplicate`). Verify the scenarios "Real coupon in
  simulation" and "Coupon already in Ghostfolio".
  Keep quantity 1, net unit price and fee 0. Do not copy Flex action partition,
  gross amounts or withholding logic.

## 5. Stops

- [x] 5.1 Add `share_count_change`, `unknown_operation` and the
  `PAPERLESS_DONE_TAG` check. Verify the scenario "Division and coupon in one
  notice".
- [x] 5.2 Align README and guidance with the accepted TTF/fee policy.
  State that main describes an unqualified, unpublished v1 candidate and
  v0.1.1 is preview-only. Explain brokerage plus charged TTF, fee-exclusive
  average price, and the exact fee-only correction. Explain that the done tag
  clears only blocking rows. Verify "Stop cleared" through task 5.1 evidence.
  Task 5.1 owns that runtime proof. This documentation task references it;
  it does not own a second runtime gate.

## 6. Import, notification and schedule

- [x] 6.1 Add the import with `DRY_RUN=0`, the strict readback
  (`import_unconfirmed`), the summary line and the exit codes. This task
  qualifies writes in the shared labs. The first production write needs a
  separate operator-approved `Operation plan:` under
  [AGENTS.md](../../../AGENTS.md), Method, Operation beads. Qualify the image
  in the existing infra empty/golden lab. Infra owns the BD launch/evidence
  adaptation; retain its target checks, snapshots, credential isolation and
  stop verification. Prove first creation, duplicate rerun, mixed legacy rows,
  chronological sells, exact readback and uncertain-result stop. Add charged
  TTF attribution within source account/notice/date/ISIN; ambiguity suspends
  affected BUYs with `ttf_attribution_failed`, without blocking independent rows.
  Verify "Attributed TTF" from retained notice rows. For "Ambiguous TTF",
  apply the rule above for an error case absent from the complete available
  archive. Commit an offline application regression for a derived two-BUY
  same-day ambiguous-TTF case. Assert
  `ttf_attribution_failed`, exit 1 and zero POST/PUT calls with network forbidden.
  Label its data as derived; do not claim a real financial observation.
  Implement the approved fee-only correction for exactly one matching BUY
  whose fee is brokerage alone. Preserve all other fields and logical identity.
  Verify "Existing brokerage-only BUY", already-correct no-op, other-value
  conflicts, exact readback, uncertain stop and rerun without duplicate/tax
  recount. Check the exact upstream update API before implementation.
  Extend the existing Infra BD adapter for saved-PDF input and financial
  checks; no fake Paperless, new runner or Compose. Use the same image for
  DRY_RUN, empty creation/readback/rerun and golden preservation/correction.
  Real Ghostfolio lab HTTP remains necessary. Keep real Paperless integration
  a separate gate. Do not use
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

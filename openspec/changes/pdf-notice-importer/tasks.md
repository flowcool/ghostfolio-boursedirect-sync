# Tasks

Each task is one bead, one branch and one PR. "The run command" and "notice
documents" are defined in the spec. A task that needs a real PDF of a type that
is not yet in Paperless waits for that PDF. Tests use anonymized text of real
PDFs only. Paperless is read only; no task writes to it.

## 1. First real BUY in simulation

- [ ] 1.1 Replace the main Python file, `Dockerfile`, `entrypoint.sh`,
  `requirements.txt` and `compose.yaml` with the ibkr skeleton. Read the notice
  documents from Paperless, the BUY rows, the mapping file and the Ghostfolio
  account. Log the simulated BUY. Add one offline test from the anonymized text
  of the real BUY PDF and a README quick start. Verify:
  `docker compose up --abort-on-container-exit --exit-code-from boursedirect-sync`
  without a TTY and without `DRY_RUN`, with the real BUY PDF as the only notice
  document, shows `DRY RUN`, one BUY line and exit code 0.
- [ ] 1.2 Add the settings checks, `paperless_auth_failed`,
  `paperless_unreachable` and the README settings table. Verify the scenarios
  "Missing Paperless token", "Wrong Paperless token" and "Paperless down".
- [ ] 1.3 Remove the files that only the legacy code uses: `scripts/`,
  `collector/`, `compose.lab.yaml`, `compose.broker-inspection.yaml`,
  `docs/verification/` and the legacy tests. Update the CI workflows that call
  them. Verify: CI is green, and `wc -l` of the main Python file shows 2 500
  lines or fewer.

## 2. Notice checks

- [ ] 2.1 Add the amount checks and `notice_unreadable`, with offline tests from
  altered anonymized text. Verify the scenarios "Altered amount" and
  "Unreadable document".

## 3. Security resolution

- [ ] 3.1 Add the Ghostfolio lookup by ISIN, `unresolved_security` and the list
  of mapping lines to paste. Add the README mapping section. Verify the scenario
  "No EUR lookup result".

## 4. Sells, coupons and duplicates

- [ ] 4.1 Add the `BD#` comment, the manual match with exact price and
  `possible_duplicate`, with offline tests (two identical rows in one notice
  give two activities). Verify in simulation with the run
  command: a real BUY that matches a manual Ghostfolio activity shows a
  duplicate.
- [ ] 4.2 Add SELL rows, the sell guard and `custody_fee_ignored`. Verify the
  scenarios "Sell without a position" and "Sell notice with a custody fee".
- [ ] 4.3 Add COUPONS rows and the 3-day dividend match. Verify the scenarios
  "Real coupon in simulation" and "Coupon already in Ghostfolio".

## 5. Stops

- [ ] 5.1 Add `share_count_change`, `unknown_operation` and the
  `PAPERLESS_DONE_TAG` check. Verify the scenario "Division and coupon in one
  notice".
- [ ] 5.2 Add `ttf_found` and the README TTF section. Verify the scenarios
  "TTF row" (in simulation) and "Stop cleared".

## 6. Import, notification and schedule

- [ ] 6.1 Add the import with `DRY_RUN=0`, the strict readback
  (`import_unconfirmed`), the summary line and the exit codes. This is the
  first real Ghostfolio write: it runs only from an operation plan that Florent
  validated. Verify the scenarios "Second run" and "Unexpected import response"
  (the second one with a mocked Ghostfolio response in an offline test).
- [ ] 6.2 Add the failure notification and `CRON`, with the README sections and
  one README line on the notice copies in Paperless and paperless-gpt. Verify
  the scenarios "Failure notification" and "Invalid schedule".

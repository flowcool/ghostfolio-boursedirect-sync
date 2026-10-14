# Tasks

Each task is one bead, one branch and one PR. "The run command" is defined in
the spec. A task that needs a real PDF of a type that track A has not yet
downloaded waits for that PDF. Tests use anonymized text of real PDFs only.

## 1. First real BUY in simulation

- [ ] 1.1 Replace the main Python file, `Dockerfile`, `entrypoint.sh`,
  `requirements.txt` and `compose.yaml` with the ibkr skeleton. Read the PDF
  files of `NOTICE_DIR`, the BUY rows, the mapping file and the Ghostfolio
  account. Log the simulated BUY. Add one offline test from the anonymized text
  of the real BUY PDF and a README quick start. Verify:
  `docker compose up --abort-on-container-exit --exit-code-from boursedirect-sync`
  without a TTY and without `DRY_RUN`, with the real BUY PDF in `NOTICE_DIR`,
  shows `DRY RUN`, one BUY line and exit code 0.
- [ ] 1.2 Add the settings checks (`invalid_configuration`, `account_failed`)
  and the README settings table. Verify the scenario "Missing account name" with
  the run command.

## 2. Notice checks

- [ ] 2.1 Add the amount checks and `notice_unreadable`, with offline tests from
  altered anonymized text. Verify the scenarios "Altered amount" and
  "Unreadable file" with the run command.

## 3. Security resolution

- [ ] 3.1 Add the Ghostfolio lookup by ISIN, `unresolved_security` and the list
  of mapping lines to paste. Add the README mapping section. Verify the scenario
  "No EUR lookup result" with the run command.

## 4. Sells, coupons and duplicates

- [ ] 4.1 Add the `BD#` comment, the manual match with exact price and
  `possible_duplicate`, with offline tests. Verify in simulation with the run
  command: a real BUY that matches a manual Ghostfolio activity shows a
  duplicate.
- [ ] 4.2 Add SELL rows, the sell guard and `custody_fee_ignored`. Verify the
  scenarios "Sell without a position" and "Sell notice with a custody fee".
- [ ] 4.3 Add COUPONS rows and the 3-day dividend match. Verify the scenarios
  "Real coupon in simulation" and "Coupon already in Ghostfolio".

## 5. Stops

- [ ] 5.1 Add `share_count_change` and `unknown_operation`. Verify the scenario
  "Division and coupon in one notice".
- [ ] 5.2 Add `ttf_found` and the README TTF section. Verify the scenario
  "TTF row" in simulation with the run command.

## 6. Import, notification and schedule

- [ ] 6.1 Add the import with `DRY_RUN=0`, the summary line and the exit codes.
  This is the first real Ghostfolio write: it runs only from an operation plan
  that Florent validated. Verify the scenarios "Second run with the same files"
  and "Manual activity unchanged".
- [ ] 6.2 Add the failure notification and `CRON`, with the README sections.
  Verify the scenarios "Failure notification" and "Invalid schedule".

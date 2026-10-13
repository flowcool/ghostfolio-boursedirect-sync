# Tasks

Each checkbox owns one functional slice and its acceptance. Keep each reuse/adaptation bounded to about one hour; report if the first slice exceeds one fresh session. Include relevant README instructions and offline pytest parsing/mapping regressions with anonymized real fixtures in each slice, never a separate tooling/docs task.

All Compose checks below use private ENV and state, no TTY, and the service name `boursedirect-sync`. They describe future acceptance, not commands executed during planning. Broker login needs separate authorization; never create a failed live login for testing. Failure cases use retained evidence or offline fixtures. No new Ghostfolio lab or unapproved writes.

## 1. Real purchase through Compose

- [x] 1.1 Reuse the existing vault/login, selected-account notice path and BUY parser with sibling configuration/authentication to process one known real BUY with an explicit YAML entry. Touch `Dockerfile`, `compose.yaml`, `entrypoint.sh`, `boursedirect_to_ghostfolio.py`, bounded acquisition files and README. Check `docker compose up --build --abort-on-container-exit --exit-code-from boursedirect-sync` with `DRY_RUN=1`, empty `CRON` and explicit accounts: exact known BUY fields appear, no TTY, zero financial writes. Compare against the saved real notice; simulation must not mark it imported.

## 2. Safe unattended source selection

- [x] 2.1 Add one-time account discovery before destination/mapping validation, persistent login/discovery receipts and cross-service broker serialization. Touch acquisition, connector, Compose and README. Check the same Compose command with source reference omitted: copyable PEA/PEA-PME options, no holders/balances, nonzero configuration-required exit. Restart with the same state: zero login attempts. With a retained unresolved attempt, verify refusal without broker access; never clear existing uncertainty to pass acceptance.
- [ ] 2.2 Extend notice acquisition to the full rolling 90-day window, selected-account checks, logout and cleanup. Touch acquisition, connector and README. Check the Compose command with configured accounts and `DRY_RUN=1`: exact window bounds, observed calendar coverage (a confirmed empty month succeeds; a missing expected period, from retained evidence or offline fixture, exits nonzero before any financial write), zero monthly statements, no fallback account, zero financial writes.

## 3. Instruments and supported operations

- [ ] 3.1 Require readable YAML, accepting `{}`, and implement override → existing ISIN/profile → Ghostfolio lookup resolution. Touch connector, Compose, mapping example and README. Check Compose with a private empty mapping and `DRY_RUN=1`: uniquely resolved EUR symbols proceed; unresolved/ambiguous ISINs log candidate tickers, skip, continue valid rows and exit nonzero. Check a YAML override selects the configured candidate. Verify the installed Ghostfolio lookup read-only; do not install yfinance/OpenFIGI.
- [ ] 3.2 Extend the real BUY path to domestic/foreign SELL and coupon notices, dates, EUR evidence and explicit skips. Touch connector, anonymized real parsing/mapping fixtures and README. Check Compose with `DRY_RUN=1` over retained-observed forms: exact trade quantities/prices/brokerage, coupon credit as DIVIDEND, row dates at midnight UTC; no-ISIN and known out-of-scope rows log an error, skip and exit zero; unknown operations, unproved currency and nonzero TVA log an error, skip, continue valid rows and exit nonzero. Verify parsing/mapping offline with `.venv/bin/python -m pytest -q` on the relevant fixture tests.

## 4. Reconciliation and additive import

- [ ] 4.1 Adapt account-scoped notice identities, complete activity reading, exact duplicate/manual matching and DEGIRO's holdings guard. Touch connector and README. Check Compose in simulation against an already represented notice: no new proposal for it. With retained real insufficient-holdings evidence (or an offline anonymized mapping scenario), selling 50 with only 10 available stops the whole run, logs both quantities and writes nothing. Reconcile all proposals before enabling any POST; do not fund SELLs from skipped or merely submitted BUYs.
- [ ] 4.2 Wire `DRY_RUN=0` to sibling activities-only import, exact response/readback and durable uncertainty; retain `DRY_RUN=1` and absent-variable simulation. Touch connector, entrypoint and README. Check the Compose command with explicit and absent `DRY_RUN`: both simulate, with zero financial writes. A retained uncertain write refuses replay. For actual creation acceptance, only after separate write authorization run the same command with `DRY_RUN=0`, compare exact returned/readback fields, then repeat and observe zero new activities. Dry-run evidence alone does not complete actual-write acceptance; no new lab is required or authorized.

## 5. Scheduled unattended operation

- [ ] 5.1 Add sibling CRON validation, optional bounded Apprise failure alerts and final count/error summaries. Touch entrypoint, Compose, connector and README. Check `docker compose up --abort-on-container-exit --exit-code-from boursedirect-sync` with invalid `CRON`: fixed error and zero broker attempts. Check `docker compose up -d` with a valid schedule and `DRY_RUN=1`: scheduled nonoverlapping simulation logs. Verify discovery/login/write refusals remain effective on later scheduled runs; use only an explicitly authorized alert destination for delivery checks.

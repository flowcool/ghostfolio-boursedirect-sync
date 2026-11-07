# Maintenance

## Ghostfolio evidence

Before selection, the connector reads the complete activity list.
Review and correction recovery require fresh complete reads. The
reported count must equal the number of rows. Invalid, masked or incomplete
profiles stop with `activities_unavailable`.

The current `assetProfile` takes precedence over the legacy `SymbolProfile`.
Draft, excluded, future and non-YAHOO rows do not support holdings. Their
identities remain occupied for duplicate protection.

Selection uses the acquired evidence. Correction dispatch revalidates that evidence. Money uses exact `Decimal` values.

## Amounts and fees

The accepted v1 rule checks printed BRUT against quantity times unit price,
rounded to EUR cents with ROUND_HALF_UP. Source quantity and price stay exact.
Missing COURTAGE means zero only with explicit TVA zero and Debit equal to BRUT.
The connector reports that exception. Other amount differences reject the row.

Charged TTF belongs in BUY fees with brokerage. It needs exactly one BUY in the
same source account, notice, date and ISIN. Ambiguity logs
`ttf_attribution_failed` and suspends the affected BUYs;
independent operations continue. The connector never estimates tax from a rate.
Ghostfolio net performance includes fees. Its average price excludes fees; it
is not a fiscal cost basis.

An existing BUY can receive a fee-only correction when exactly one activity
matches account, date, security, quantity and unit price, and its fee is exactly
brokerage alone. The new fee is brokerage plus the attributed charged TTF.
Every other field and the logical identity stay unchanged. Exact readback must
confirm the result. An already-correct fee is a no-op. Other differences are
reported without correction. An uncertain result stops writes without resend.
The connector never deletes activities.

Corrections now require `ACTIVITY_REVIEW_FILE`, including with profile `off`.
Without it, an eligible TTF correction reports `review_evidence` and holds that
BUY. Independent imports can continue. This changes the v1 fee-correction setup.

Custody fees are ignored with `custody_fee_ignored`. The done tag clears only
`share_count_change` and `unknown_operation` for that document. A share-count
change logs an error and blocks the affected security. Other rows stay
subject to their normal checks.

## Operator review and reconciliation

Reconciliation is part of v2. Source-folder support is planned for v2.2.0.
The same financial checks apply to both sources.

Set `ACTIVITY_REVIEW_FILE=/review/activities.yaml` to retain proposals and
recovery evidence. The container runs as UID/GID `10001`. The parent directory
must already exist, belong to that user and have mode `0700`. Review files and
companions require mode `0600`. Keep the entire directory between runs. The
connector rejects links, input overlap, unsafe permissions and concurrent edits
with `review_unavailable` before financial writes. Paperless stays read only.

The YAML contains `reference_updates`, `activity_corrections`, groups and
conforming rows. Read the exact before and after values. Edit only the proposal's
`decision` between runs:

```yaml
decision: yes
```

Only literal `yes` approves an eligible proposal already present with unchanged
evidence. `true` does not approve it. Use `decision: reject` to reject a pair.
A changed source, destination or association clears stale consent. A cleared
choice does not immediately acquire automatic authority. A blocked proposal
remains blocked after `yes`. Held events cannot become new imports.

Corrections preserve the activity ID, owner, account, security, type,
tags and notes. BUY and SELL quantities stay unchanged. A coupon uses quantity
`1` and the validated net credit as price. The connector never merges, splits
or deletes activities. Groups and total amounts are diagnostic evidence only.
Conflicting ISINs and competing candidates hold the related events.

Profile `off` permits manual review, dedicated TTF corrections and pending
recovery without `TZ`. Other profiles require a review file and explicit IANA
`TZ`. Profiles never create a manual `yes`.

| Profile | Maximum gross difference | Maximum source-relative difference | Maximum date distance |
| --- | --- | --- | --- |
| `conservative` | 0 EUR | 0 | 0 days; recognized unique reference required |
| `balanced` | 0.01 EUR | 0.1% | 0 days |
| `permissive` | 1 EUR | 1% | 2 days for BUY/SELL; 3 for coupons |

Both amount limits must pass. Gross means exact quantity times price, without
fees. Fees require separate source validation. No exchange-rate or floating
point exception applies. Profiles compare the printed source date with the
destination calendar day in `TZ`. Manual notice proposals compare canonical
source and destination instants by calendar day in `TZ`. A stored manual
instant on the same local day stays unchanged.
New source dates and required date replacements use the printed date at midnight UTC.
West of UTC, midnight UTC can display on the previous local day. `TZ` must
match the Ghostfolio server timezone. It does not convert stored history.
Eligible pairs outside a profile limit remain available for manual review.

Legacy comments require reproducible event and account inputs before migration.
An eligible migration changes only the identity line and preserves notes after
a blank separator. Financial differences are evaluated on a later run. Missing
historical inputs report `review_evidence`; `yes` cannot replace them. Unchanged
legacy and manual duplicates do not require migration.

Manual, profile, migration and TTF work execute all eligible corrections in one
run. The oldest eligible proposal goes first, with a stable order for ties.
Each next PUT waits at least 150 seconds after the previous confirmed correction.
Exact readback must pass before the next PUT. A release can raise this delay when its
qualification margin no longer passes. No ENV setting changes this delay
or adds a count cap. Later approvals stay in the file if uncertainty stops the run.
Simulation shows `would correct` and sends no financial request.

Before a correction, the connector saves the exact request, before and after
values, and authority. It sends one PUT and checks all changed and preserved
fields. An uncertain result stops all later financial writes across restarts.
The connector does not resend the PUT. Only an exact readback settles it.
Simulation and profile changes cannot settle pending real work. Keep the review
file and its companion evidence; removing them is not a recovery procedure.

### Manual fees and coupons

A manual BUY or SELL can receive a fee-only proposal when account, security,
quantity and price match exactly within two calendar days in `TZ`. The notice
fee includes charged, uniquely attributed TTF for BUY. It includes brokerage
for SELL. Fees never select a pair. Every other stored field stays unchanged.

A manual coupon can match within 31 calendar days in either direction. Require
one source per target and one target per source across all available notices.
This is a payment hypothesis. Confirm it before setting `decision: yes`.
The proposal shows the exact net credit in EUR, quantity `1`, fee `0` and any
required date change. A wrong activity currency can change to EUR. The security
profile and its market currency stay unchanged. No exchange rate is inferred.

Profiles cannot approve these manual kinds. Missing review, competing pairs or
source holds cannot authorize a write or duplicate creation. Already corrected
rows need no further correction. The whole manual comment stays unchanged.

### Available-notice coverage

Set `IMPORT_CREATE_FROM=YYYY-MM-DD` to prevent creation of older notice rows.
The boundary day remains eligible. Dates must be valid ISO calendar dates.
Historical rows stay available for review and full notice coverage. The cut-off
does not approve corrections. Historical rows do not add simulated holdings.
Historical unsupported operations do not block recent creations. They remain
visible in coverage and retain historical review holds.

An unreadable notice normally blocks all writes. With a cut-off, only a valid
older Paperless document `created` date exempts it from this block. The importer
never uses the ingestion date or filename for this decision. Missing, invalid
or current dates retain the block. Paperless access failures remain failures.
Logs retain each exempt unreadable document and count excluded source rows and
documents with only historical rows. Source-copy rows count separately.
Coverage still reports unreadable originals and incomplete evidence.

Set `NOTICE_COVERAGE=1` for a report with no financial POST, PUT or DELETE.
It reads every selected original in either source, including Paperless done-tagged originals.
It does not open or settle the review journal. It preserves review decisions.
This rule also applies with `DRY_RUN=0` and existing approvals or pending work.

Local output shows conforming rows, correction candidates, unresolved
associations, absent supported rows and unsupported operations. Equal notice
copies count once. A normal import proposal alone does not prove absence.
Uncertain aliases, normalized quantities and foreign-price representations stay
unresolved. Unreadable originals or incomplete acquisition remain failures.

Position diagnostics compare net BUY-minus-SELL quantities within the stated
UTC interval. They describe unexplained movements, not absolute holding errors.
Unsupported transformations make the affected comparison unverifiable.
Notices cannot prove complete broker history. Empty periods, statement holdings
and missing opening acquisitions remain unverified. No opening BUY is invented.

## Outcomes and notifications

The run reports `success`, `success with user action required`, or `failure`.
`review_approval`, `review_evidence`, `coverage_gap` and `position_mismatch`
require action but keep exit code 0. Missing proof with a concrete resolution
action can report `coverage_unverifiable`. Informational history limits alone
do not request a correction or send an alert.
`review_unavailable` is a failure with exit code 1. Other existing failures
retain exit code 1. Custody fees and inferred zero brokerage are information.
The summary separates imports, simulations, duplicates, conforming rows,
corrections, migrations, holds and deferred work. Counts can overlap.

A failed run or required action sends at most one notification when
`APPRISE_URLS` is set, including in simulation.
The message contains fixed error codes. It contains no account data or secrets.
For example, set `APPRISE_URLS='["json://notification-service/hook"]'`.

Action summaries group unique events by fixed reason and count. The first,
changed or cleared group sends one summary. A cleared reason appears with count
zero. An unchanged group sends a reminder after seven days since confirmed
delivery. A same-count event replacement does not trigger another summary.
Failures notify each run. Clean runs without previous actions stay silent.
The private `<review-file>.normal.required-actions.yaml` and `<review-file>.coverage.required-actions.yaml`
companions beside `ACTIVITY_REVIEW_FILE`
store delivery counts and time only. Retain this private mount for reminders.
Without usable persistent state, actions remain eligible each run and a fixed
warning explains the missing state. Failed or uncertain delivery does not advance
its clock. Failed runs cannot certify cleared actions. Normal and coverage modes keep separate delivery state and reminder clocks. Full findings stay in the
local log on every run. Notification delivery uses a separate process.
The deadline covers process startup and delivery. On expiry, the process stops.
A timed-out notification can still arrive. The connector does not retry it.
Invalid notification settings stop before service access with `invalid_configuration`.
Delivery failure does not change the import exit code.

## Notice copies

Keep notice copies in Paperless; paperless-gpt can process those copies independently.
The connector reads original PDFs and never changes Paperless documents.

## Backups and routine checks

Stop the scheduled service before a manual run or review-file edit. Keep
originals, mapping, `.env`, review files and every journal companion together.
Verify a Ghostfolio backup before enabling writes. Read the cycle result and
notification result after each run. A green exit can still require user action.
For write uncertainty, follow [troubleshooting](troubleshooting.md). Never
remove recovery evidence to clear a hold.

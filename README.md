# Bourse Direct to Ghostfolio

Import original Bourse Direct PDF operation notices into one Ghostfolio account.
Use a read-only folder or an existing Paperless-ngx service. The importer has no
broker login and no vault access. It adds activities and prevents duplicates.
Simulation is the default. Paperless is always read only.

**v2.2.0 is unreleased.** Folder input and digest waivers require this candidate
or a later released bundle. The last stable release is v2.1.0. Its image does not
support folder input. Its immutable image is
`ghcr.io/flowcool/ghostfolio-boursedirect-sync:2.1.0@sha256:2949c5773dab862590a3dabbaf2bb52495d759f37c615f9cfdb72b66bbcd6c76`.
The release process replaces the bundle image reference
with its qualified digest. Do not use a v2.1.0 image to test the v2.2 instructions.

[Releases](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases) ·
[Questions and bugs](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues) ·
[Contribute](CONTRIBUTING.md) · [Changes](CHANGELOG.md)

## Install

Use Docker Engine and Compose v2 on Linux amd64 or arm64. Prepare a reachable
Ghostfolio instance and its backup procedure first. Keep the final service URL:
redirects are rejected before credentials can leave the configured origin.
Use HTTPS across hosts. Private HTTP is suitable only on your trusted network.
The connector requires complete, unmasked account and activity responses.
A release watcher baseline is not a minimum supported Ghostfolio version.
Use the retained lab receipt for the tested destination of each release;
compatibility with an untested version is not guaranteed.

### 1. Get the operator bundle

Download the versioned archive and `SHA256SUMS` from the selected
[release](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases).
Verify the checksum before extraction. Commands below use the extracted bundle.
They need no source checkout or local image build. Keep `IMAGE_DIGEST` with it.
It identifies the exact qualified image; keep the previous bundle for rollback.

```sh
sha256sum --check SHA256SUMS --ignore-missing
tar -xzf ghostfolio-boursedirect-sync-vX.Y.Z.tar.gz
cd ghostfolio-boursedirect-sync-vX.Y.Z
cp .env.example .env
chmod 600 .env
sudo install -d -m 0700 -o 10001 -g 10001 review
```

Use one installation directory and one service for each source/target account.
A second account needs separate `.env`, review directory and Compose project
(`COMPOSE_PROJECT_NAME`). Never share review journals between targets.

### 2. Set Ghostfolio and choose one source

In Ghostfolio, open **Account → Access → Security Token**. Keep that token
private. Set `GHOST_ACCESS_TOKEN` to it and leave `GHOST_TOKEN` empty. The importer
exchanges the Security Token for a session bearer on each run. A copied session
bearer in `GHOST_TOKEN` is an alternative, but it can expire between runs.
Set exactly one credential mode. Never put a token on a command line or in an issue.

Set `GHOST_HOST` and the exact `GHOST_ACCOUNT_NAME`. The account must be unique,
active and included in analysis. Use full account access, not restricted public
view access. Set `BD_ACCOUNT_REF` from the PDF account label, without spaces.

For a **folder**, set these values in `.env`:

```dotenv
COMPOSE_FILE=compose.yaml:compose.folder.yaml
NOTICE_DIR=/notices
NOTICE_DIRECTORY=./notices
PAPERLESS_URL=
PAPERLESS_TOKEN=
ACTIVITY_REVIEW_FILE=/review/activities.yaml
```

Create `notices` yourself. Put original PDFs directly in it. The container uses
UID/GID `10001`. Give that user read and traversal rights. For example:

```sh
mkdir -p notices
sudo chgrp 10001 notices
chmod 0750 notices
# After copying the originals:
sudo chgrp 10001 notices/*.pdf
chmod 0640 notices/*.pdf
```

Keep private originals outside Git. Mounts are read only and do not create host
paths. Files must contain 1 byte through 20 MiB. Selection is shallow and accepts
`.pdf` in any letter case. Other entries are ignored and counted. Selected links,
special files, empty files and oversized files block all financial writes.
Links in the source directory path are rejected. The importer does not move
files, change PDFs or create completion markers.

For **Paperless**, leave `NOTICE_DIR` and `NOTICE_WAIVER_FILE` empty. Use
`COMPOSE_FILE=compose.yaml`. Set `PAPERLESS_URL` and `PAPERLESS_TOKEN`.
Follow [Paperless setup](#paperless-setup) before the first simulation.

Keep `MAPPING_FILE` empty for automatic lookup. If an ISIN cannot resolve to one
EUR Yahoo symbol, verify that symbol in Ghostfolio. Copy
`config/mappings.example.yaml` to private `config/mappings.yaml`, replace the
synthetic entry, then set `MAPPING_FILE=/config/mappings.yaml`. Give GID 10001
read access as described in [mapping setup](config/README.md).

The base Compose uses the public image and normal Docker egress. For an existing
private Docker network, append `:compose.ghostfolio.yaml` to `COMPOSE_FILE`, set
`GHOSTFOLIO_NETWORK` to its exact name, and use reachable internal service URLs.
The override adds that network. It requires no fixed personal network name.
A source checkout can use `compose.build.yaml` for development; release users
must not need it. `BOURSEDIRECT_IMAGE` can select an immutable digest explicitly.

### 3. Simulate and inspect

Keep `DRY_RUN=1` and `CRON=` in `.env`. Validate without printing resolved secrets.
Pull the image, then force one non-interactive simulation:

```sh
docker compose config --quiet
docker compose pull
docker compose run --rm -T --no-deps -e DRY_RUN=1 -e CRON= importer
```

Read the exit status and each proposed date, type, symbol, quantity, price and
fee. Inspect the source-file/document counts, unreadable count and review/action
counts. Exit 0 can still require a user action. Preserve private logs locally.
Never share full financial logs or resolved Compose output.

Run coverage against the same source and account:

```sh
docker compose run --rm -T --no-deps -e NOTICE_COVERAGE=1 -e DRY_RUN=1 -e CRON= importer
```

Coverage sends no financial write. It does not open or settle a review journal.
It reports missing rows and unverifiable positions. A partial archive cannot
prove opening holdings or complete broker history.

The review directory belongs to UID/GID 10001. Read its private YAML with
`sudo less review/activities.yaml`. Edit only `decision` with
`sudoedit review/activities.yaml` between runs. Retain owner 10001 and mode 0600.
Keep the file and every companion together. A `yes` cannot bypass missing proof,
source stops or pending financial uncertainty. Profile `off` disables automatic
profiles; manual approved work, proved TTF corrections and recovery can still run.
Review every proposal before enabling writes. See [review rules](#operator-review-and-reconciliation).

### 4. Import once, verify, then schedule

Take and verify a Ghostfolio backup. Back up the complete private review directory
while the importer is stopped. Retain the original PDFs, mapping and `.env`.
Resolve unreadable files, security mapping and unexpected coverage findings first.
On a shared or managed destination, obtain its owner's approval before writes.

Run one deliberate import with the same inputs:

```sh
docker compose run --rm -T --no-deps -e DRY_RUN=0 -e CRON= importer
```

Require exit 0. Check Ghostfolio's exact activities and the final created,
corrected and held counts. The importer confirms each accepted write by exact
readback. If a result is uncertain, stop. Do not resend or delete journals.
Read [recovery](#troubleshooting) before another run.

After a confirmed import, repeat the same command once. Require zero new
activities and zero repeated corrections. File renaming, copies, relocation and
switching sources retain `BD#v3` financial identities. Identical bytes share a
`sha256:` document identity. Different bytes change source evidence; they do not
replace destination duplicate checks or authorize another activity.

Only then set `DRY_RUN=0`, an explicit `TZ` and `CRON` in `.env`, for example
`CRON=0 6 * * *`. Start with `docker compose up -d`. Check private logs and the
first scheduled result. Stop the scheduled service before a manual run. Do not
run two writers against one review directory. Reverting an image does not undo
accepted financial activities. Restore data only through your verified recovery
procedure, with the importer stopped and its journals retained.

## Supported inputs

| Supported | Limits |
| --- | --- |
| EUR PEA and PEA-PME original operation notices | No CTO or arbitrary account types; no statements or OCR scans |
| Text-bearing `ACHAT COMPTANT`, `ACHAT ETRANGER`, `VENTE COMPTANT`, `VENTE ETRANGER` | Exact supported layout and EUR values; foreign labels do not imply FX conversion |
| `COUPONS` | Validated net credit; quantity 1 and fee 0 in Ghostfolio |
| Charged TTF | One unambiguous BUY in the same notice/account/date/ISIN |
| `DROITS DE GARDE` | Reported and ignored; no activity |
| Corporate actions or unknown operations | Held and reported; no automatic transformation |

Missing earlier BUYs can hold a SELL with `sell_exceeds_holding`. Supply the
supported history or resolve opening positions independently. No opening BUY
is invented. This importer is not a complete fiscal ledger.

## Paperless setup

Paperless is optional. Use an existing Paperless-ngx service. Upload unchanged
original PDFs manually, or use a collector that you operate separately. This
project does not install the collector or manage its login.

Create a text custom field named `Source`. Set its exact value to `Bourse Direct`
on every intended notice. Assign a dedicated token user with global
`documents.view_document` permission and object visibility for the full intended
notice set. Give it global `documents.view_tag` and visibility of the configured
waiver tag (`ghostfolio-done` by default). Tag access does not grant document
access. Give no add/change/delete permission. Generate its API token and store
it only in `.env`. Follow the
[Paperless permissions documentation](https://docs.paperless-ngx.com/usage/#permissions).

Check the visible selected count against your own inventory. Check original
downloads, not OCR output or thumbnails. The importer uses all selected pages
and `download/?original=true`. It also checks `BourseDirect_` filenames without
Source metadata. Hidden documents cannot be diagnosed by this token; a successful
run proves only the visible source set. The importer never sets done tags.
A tag waives that document's share-count/unknown-operation stop only. It does
not waive an unreadable PDF, missing evidence or financial checks.

## Troubleshooting

| Code or symptom | Action |
| --- | --- |
| `invalid_configuration` | Read the named setting. Use exactly one source and one Ghostfolio credential; check final URLs and one active unique target. |
| `paperless_auth_failed` (401/403) | Verify the token user, `view_document`, intended document visibility, `view_tag` and waiver-tag visibility. Do not grant superuser or write access. |
| `paperless_unreachable` | Check the final URL, network, TLS and response shape. Redirects are refused. |
| `source_field_missing` | Set `Source = Bourse Direct` on the intended originals yourself. |
| `notice_source_unavailable` | Restore directory readability or finish the source copy. Keep input stable during acquisition and dispatch. |
| `notice_unreadable` | Preserve the original. Privately check text extraction, account label, printed dates, known layout and all required fields. It blocks all financial writes. |
| `unresolved_security` | Verify one EUR Yahoo ticker and add the optional mapping; this is separate from unreadable-PDF recovery. |
| `review_unavailable` | Check private ownership/modes, source separation and companion files. Stop writers before editing. |
| `import_unconfirmed` | Stop writes. Preserve the journal and obtain complete exact destination readback. Never resend an uncertain request. |
| `share_count_change` / `unknown_operation` | Inspect the unsupported operation. Waive only the exact document/code after independent review; other guards remain. |

For a permanently unreadable folder notice, move it outside `NOTICE_DIR` yourself
and record the file, reason and move in your private records. Preserve the original.
This hides the notice from coverage. It does not prove complete history. The
importer never moves it. Old filenames and mtimes cannot exempt unreadable folder
files. Printed dates control `IMPORT_CREATE_FROM`, including the boundary day.
Only Paperless has the narrow older-`created` unreadable exemption described below.

An optional folder waiver file uses this exact UTF-8 format:

```text
sha256:<64 lowercase hexadecimal digits> share_count_change
sha256:<64 lowercase hexadecimal digits> unknown_operation
```

Replace each placeholder with `sha256sum` of the reviewed original. Use one ASCII
space, one code per line, no comments and no duplicate pairs. Blank lines are
allowed. The file must be regular, readable, outside the notice directory and
separate from all review paths. Links and inode aliases are refused. The limit
is 65,536 bytes. Append `:compose.waivers.yaml` to `COMPOSE_FILE`, set
`NOTICE_WAIVER_FILE=/notice-waivers.txt` and `NOTICE_WAIVER_PATH` to your existing
host file. Mount it read only. Malformed files fail before service access.
Unknown digests are counted and ignored. Renaming preserves a waiver; changed
bytes need a new exact entry. A waiver cannot bypass any other guard.

For support, open a [GitHub issue](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues).
Share version/digest, architecture, source mode, relevant service versions, fixed
codes, exit status and a sanitized reproduction. Keep originals, holder fields,
account identifiers, review files and full logs private. Report vulnerabilities
through the [private security process](.github/SECURITY.md).

## Settings

| Variable | Required | Meaning |
| --- | --- | --- |
| `GHOST_HOST` | yes | Ghostfolio HTTP(S) origin without credentials, query or fragment |
| `GHOST_TOKEN` or `GHOST_ACCESS_TOKEN` | one | Ghostfolio bearer or security token |
| `GHOST_ACCOUNT_NAME` | yes | Exact name of one active Ghostfolio account |
| `BD_ACCOUNT_REF` | yes | Exact account reference from the notice, without spaces |
| `PAPERLESS_URL` | Paperless only | Paperless HTTP(S) origin |
| `PAPERLESS_TOKEN` | Paperless only | Read-only Paperless token |
| `NOTICE_DIR` | folder only | Absolute container path; excludes both Paperless settings |
| `NOTICE_WAIVER_FILE` | no | Folder-only absolute read-only stop-waiver file; see recovery |
| `PAPERLESS_DONE_TAG` | no | Tag name, default `ghostfolio-done` |
| `MAPPING_FILE` | no | Read-only YAML mapping file; empty allows no override |
| `DRY_RUN` | no | Absent or `1` simulates; `0` enables imports |
| `IMPORT_CREATE_FROM` | no | Optional `YYYY-MM-DD`; never create rows before this trade/payment date; absent or empty disables the cut-off |
| `TZ` | for a non-off profile | Explicit IANA timezone for destination date comparison and scheduling; source dates stay UTC |
| `NOTICE_COVERAGE` | no | `1` reads all available notices and reports coverage; sends no financial write even with `DRY_RUN=0`; default `0` |
| `ACTIVITY_REVIEW_FILE` | no | Private writable YAML path inside the container, for example `/review/activities.yaml` |
| `ACTIVITY_RECONCILIATION` | no | `off` by default; or `conservative`, `balanced`, `permissive` |
| `ACTIVITY_REVIEW_DIRECTORY` | Compose only | Host directory mounted at `/review`; default `./review` |
| `CRON` | no | Five numeric schedule fields; empty runs once |
| `APPRISE_URLS` | no | JSON list of Apprise destination URLs; empty or `[]` disables delivery |
| `APPRISE_TIMEOUT` | no | Notification deadline in seconds, from 1 to 30; default 10 |
| `LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |

The connector rejects redirects before it sends a credential. It uses a
120-second timeout for the Ghostfolio account read. It never logs response
bodies or secrets.

## Paperless selection

The connector reads every page matching `Source = Bourse Direct`. It also
checks filenames beginning with `BourseDirect_`. A matching file without the
Source field stops the run before any Ghostfolio account read.

Each original PDF is downloaded with `original=true`. Paperless errors use
fixed codes:

- `paperless_auth_failed` for HTTP 401 or 403;
- `paperless_unreachable` for network, redirect, malformed or other HTTP errors;
- `source_field_missing` for a Bourse Direct filename without the Source field.

## Mapping

When `MAPPING_FILE` is set, it must contain a `symbol_mapping` object:

```yaml
symbol_mapping:
  FR0000000002: VERIFIED.PA
```

The mapping file is read only. A mapped ISIN takes priority over lookup.
For each unmapped ISIN, the connector queries Ghostfolio once per run.
It accepts exactly one EUR result from the YAHOO data source.

If lookup fails or has no single EUR result, the connector skips that ISIN.
Other resolved securities continue. The run exits with code 1 and logs
`unresolved_security` with one mapping line per ISIN:

```text
symbol_mapping: 'FR0000000002: <yahoo ticker>'
```

Lookup failures also report a fixed transport, HTTP or invalid-response reason.
A valid lookup with no single EUR result does not report a lookup failure.

Verify the EUR Yahoo ticker in Ghostfolio. Replace `<yahoo ticker>` with that
ticker. Add the `ISIN: TICKER` line under `symbol_mapping` in the YAML file.
Then run the connector again. A missing or invalid file stops the run with
`invalid_mapping`. Leave `MAPPING_FILE` empty to use lookup without a file.

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
Each next PUT waits at least 120 seconds after the previous confirmed correction.
Exact readback must pass before the next PUT. A new release raises D when the
lab margin no longer passes. No ENV setting changes this delay
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

## Development checks

```sh
.venv/bin/python -m ruff check ghostfolio_boursedirect_sync
.venv/bin/python -m mypy --strict ghostfolio_boursedirect_sync
.venv/bin/python -m pytest -q
```

The retained fixtures contain anonymized text from real Bourse Direct notices.
Private originals and runtime state stay outside Git. An error case absent
from the complete available archive does not require another original for
delivery. Explicit derived-data regressions check its error log and protection.
They do not establish a real financial observation.

Qualification uses saved real PDFs with the installed candidate and the existing
Infra empty and golden labs. This proves financial behavior without broker or
Paperless access. It still uses real Ghostfolio lab requests. Paperless service
integration is a separate gate. Both scenarios must pass on the same candidate
image before release. Lab tooling stays in Infra.

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

## Schedule

Leave `CRON` empty to run once. Set `CRON='0 6 * * *'` to run daily at 06:00.
Start the scheduled service with `docker compose up -d`.
Use `TZ` to select the schedule timezone. Source activity dates stay at midnight UTC.
The connector accepts five numeric fields with `*`, `/`, `,` and `-`.
It rejects invalid schedules with `Invalid CRON` and exit code 1.
It rejects names, macros, extra fields and shell commands.

## Notice copies

Keep notice copies in Paperless; paperless-gpt can process those copies independently.
The connector reads original PDFs and never changes Paperless documents.

## License

The project uses the [MIT NON-AI License](LICENSE). It includes additional
restrictions and is not the standard MIT license. Read it before use or contribution.

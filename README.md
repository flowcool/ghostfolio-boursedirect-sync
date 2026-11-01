# Bourse Direct to Ghostfolio

**Status: v1.0.0 published and qualified in the shared labs.**

The published image passed 19 financial scenarios in the empty and golden labs.
Real Paperless acceptance passed the default BUY simulation, source error checks
and one failure notification to an isolated local receiver. The Paperless checks
sent no financial request. The default mode remains simulation.
BillCollector has delivered original notices to Paperless through its daemon.
The first approved production import and its immediate repeat passed.
The repeat added no activity. Scheduled production imports still need setup.
Infra owns production host files and scheduled-service deployment.
A production financial write requires operator approval.
**v0.1.1 is a legacy preview only**. It does not import activities or provide
the v1 unattended service.

Release preparation follows the IBKR release chain. Run the manual
`Prepare release candidate image` workflow on `main` with the intended
`vX.Y.Z` version. It builds `amd64` and `arm64` once. It checks each native
image, then signs the candidate index. This step writes candidate images to
GHCR. It does not publish a stable version or change `latest`.

Qualify that exact index in the empty and golden labs. Keep the
`candidate-image.json` artifact. Add `labs.empty` and `labs.golden` to its
record. Each entry must contain `status: PASS`, `cleanup: stopped`, and the
`evidence_sha256` of its retained proof. Attach the completed record as
`lab-qualification.json` to the prepared stable GitHub release. Tag the exact
candidate source commit. Publish the release only after operator approval.
The release workflow checks the record and signature, then copies the exact
index to the version tag. It changes `latest` only for the current stable
release. It verifies both tags by digest. It never rebuilds the image.
No RC channel is required. A failed or partial publication stops the workflow;
inspect retained evidence before recovery. Never overwrite a version tag.
The release keeps the digest-pinned Compose archive, `IMAGE_DIGEST` and
`SHA256SUMS`. See the [release procedure](docs/operations/releasing.md).

This Docker connector reads Bourse Direct operation notices from Paperless.
It reads BUY, SELL and coupon activities for one active Ghostfolio account.

The connector reads Paperless only. It has no Bourse Direct login and no vault
access. `billcollector-recipes` owns the provider recipe. BillCollector owns
the engine, broker login and vault access. Infra deploys collection and the
Paperless delivery workflow.
Use the BillCollector [runtime contract](docs/upstreams.md#billcollector-acquisition) to prepare
Paperless delivery and verify each archived original.

## Quick start

Use one Compose service for one Bourse Direct account. Copy `.env.example` to
`.env` and set the required values. Keep `.env` private with mode `0600`.

```sh
chmod 600 .env
sudo install -d -m 0700 -o 10001 -g 10001 review
docker compose run -T --no-deps importer; echo "exit=$?"
```

The default mode is simulation. It prints each proposed activity and sends no
Ghostfolio write. Set `DRY_RUN=0` only after the separate write acceptance is
complete.

The container uses the latest qualified stable Python release and `pdftotext`.
It has no browser, Node or vault client. Paperless documents must have the custom
field `Source` with the exact value `Bourse Direct`. A filename starting with
`BourseDirect_` without that field stops the run with `source_field_missing`.

The published legacy preview has this immutable image reference:
`ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.1@sha256:486cc5ef8b3dde9e65b2b502789b65c9d956acb4ea03e3e2544c316d2bbef231`.

## Settings

| Variable | Required | Meaning |
| --- | --- | --- |
| `GHOST_HOST` | yes | Ghostfolio HTTP(S) origin without credentials, query or fragment |
| `GHOST_TOKEN` or `GHOST_ACCESS_TOKEN` | one | Ghostfolio bearer or security token |
| `GHOST_ACCOUNT_NAME` | yes | Exact name of one active Ghostfolio account |
| `BD_ACCOUNT_REF` | yes | Exact account reference from the notice, without spaces |
| `PAPERLESS_URL` | yes | Paperless HTTP(S) origin |
| `PAPERLESS_TOKEN` | yes | Read-only Paperless token |
| `PAPERLESS_DONE_TAG` | no | Tag name, default `ghostfolio-done` |
| `MAPPING_FILE` | no | Read-only YAML mapping file; empty allows no override |
| `DRY_RUN` | no | Absent or `1` simulates; `0` enables imports |
| `TZ` | for a non-off profile | Explicit IANA timezone for destination date comparison and scheduling; source dates stay UTC |
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

The reconciliation implementation is under qualification. The published v1
image does not contain this interface. Use the candidate only in an isolated lab until its native checks pass.

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

Corrections preserve the activity ID, owner, account, security, type, EUR,
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
point exception applies. Date comparison keeps the printed source day and uses
the destination day in `TZ`. Writes use the printed date at midnight UTC.
Eligible pairs outside a profile limit remain available for manual review.

Legacy comments require reproducible event and account inputs before migration.
An eligible migration changes only the identity line and preserves notes after
a blank separator. Financial differences are evaluated on a later run. Missing
historical inputs report `review_evidence`; `yes` cannot replace them. Unchanged
legacy and manual duplicates do not require migration.

Manual, profile, migration and TTF work share a limit of one correction per run.
The oldest eligible proposal goes first, with a stable order for ties. Deferred
choices remain in the file. New imports have no correction-budget limit.
Simulation shows `would correct` and sends no financial request.

Before a correction, the connector saves the exact request, before and after
values, and authority. It sends one PUT and checks all changed and preserved
fields. An uncertain result holds all writes to that account across restarts.
The connector does not resend the PUT. Only an exact readback settles it.
Simulation and profile changes cannot settle pending real work. Keep the review
file and its companion evidence; removing them is not a recovery procedure.

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
`review_approval` and `review_evidence` require action but keep exit code 0.
`review_unavailable` is a failure with exit code 1. Other existing failures
retain exit code 1. Custody fees and inferred zero brokerage are information.
The summary separates imports, simulations, duplicates, conforming rows,
corrections, migrations, holds and deferred work. Counts can overlap.

A failed run or required action sends at most one notification when
`APPRISE_URLS` is set, including in simulation.
The message contains fixed error codes. It contains no account data or secrets.
For example, set `APPRISE_URLS='["json://notification-service/hook"]'`.

Unresolved actions repeat on later runs. Clean runs stay silent. Notification delivery uses a separate process.
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

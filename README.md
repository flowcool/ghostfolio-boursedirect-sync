# Bourse Direct to Ghostfolio

This Docker connector reads Bourse Direct operation notices from Paperless.
It reads BUY, SELL and coupon activities for one active Ghostfolio account.

The connector reads Paperless only. It has no Bourse Direct login and no vault
access. BillCollector downloads and publishes the notices.

## Quick start

Use one Compose service for one Bourse Direct account. Copy `.env.example` to
`.env` and set the required values. Keep `.env` private with mode `0600`.

```sh
chmod 600 .env
docker compose run --rm -T importer; echo "exit=$?"
```

The default mode is simulation. It prints each proposed activity and sends no
Ghostfolio write. Set `DRY_RUN=0` only after the separate write acceptance is
complete.

The container uses the latest qualified stable Python release and `pdftotext`.
It has no browser, Node or vault client. Paperless documents must have the custom
field `Source` with the exact value `Bourse Direct`. A filename starting with
`BourseDirect_` without that field stops the run with `source_field_missing`.

Existing release checks keep this stable image reference:
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
| `TZ` | no | Container timezone for scheduling; activity dates stay UTC |
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

Before selection, the connector reads the complete activity list once. The
reported count must equal the number of rows. Invalid, masked or incomplete
profiles stop with `activities_unavailable`.

The current `assetProfile` takes precedence over the legacy `SymbolProfile`.
Draft, excluded, future and non-YAHOO rows do not support holdings. Their
identities remain occupied for duplicate protection.

All selection is offline after the reads. Money uses exact `Decimal` values.

## Development checks

```sh
.venv/bin/python -m ruff check ghostfolio_boursedirect_sync
.venv/bin/python -m mypy --strict ghostfolio_boursedirect_sync
.venv/bin/python -m pytest -q
```

The retained fixtures contain anonymized text from real Bourse Direct notices.
Private originals and runtime state stay outside Git.

## Failure notifications

With `DRY_RUN=0`, a failed run sends one notification when `APPRISE_URLS` is set.
The message contains fixed error codes. It contains no account data or secrets.
For example, set `APPRISE_URLS='["json://notification-service/hook"]'`.

Simulation never sends a notification, including failures and invalid settings.
Successful runs stay silent. Notification delivery uses a separate process.
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

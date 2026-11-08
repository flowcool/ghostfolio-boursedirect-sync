# Configuration

## Settings

| Variable | Required | Meaning |
| --- | --- | --- |
| `GHOST_HOST` | yes | Ghostfolio HTTP(S) origin without credentials, query or fragment |
| `GHOST_TOKEN` or `GHOST_ACCESS_TOKEN` | one | Ghostfolio bearer or security token |
| `GHOST_ACCOUNT_NAME` | yes | Exact name of one active Ghostfolio account |
| `BD_ACCOUNT_REF` | yes | Reference after `COMPTE N°`, without spaces, `EUR` or the account type; see [account setup](getting-started.md#2-set-ghostfolio-and-choose-one-source) |
| `PAPERLESS_URL` | Paperless only | Paperless HTTP(S) origin |
| `PAPERLESS_TOKEN` | Paperless only | Read-only Paperless token |
| `NOTICE_DIR` | folder only | Absolute container path; excludes both Paperless settings |
| `NOTICE_WAIVER_FILE` | no | Folder-only absolute read-only stop-waiver file; see recovery |
| `PAPERLESS_DONE_TAG` | no | Tag name, default `ghostfolio-done` |
| `MAPPING_FILE` | no | Read-only YAML mapping file; empty allows no override |
| `DRY_RUN` | no | Absent or `1` simulates; `0` enables imports |
| `IMPORT_CREATE_FROM` | no | Optional `YYYY-MM-DD`; never create rows before this trade/payment date; absent or empty disables the cut-off |
| `TZ` | for a non-off profile | IANA timezone for destination date comparison and scheduling; Compose defaults to `Europe/Paris`; source dates stay UTC |
| `NOTICE_COVERAGE` | no | `1` reads all available notices and reports coverage; sends no financial write even with `DRY_RUN=0`; default `0` |
| `ACTIVITY_REVIEW_FILE` | no | Private writable YAML path inside the container, for example `/review/activities.yaml` |
| `ACTIVITY_RECONCILIATION` | no | `off` by default; or `conservative`, `balanced`, `permissive` |
| `BOURSEDIRECT_IMAGE` | Compose only | Empty uses the qualified image in Compose; otherwise set a version or digest |
| `COMPOSE_FILE` | Compose only | Base Compose and selected source/network overrides |
| `COMPOSE_PROJECT_NAME` | Compose only | Distinct service project for each source/target |
| `GHOSTFOLIO_NETWORK` | private network only | Existing network used by `compose.ghostfolio.yaml` |
| `NOTICE_DIRECTORY` | Compose folder only | Existing host directory mounted read only at `NOTICE_DIR` |
| `NOTICE_WAIVER_PATH` | Compose waiver only | Existing host file mounted read only at `NOTICE_WAIVER_FILE` |
| `ACTIVITY_REVIEW_DIRECTORY` | Compose only | Host directory mounted at `/review`; default `./review` |
| `CRON` | no | Five numeric schedule fields; empty runs once |
| `APPRISE_URLS` | no | JSON list of Apprise destination URLs; empty or `[]` disables delivery |
| `APPRISE_TIMEOUT` | no | Notification deadline in seconds, from 1 to 30; default 10 |
| `LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` |

The connector rejects redirects before it sends a credential. It uses a
120-second timeout for the Ghostfolio account read. It never logs response
bodies or secrets.

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
Map every selected ISIN to freeze the symbols across simulation, import and
repeat. Keep the same file for all three runs. Live lookup can return different
results between runs. For foreign shares bought in EUR, follow the
[EUR listing guide](troubleshooting.md#foreign-shares-bought-in-eur).
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

## Schedule

Leave `CRON` empty for a one-off `docker compose run --rm` command.
Use `docker compose up -d` only with a nonempty valid `CRON`.
Set `CRON='0 6 * * *'` to run daily at 06:00.

The service uses `restart: unless-stopped`. Docker restarts it after every exit,
including exit 0. With empty `CRON`, `up` repeatedly runs the one-off import.
With invalid `CRON`, it repeatedly exits and can send a failure notification on
each restart. If logs show `Invalid CRON`, run `docker compose stop importer`.
Correct `.env`, validate it and recreate the service with
`docker compose up -d importer`. Use the one-off command for manual work;
`docker compose run --rm` does not apply the service restart policy.
Use `TZ` to select the schedule timezone. Source activity dates stay at midnight UTC.
The connector accepts five numeric fields with `*`, `/`, `,` and `-`.
It rejects invalid schedules with `Invalid CRON` and exit code 1.
It rejects names, macros, extra fields and shell commands.

## Timezone and log output

Compose and `.env.example` default `TZ` to `Europe/Paris`. Set it to the
Ghostfolio server's IANA zone before imports or reconciliation. Each run logs
`Activity comparison TZ=...; must match the Ghostfolio server TZ`.
A direct Python run without `TZ` keeps the existing UTC comparison fallback.
This setting does not convert historical activities. Source dates stay at
midnight UTC. A server west of UTC can display them on the previous local day.

The container prints static `BD SYNC` art, `Bourse Direct -> Ghostfolio`, and
its version and 12-character commit. Each run logs the identity again.
Unknown build revisions display `unknown`. Logs use a timestamp and `[LEVEL]`.
INFO and DEBUG use stdout. WARNING, ERROR and CRITICAL use stderr.
`LOG_LEVEL` controls the threshold. urllib3 request DEBUG logs stay disabled.
Failures use fixed codes and allowlisted setting or HTTP context. Arbitrary
exception text is omitted from logs and notifications.
An absent `DRY_RUN` warns `DRY_RUN not set: simulation, nothing written`.
Use explicit `DRY_RUN=1` for a deliberate simulation.

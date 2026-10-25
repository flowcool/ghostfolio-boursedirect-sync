# Bourse Direct to Ghostfolio

This Docker connector reads Bourse Direct operation notices from Paperless.
It proposes BUY activities for one active Ghostfolio account.
Later tasks add SELL, coupon, notification and schedule support.

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

The container uses Python 3.14 and `pdftotext`. It has no browser, Node or
vault client. Paperless documents must have the custom field `Source` with the
exact value `Bourse Direct`. A filename starting with `BourseDirect_` without
that field stops the run with `source_field_missing`.

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
| `DRY_RUN` | no | Absent or `1` simulates; `0` enables the later writer |
| `TZ` | no | Container timezone for later scheduling |
| `CRON` | no | Later schedule; empty runs once |
| `APPRISE_URLS` | no | Later failure notification destinations |
| `APPRISE_TIMEOUT` | no | Later notification timeout in seconds |
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

The mapping is read only. Later security resolution also checks Ghostfolio for
one EUR result. An unresolved ISIN is reported and is never written.

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

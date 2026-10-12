<div align="center">

# Bourse Direct → Ghostfolio

**Your operation notices. A clear dry run. Your data stays yours.**

[![Release](https://img.shields.io/github/v/release/flowcool/ghostfolio-boursedirect-sync)](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/latest)
[![Offline tests](https://github.com/flowcool/ghostfolio-boursedirect-sync/actions/workflows/offline-tests.yml/badge.svg)](https://github.com/flowcool/ghostfolio-boursedirect-sync/actions/workflows/offline-tests.yml)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](#quick-start)
[![AMD64](https://img.shields.io/badge/platform-linux%2Famd64-blue)](#requirements)
[![Preview only](https://img.shields.io/badge/financial_writes-none-success)](#what-you-get)
[![License](https://img.shields.io/github/license/flowcool/ghostfolio-boursedirect-sync)](LICENSE)

[Quick start](#quick-start) · [Configuration](#configuration) · [Results](#reading-the-results) · [Troubleshooting](#troubleshooting) · [Contributing](CONTRIBUTING.md)

</div>

Connect to Bourse Direct, choose your PEA or PEA-PME and an existing Ghostfolio
account, then review the operation notices from the last **90 days**. The connector
saves the original documents and a detailed report in a persistent Docker volume.

**v0.1.0 delivers acquisition and preview.** It does not add, change or delete
financial records in Ghostfolio. Differences in existing records appear in the
dry run for you to review.

## What you get

```text
Bitwarden → Bourse Direct → 90 days of operation notices
                                  ↓
                  Ghostfolio snapshot + dry run
                                  ↓
                   Terminal summary + saved files
```

| Feature | v0.1.0 |
| --- | --- |
| Source accounts | PEA and PEA-PME; one account pair per persistent state volume |
| Documents | Operation notices offered within the rolling 90-day window |
| Preview | EUR buys, sells and dividends; differences and unsupported operations reported |
| Dividends | Amount actually received, using the Bourse Direct booking date |
| General fees / rows without ISIN | Skipped |
| Account selection | Explicit configuration, or a terminal choice retained for later runs |
| Retention | Original HTML, receipts, snapshots, reports and recovery journals |
| Financial writes / automatic scheduling | None |

No monthly statement cross-check is required. Currency and security mappings
must be explicit: the connector does not guess them or automatically convert
corporate actions such as subscription rights. A 90-day window is not a complete
account history. ARM is outside this release's supported connection path.

## Requirements

- Linux on Intel/AMD (**AMD64**) with Docker Engine and Docker Compose v2.
- A Bitwarden-compatible HTTPS vault with a personal API key and master password.
- One uniquely named login item containing your Bourse Direct login, password and
  TOTP setup, normally named `boursedirect.fr`.
- Ghostfolio, an existing destination account and its long-lived **Security Token**.
- About 1.5 GiB of container memory; outbound access to the vault, broker and
  configured Ghostfolio origin.

The release includes the qualified browser and Bitwarden CLI. No local Python,
Node.js, browser installation, Docker socket mount or published port is needed.

## Quick start

Download **`ghostfolio-boursedirect-sync-v0.1.0.tar.gz`** and **`SHA256SUMS`** from
[the release](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/tag/v0.1.0),
then run:

```bash
sha256sum -c SHA256SUMS
tar -xzf ghostfolio-boursedirect-sync-v0.1.0.tar.gz
cd ghostfolio-boursedirect-sync-v0.1.0
cp .env.example .env
chmod 600 .env
```

Fill in `.env` using the settings below, then:

```bash
docker compose pull
docker compose run --rm bitwarden connect
```

The service is named **`bitwarden`**. Keep the terminal attached on the first run:
if accounts are not configured, it presents the available accounts and saves
your selection. Configured values are respected; a conflict with the saved pair
stops the run instead of changing accounts.

The Compose project pins `ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0`.
Keep `collector/browser-seccomp.json` beside the Compose files; it is included in
the archive and required by the browser sandbox.

## Configuration

| Setting | Purpose |
| --- | --- |
| `BW_SERVER` | Canonical HTTPS vault origin; default `https://vault.bitwarden.com` |
| `BW_CLIENTID`, `BW_CLIENTSECRET` | Bitwarden personal API credentials |
| `BW_PASSWORD` | Vault master password |
| `BW_ITEM_NAME` | Exact, unique login-item name; default `boursedirect.fr` |
| `GHOSTFOLIO_ORIGIN` | Ghostfolio HTTPS origin, without path, query or fragment |
| `GHOSTFOLIO_SECURITY_TOKEN` | Permanent Security Token; not an expiring JWT |
| `BD_SOURCE_ACCOUNT_REF` | Optional exact source reference, for example `ABC12345 PEA` |
| `GHOSTFOLIO_ACCOUNT_ID` | Optional existing destination account ID |
| `BOURSEDIRECT_IMAGE` | Optional image override for a deliberate upgrade or rollback |

Source and destination settings remain visible in Compose and are never silently
overridden. Leave both account fields blank to select in the terminal, or supply
the exact account references. Changing a previously retained pair requires an
explicitly reviewed state change; editing `.env` alone will not reroute it.

### Ghostfolio on a private Docker network

For a deployment using the internal service **`ghostfolio:3333`**, set:

```dotenv
GHOSTFOLIO_ORIGIN=http://ghostfolio:3333
GHOSTFOLIO_NETWORK=your-existing-private-network
```

Use the included overlay for both commands:

```bash
docker compose -f compose.yaml -f compose.ghostfolio.yaml pull
docker compose -f compose.yaml -f compose.ghostfolio.yaml run --rm bitwarden connect
```

The network must already exist and resolve `ghostfolio` to your trusted service.
Only this exact HTTP origin is accepted, and its connected peer must have an
RFC1918 address before credentials are sent. Other HTTP origins and redirects
are refused. The default Compose does not join a production network.

### Security mappings

Put verified mappings in **`config/mappings.yaml`**. The directory is mounted
read-only. A missing mapping is reported in the dry run; acquisition can still
save the documents. See the [mapping format](config/README.md).

Keep `.env`, mappings and the state volume private. Docker administrators can
inspect container environment variables. Never publish documents, credentials,
account identifiers or report contents in an issue or pull request.

## Reading the results

The terminal prints a JSON summary with document counts, candidate activity counts,
exception counts and the saved report path.

| Exit code | Meaning |
| --- | --- |
| `0` | Dry run completed without unresolved source exceptions |
| `2` | Dry run completed; the report contains exceptions to review |
| `1` | Connection, configuration or processing failed |

A completed dry run is a preview, regardless of exit code. Inspect the exceptions
before considering any later import. Currency conflicts, missing mappings,
unsupported operations and existing-record differences remain visible.

The **`bitwarden-binding`** volume, named within the Compose project, retains:

- `community-binding.yaml`: the selected source/destination pair.
- `runs/<run-id>/`: original documents, destination snapshots and acquisition receipts.
- `outputs/daily-notices-<account-key>.yaml`: the detailed private report.
- `state/`: journals needed to preserve identity and uncertain-attempt fences.

The state root is `/state` inside the container. To copy the retained files into a
private local directory without another connection attempt:

```bash
install -d -m 700 saved-run
docker compose run --rm --no-deps --entrypoint /bin/sh \
  -v "$PWD/saved-run:/export" bitwarden -c 'cp -a /state/. /export/'
```

The export directory must be writable by UID/GID 1000, used by the container.
Preserve the whole volume for backups and reuse the same Compose project directory
for later deliberate launches. `docker compose down -v` removes this history.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Account selection requires a terminal | Run interactively or configure both exact account fields |
| Saved account conflicts with configuration | Restore the intended settings; do not silently replace the binding |
| Missing security mapping or currency conflict | Review the report and verified per-ISIN mapping |
| Exit `2` | Read the diagnostic report; this is a completed preview with exceptions |
| Vault item cannot be resolved | Check the exact item name, uniqueness and stored TOTP setup |
| HTTP origin refused | Use HTTPS, or the exact private-network setup documented above |
| Browser sandbox fails | Keep the supplied seccomp profile and Compose capabilities |
| An unfinished authentication attempt blocks another run | Retain its journal and inspect the failure before an explicit recovery |

Do not loop failed broker logins or remove authentication journals to bypass a
fence. A successfully closed session permits a later deliberate launch; it does
not enable automatic retries or scheduling.

The optional `docker compose run --rm bitwarden inspect` checks vault item identity
and logout without submitting credentials to Bourse Direct.

## Documentation and development

- [Documentation map](docs/README.md): current contracts, operational guidance and archives.
- [Contributing](CONTRIBUTING.md): local builds and synthetic verification.
- [Release process](docs/operations/releasing.md) and [changelog](CHANGELOG.md).
- [Design contracts](docs/design/index.md): financial, acquisition and recovery boundaries.

This is a community project, unaffiliated with Bourse Direct or Ghostfolio.
The project uses the terms in its [MIT Non-AI License](LICENSE). The bundled
browser includes third-party components; see the [Playwright Apache 2.0 license](collector/licenses/playwright-LICENSE)
and its attribution notices. See the [build and release guarantees](.github/BUILD.md)
for image scanning and artifact publication.

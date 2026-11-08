<p align="center">
  <img src="docs/assets/readme-banner.svg" alt="Bourse Direct PDF notices flow through the importer into self-hosted Ghostfolio" width="100%">
</p>

<p align="center">
  <a href="https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/latest"><img src="https://img.shields.io/github/v/release/flowcool/ghostfolio-boursedirect-sync?display_name=tag&amp;sort=semver" alt="Latest release"></a>
  <a href="https://github.com/flowcool/ghostfolio-boursedirect-sync/actions/workflows/offline-tests.yml"><img src="https://github.com/flowcool/ghostfolio-boursedirect-sync/actions/workflows/offline-tests.yml/badge.svg" alt="Build and checks: offline tests"></a>
  <a href="https://github.com/flowcool/ghostfolio-boursedirect-sync/actions/workflows/codeql.yml"><img src="https://github.com/flowcool/ghostfolio-boursedirect-sync/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT%20NON--AI-5b6f8f" alt="MIT NON-AI License"></a>
</p>

<p align="center"><strong>Your Bourse Direct trades, in your self-hosted Ghostfolio.</strong><br>Drop your PDF notices in a folder. Preview. Import. Done.</p>

<p align="center">🇫🇷 <a href="README.fr.md"><strong>Version française</strong></a> · <a href="#quick-start">Quick start</a> · <a href="#configuration">Configuration</a> · <a href="https://github.com/flowcool/ghostfolio-boursedirect-sync/discussions">Questions</a> · <a href="https://github.com/flowcool/ghostfolio-boursedirect-sync/releases">Releases</a></p>

## What it does

Bourse Direct has no public API, but it sends a PDF **operation notice** (avis d'opéré)
for every trade and coupon. This importer reads those original PDFs and creates the
matching activities in one [Ghostfolio](https://ghostfol.io) account: buys, sells,
fees and coupons, for EUR **PEA** and **PEA-PME** accounts.

- 📁 Reads a plain PDF folder, or an existing Paperless-ngx.
- 🧪 Simulates by default. Nothing is written until you switch it on.
- 🔁 Never imports the same notice twice, even after a rename.
- 🔐 No broker login. It only reads your PDFs and talks to Ghostfolio.
- 🐳 One Docker container, amd64 and arm64, with a built-in schedule.

## Requirements

- Docker with Compose.
- A running Ghostfolio, with one account for your Bourse Direct PEA (or PEA-PME)
  and a **Security Token** (Ghostfolio → Account → Access).
- Your **original PDF notices**, downloaded from your Bourse Direct client area.
  Scans are not supported.
- New notices must reach the folder for later runs. Download them yourself, or
  automate it with a document collector. [Paperless-ngx](https://docs.paperless-ngx.com)
  can be the source instead of the folder.

## Quick start

**1. Create a folder with your PDFs and this `compose.yaml`:**

```yaml
services:
  importer:
    image: ghcr.io/flowcool/ghostfolio-boursedirect-sync:latest
    restart: unless-stopped
    user: "10001:10001"
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    tmpfs: ["/tmp:rw,noexec,nosuid,size=16m,mode=1777"]
    env_file: .env
    volumes:
      - ./notices:/notices:ro
```

Put the PDFs in `notices/`. The container runs as UID 10001 and needs read access:
`sudo chgrp -R 10001 notices && chmod -R g+rX notices`.

**2. Create `.env`:**

```dotenv
GHOST_HOST=https://ghostfolio.example.com
GHOST_ACCESS_TOKEN=your-ghostfolio-security-token
GHOST_ACCOUNT_NAME=Bourse Direct PEA
BD_ACCOUNT_REF=12345678
NOTICE_DIR=/notices
DRY_RUN=1
TZ=Europe/Paris
CRON=
```

**3. Simulate, then import:**

```sh
docker compose run --rm importer               # simulation: read the proposed rows
docker compose run --rm -e DRY_RUN=0 importer  # import once
```

Check the result in Ghostfolio. A second import must create nothing.

**4. Schedule:** set `DRY_RUN=0` and `CRON=0 6 * * *` in `.env`, then `docker compose up -d`.

Using an AI assistant to install it? Point it to [llms.txt](llms.txt).

## Configuration

| Variable | Required | Default | Values and meaning |
| --- | --- | --- | --- |
| `GHOST_HOST` | yes | — | Ghostfolio URL as seen from the container: its normal URL, or `http://ghostfolio:3333` if both services share a Docker network. |
| `GHOST_ACCESS_TOKEN` | yes | — | Ghostfolio Security Token. |
| `GHOST_ACCOUNT_NAME` | yes | — | Exact name of the target Ghostfolio account. |
| `BD_ACCOUNT_REF` | yes | — | Account reference after `COMPTE N°` on a notice, without spaces, `EUR` or `PEA`. |
| `NOTICE_DIR` | folder source | empty | `/notices`. Leave empty to use Paperless. |
| `PAPERLESS_URL`, `PAPERLESS_TOKEN` | Paperless source | empty | Paperless-ngx URL and a read-only token. |
| `DRY_RUN` | no | `1` | `1` simulates. `0` writes to Ghostfolio. |
| `CRON` | no | empty | Five-field schedule, e.g. `0 6 * * *`. Empty runs once. |
| `TZ` | no | — | Your timezone, e.g. `Europe/Paris`. |
| `MAPPING_FILE` | no | empty | Mounted YAML file with a `symbol_mapping:` block of `ISIN: TICKER` overrides. See [mapping](config/README.md). |
| `IMPORT_CREATE_FROM` | no | empty | `YYYY-MM-DD`: never create activities before this date. |
| `APPRISE_URLS` | no | empty | JSON list of [Apprise](https://github.com/caronc/apprise) URLs for alerts. |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

All settings, review options and Paperless setup: [configuration reference](docs/configuration.md).

**Foreign shares:** Bourse Direct buys them in EUR on European venues. Map them to
the EUR listing, e.g. SAAB → `SDV1.F`, not `SAAB-B.ST`.

## Safety

- It adds activities and never deletes any. Changes to existing activities follow the [review rules](docs/maintenance.md#operator-review-and-reconciliation).
- Unreadable notices and uncertain writes stop the import. Nothing is retried blindly.
- Keep your token, PDFs and logs private.

## Limitations

Original text PDFs of EUR PEA and PEA-PME only. No CTO, no account statements, no
scans, no currency conversion. Corporate actions are held for manual review. A sell
needs its earlier buy notice. Details: [supported notices](docs/supported-notices.md).

## Documentation

[Full installation guide](docs/getting-started.md) · [Configuration](docs/configuration.md) ·
[Troubleshooting](docs/troubleshooting.md) · [Upgrading](docs/upgrading.md) ·
[All docs](docs/README.md) · [Contributing](CONTRIBUTING.md)

Questions: [Discussions](https://github.com/flowcool/ghostfolio-boursedirect-sync/discussions) ·
Bugs: [Issues](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues)

## License

[MIT NON-AI License](LICENSE). It adds restrictions to the standard MIT license. Read it before use.

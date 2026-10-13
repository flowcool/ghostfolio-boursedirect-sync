# Bourse Direct → Ghostfolio

The v0.2 rebuild starts with a noninteractive BUY simulation through Docker
Compose. Use one explicitly configured PEA or PEA-PME, an existing Ghostfolio
account and verified Yahoo mappings. No financial records are written.

This source checkout implements OpenSpec tasks 1.1 and 2.1. Account discovery
runs once without a terminal and needs only Bitwarden configuration. Additional
operation types, automatic symbol resolution, deduplication, actual imports and
scheduling belong to later slices. Non-BUY rows are counted as deferred in this
slice. `DRY_RUN=0` and nonempty `CRON` refuse before broker access.

## Quick start

Requires Linux AMD64, Docker Engine and Compose 2.27.0 or later. The image contains the pinned
Bitwarden CLI and sandboxed Chromium. No TTY or browser port is required.

1. Clone this repository. Copy `.env.example` to `.env`, restrict it with
   `chmod 600 .env`, and fill in the `BW_*` values. Leave
   `BD_SOURCE_ACCOUNT_REF` empty to discover accounts first. Ghostfolio and
   mappings are not required for discovery.
2. Run without a TTY:

   ```sh
   docker compose up --build --abort-on-container-exit --exit-code-from boursedirect-sync
   ```

   The log lists copyable `BD_SOURCE_ACCOUNT_REF='reference PEA'` or
   `BD_SOURCE_ACCOUNT_REF='reference PEA-PME'` options, without holders or
   balances. `SOURCE_ACCOUNT_CONFIGURATION_REQUIRED` and exit code 1 are
   expected. No notices or financial data are imported. The completed discovery
   receipt prevents another login on restart while the source reference is empty;
   the same options appear with `broker_attempts=0`.
3. Copy the exact source option into `.env`. Configure `GHOST_HOST`,
   `GHOST_ACCESS_TOKEN` and `GHOST_ACCOUNT_ID`. Create `config/mappings.yaml` as
   private YAML (`chmod 600`). Use verified
   Yahoo symbols with explicit EUR currency:

   ```yaml
   FR0000000002:
     symbol: VERIFIED.PA
     currency: EUR
   ```

   This example ISIN is synthetic. Replace it with your actual instrument.
   Every BUY in the acquired window needs its explicit entry in this slice.
   A missing mapping refuses the simulation. Venue text never selects a ticker.
4. Run the same Compose command to simulate the configured account:

   ```sh
   docker compose up --build --abort-on-container-exit --exit-code-from boursedirect-sync
   ```

Bourse Direct locks the account after three failed logins. The connector makes
one attempt, never retries automatically, and preserves the authentication
journal. On failure or uncertain outcome, stop and inspect the private state;
never delete a journal or volume to make a restart succeed.

## Configuration

| ENV | Value |
| --- | --- |
| `BW_SERVER` | HTTPS Bitwarden-compatible vault origin |
| `BW_CLIENTID`, `BW_CLIENTSECRET`, `BW_PASSWORD` | Personal API credentials and vault master password |
| `BW_ITEM_NAME` | Unique broker login item with password and TOTP; default `boursedirect.fr` |
| `BD_SOURCE_ACCOUNT_REF` | Empty: discover once; otherwise exact reference and wrapper, e.g. `SYNTHETIC001 PEA` |
| `BD_STATE_VOLUME` | Optional shared Docker state volume name; identical for all services using the same broker credentials |
| `GHOST_HOST` | Final HTTPS Ghostfolio origin; no redirect, path, query or credentials |
| `GHOST_ACCESS_TOKEN` | Long-lived Ghostfolio Security Token, exchanged each run |
| `GHOST_ACCOUNT_ID` | Exact existing destination ID |
| `MAPPING_FILE` | Readable private YAML inside the container; default `/config/mappings.yaml` |
| `DRY_RUN` | `1`/`true`/`yes`/`on`, or absent, simulates; other values refuse in this slice |
| `CRON` | Leave empty for one run; scheduling is not implemented yet |
| `APPRISE_URLS` | Reserved for the later alert slice |

The existing acquisition reads notices for the selected account and closes the
vault and browser before simulation. The connector authenticates to Ghostfolio
and reads accounts/activities; the authentication POST is not a financial write.
The rolling window uses today's date in Europe/Zurich. This slice uses the
existing acquisition path; the dedicated coverage acceptance is task 2.2.

Discovery runs before Ghostfolio and mapping validation. It closes the vault
and browser before publishing the completed receipt. An unfinished discovery,
malformed login journal or unresolved authentication attempt refuses before
vault/broker access and reports `broker_attempts=0`. Inspect the preserved state
for operator resolution; never delete receipts to retry.

All services using the same broker credentials must mount the same state volume.
Use Compose 2.27.0 or later: [that release includes compose-go 2.1.0](https://github.com/docker/compose/blob/v2.27.0/go.mod),
which contains the project-name interpolation fix. For every invocation with
`docker compose -p alternate`, including upgrades of the same deployment, set
`BD_STATE_VOLUME` explicitly to its existing volume name, for example
`BD_STATE_VOLUME=alternate_boursedirect-state`. Use the actual existing name if
that deployment already uses a custom volume.
For separate Compose projects, set the same `BD_STATE_VOLUME` to the existing
volume name in each `.env`; this preserves the login namespace and shares the
nonblocking broker lock. Leave it empty for a single service to keep the current
project's default volume. A concurrent run exits with `BROKER_RUN_LOCKED` before
network access. Account bindings are stored separately per source reference;
changing an existing destination remains a refusal. Do not create a new empty
volume to bypass a retained failed attempt.

For a trusted existing private Docker network, set `GHOST_HOST` to exactly
`http://ghostfolio:3333`, set `GHOSTFOLIO_NETWORK`, and include
`-f compose.yaml -f compose.ghostfolio.yaml` in the Compose command. This reuses
your instance; it does not create a Ghostfolio lab.

## Review a dry run

Each `DRY_RUN_PROPOSAL` log line shows date, ISIN, symbol, EUR quantity, unit price
and brokerage fee. Dates use midnight UTC. Decimal values are serialized as exact
strings. The final line reports `financial_writes=0`, `imported=0`, the number of
BUY proposals and the number of operations deferred to later slices.

The private `boursedirect-state` volume retains source notices, acquisition
receipts, login journals, `discovery.yaml`, source bindings under `accounts/`
and `runs/<id>/simulation.yaml`. The previous `community-binding.yaml` is retained
and reused for its original source account.
Simulation does not mark proposals imported. Keep the volume across runs.
Compose retains bounded logs; they contain the proposed financial fields, so
restrict access to the Docker host. Credentials, holders and balances are not
printed. Private state and mappings must stay off Git.

## Rollback

Keep the previous state and image. Revert this task's commit to restore the
previous Compose behavior; retain discovery and authentication journals.
The published v0.1.1 remains the legacy interactive
preview-only release. See its [release notes](docs/releases/v0.1.1.md) and
[connection procedure](docs/operations/source-connection.md).

<details>
<summary>Published v0.1.1 legacy instructions (use the v0.1.1 checkout)</summary>

## Who this is for

Use the published Docker image if you run Ghostfolio already, have a Bourse
Direct PEA or PEA-PME, and want to review recent operation notices privately.
You need a Bitwarden-compatible vault, a dedicated Bourse Direct login item, and
an existing Ghostfolio account.

## Preview only

The connector reads a rolling 90-day window of available operation notices, saves them
with a Ghostfolio snapshot, and creates a dry-run report. It never creates,
updates, or deletes financial records, and it does not schedule itself. The
window is not complete account history or a cost-basis reconstruction. Currency
and security mappings must be supplied explicitly; the connector does not guess
them or convert corporate actions such as subscription rights.

Future releases may add capabilities only through a separately reviewed release.
Until then, writes and scheduling remain out of scope.

## How it works

1. The connector opens one vault session and reads the selected Bourse Direct
   login item.
2. It connects once, lets you select a PEA or PEA-PME and an existing Ghostfolio
   account when needed, then saves that pair in its private state volume.
3. It downloads the available operation notices, closes the session, and compares
   the saved documents with a Ghostfolio snapshot.
4. It writes a report for you to review. Missing mappings, unsupported operations,
   or uncertain results remain visible; none become financial writes.

The private state volume keeps the selected account pair, source documents,
receipts, reports, and safety journals. A journal records an unfinished attempt
so it cannot be bypassed by repeatedly trying a login.

## Requirements

- Linux on Intel/AMD (**AMD64**) with Docker Engine and Docker Compose v2.
- A Bitwarden-compatible HTTPS vault with a personal API key and master password.
- One uniquely named login item containing your Bourse Direct login, password,
  and TOTP setup, normally named `boursedirect.fr`.
- Ghostfolio, an existing destination account, and its long-lived **Security
  Token**.
- About 1.5 GiB of container memory and outbound access to the vault, broker,
  and configured Ghostfolio origin.

The release includes the qualified browser and Bitwarden CLI. No local Python,
Node.js, browser installation, Docker socket mount, or published port is needed.
The published release and image CI support AMD64 only.

## Quick start

Save the following as **`compose.yaml`** in a dedicated directory. It runs the
published image; no archive, repository clone, local build, Python or Node.js
installation is needed.

```yaml
name: ghostfolio-boursedirect-sync
services:
  bitwarden:
    image: ${BOURSEDIRECT_IMAGE:-ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.1@sha256:486cc5ef8b3dde9e65b2b502789b65c9d956acb4ea03e3e2544c316d2bbef231}
    platform: linux/amd64
    init: true
    restart: "no"
    read_only: true
    user: "1000:1000"
    environment:
      BW_SERVER: ${BW_SERVER:-https://vault.bitwarden.com}
      BW_ITEM_NAME: ${BW_ITEM_NAME:-boursedirect.fr}
      BW_CLIENTID: ${BW_CLIENTID:?Supply your Bitwarden personal API client ID}
      BW_CLIENTSECRET: ${BW_CLIENTSECRET:?Supply your Bitwarden personal API client secret}
      BW_PASSWORD: ${BW_PASSWORD:?Supply your Bitwarden master password}
      # Your Ghostfolio instance supplies the origin and long-lived Security Token.
      # HTTPS normally; exact http://ghostfolio:3333 requires a trusted private network.
      GHOSTFOLIO_ORIGIN: ${GHOSTFOLIO_ORIGIN:-}
      GHOSTFOLIO_SECURITY_TOKEN: ${GHOSTFOLIO_SECURITY_TOKEN:-}
      # Optional explicit routing. Missing fields are selected once in the terminal.
      # Configured values are never overridden; conflicting retained routing refuses.
      BD_SOURCE_ACCOUNT_REF: ${BD_SOURCE_ACCOUNT_REF:-}
      GHOSTFOLIO_ACCOUNT_ID: ${GHOSTFOLIO_ACCOUNT_ID:-}
    tmpfs:
      - /data:rw,noexec,nosuid,nodev,mode=0700,uid=1000,gid=1000
      - /tmp:rw,nosuid,nodev,mode=1777
      - /home/fixture:rw,nosuid,nodev,mode=0700,uid=1000,gid=1000
    volumes:
      - bitwarden-binding:/state
      - ./config:/config:ro
    cap_drop: [ALL]
    # Required by Chromium to create its sandbox chroot.
    cap_add: [SYS_CHROOT]
    security_opt: [no-new-privileges, "seccomp=./collector/browser-seccomp.json"]
    ipc: private
    shm_size: 128m
    ulimits:
      core: {soft: 0, hard: 0}
    mem_limit: 1536m
    cpus: 1
    pids_limit: 256
    logging: {driver: none}
volumes:
  bitwarden-binding:
```

1. Prepare the configuration directory and the browser sandbox profile on the
   **Docker host**, beside `compose.yaml`:

   ```bash
   mkdir -p config collector
   curl --fail --silent --show-error --location \
     https://raw.githubusercontent.com/flowcool/ghostfolio-boursedirect-sync/6a4a3e48b688ed2edba40dff2a63c1a329e37447/collector/browser-seccomp.json \
     -o collector/browser-seccomp.json
   echo 'cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849  collector/browser-seccomp.json' | sha256sum -c -
   ```

   Docker reads this profile before starting the container; putting it inside
   the image cannot supply it to the host. Keep the verified profile in place for
   later runs. The empty `config` directory is enough to start; add your verified
   `config/mappings.yaml` when ready, using the [mapping format](config/README.md).

2. Save this template as **`.env`** beside `compose.yaml`, fill in your vault and
   Ghostfolio values using [Configuration](#configuration), then run `chmod 600 .env`:

   ```dotenv
   # Bitwarden personal API credentials and vault master password.
   # Populate locally; this file contains placeholders only.
   BW_SERVER=https://vault.bitwarden.com
   BW_CLIENTID=
   BW_CLIENTSECRET=
   BW_PASSWORD=
   BW_ITEM_NAME=boursedirect.fr

   # Your Ghostfolio instance supplies this access. Use the permanent Security Token, not a JWT.
   # HTTPS normally; http://ghostfolio:3333 is allowed on a trusted private Docker network.
   GHOSTFOLIO_ORIGIN=
   GHOSTFOLIO_SECURITY_TOKEN=

   # Optional explicit accounts. Missing choices are selected once during connect.
   # Retained routing is never silently overridden by these settings.
   BD_SOURCE_ACCOUNT_REF=
   GHOSTFOLIO_ACCOUNT_ID=

   # Only with compose.ghostfolio.yaml: existing private Docker network.
   GHOSTFOLIO_NETWORK=

   # Optional deliberate image override; blank uses the version pinned in Compose.
   BOURSEDIRECT_IMAGE=
   ```

3. Pull the released image:

   ```bash
   docker compose pull
   ```

4. Start one interactive connection and keep the terminal attached. If account
   fields are blank, choose the offered source and destination accounts:

   ```bash
   docker compose run --rm bitwarden connect
   ```

5. Read the JSON line in the terminal and the report saved in the persistent
   volume. See [Review a dry run](#review-a-dry-run).

`bitwarden` is the retained Compose service name because it includes the
Bitwarden CLI. It is the whole connector, not a Bitwarden server. Likewise,
`bitwarden-binding` is the connector's persistent state volume; it stores more
than the vault binding. Keep the same Compose project name to retain that volume.
The connection is interactive: `docker compose up -d` does not replace step 4.

For a Docker stack manager, prepare the profile and configuration on the Docker
host and use absolute host paths for `seccomp` and the `/config` bind mount.
Supply the variables through its environment editor if preferred. Run the
connection with an attached terminal; this release does not schedule itself.

The image reference above pins the published content by SHA256 digest. An
explicit `BOURSEDIRECT_IMAGE` override replaces that pin. For upgrades, follow the
new release's image reference and configuration instructions together.

The [release archive](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/latest)
is an optional way to obtain the Compose files, sandbox profile, configuration
templates and documentation as one bundle. It is not needed for the Docker flow
above. Releases from v0.1.1 also contain `IMAGE_DIGEST` alongside the archive and
checksums; previously published assets remain unchanged.

## Configuration

| Setting | Purpose |
| --- | --- |
| `BW_SERVER` | Canonical HTTPS vault origin; default `https://vault.bitwarden.com` |
| `BW_CLIENTID`, `BW_CLIENTSECRET` | Bitwarden personal API credentials |
| `BW_PASSWORD` | Vault master password |
| `BW_ITEM_NAME` | Exact, unique login-item name; default `boursedirect.fr` |
| `GHOSTFOLIO_ORIGIN` | Ghostfolio HTTPS origin, without path, query, or fragment |
| `GHOSTFOLIO_SECURITY_TOKEN` | Permanent Security Token; not an expiring JWT |
| `BD_SOURCE_ACCOUNT_REF` | Optional exact source reference, for example `ABC12345 PEA` |
| `GHOSTFOLIO_ACCOUNT_ID` | Optional existing destination account ID |
| `BOURSEDIRECT_IMAGE` | Optional image override for a deliberate upgrade or rollback |

Leave both account fields blank to select them in the terminal, or supply the
exact account references. The first successful selection is retained. A later
conflict stops the run; changing `.env` cannot silently route a saved account
pair elsewhere.

Put verified mappings in **`config/mappings.yaml`**. The directory is mounted
read-only. A missing mapping is reported in the dry run while acquisition can
still save the documents. See the [mapping format](config/README.md).

Keep `.env`, mappings, and the state volume private. Docker administrators can
inspect container environment variables. Never publish documents, credentials,
account identifiers, or report contents in an issue or pull request.

### Ghostfolio on a private Docker network

This optional setup is for an existing Ghostfolio service called
`ghostfolio:3333` on a trusted private Docker network. It is outside the normal
quick-start flow:

```dotenv
GHOSTFOLIO_ORIGIN=http://ghostfolio:3333
GHOSTFOLIO_NETWORK=your-existing-private-network
```

Save the [private-network overlay](compose.ghostfolio.yaml) as
`compose.ghostfolio.yaml` beside your Compose file, then use it for both commands:

```bash
docker compose -f compose.yaml -f compose.ghostfolio.yaml pull
docker compose -f compose.yaml -f compose.ghostfolio.yaml run --rm bitwarden connect
```

The network must already exist and resolve `ghostfolio` to your trusted service.
Only this exact HTTP origin is accepted, and its connected peer must have an
RFC1918 address before credentials are sent. Other HTTP origins and redirects
are refused. The default Compose project does not join a production network.

## Review a dry run

The terminal prints one JSON summary. This synthetic example has no personal
account number, document, or portfolio data:

```json
{"code":"COMMUNITY_DRY_RUN_COMPLETED","contract_notes":[],"source_mode":"notices","source_activities":3,"skipped_operations":0,"unresolved_exceptions":1,"import_ready":false,"blockers":["FINANCIAL_APPLICATION_NOT_AUTHORIZED"],"report":"outputs/daily-notices-example-account.yaml"}
```

| Exit code | Meaning |
| --- | --- |
| `0` | Dry run completed without unresolved source exceptions |
| `2` | Dry run completed; the report contains exceptions to review |
| `1` | Connection, configuration, or processing failed |

A completed dry run remains a preview, whatever its exit code. Review exceptions
before considering any later import. Currency conflicts, missing mappings,
unsupported operations, and existing-record differences remain visible.

The `bitwarden-binding` volume retains:

- `community-binding.yaml`: the selected source/destination pair.
- `runs/<run-id>/`: original documents, destination snapshots, and acquisition receipts.
- `outputs/daily-notices-<account-key>.yaml`: the detailed private report.
- `state/`: journals that preserve identity and stop uncertain attempts from being rerun.

The report is YAML. Its exact content depends on your private data; this excerpt
uses entirely synthetic values:

```yaml
schema_version: 1
source_mode: notices
as_of: 2026-10-12
window:
  first: 2026-07-14
  last: 2026-10-12
import_ready: false
blockers:
  - FINANCIAL_APPLICATION_NOT_AUTHORIZED
activities:
  BD#v1#example-account#example-event:
    kind: BUY
    symbol: EXAMPLE.PA
exceptions:
  - SECURITY_MAPPING_MISSING
```

To copy retained files into a private local directory without another connection
attempt:

```bash
install -d -m 700 saved-run
docker compose run --rm --no-deps --entrypoint /bin/sh \
  -v "$PWD/saved-run:/export" bitwarden -c 'cp -a /state/. /export/'
```

The export directory must be writable by UID/GID 1000, used by the container.
Preserve the whole volume for backups and reuse the same Compose project directory
for deliberate later launches. `docker compose down -v` removes this history.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Account selection requires a terminal | Run interactively or configure both exact account fields |
| Saved account conflicts with configuration | Restore the intended settings; do not silently replace the binding |
| Missing security mapping or currency conflict | Review the report and verified per-ISIN mapping |
| Exit `2` | Read the diagnostic report; this is a completed preview with exceptions |
| Vault item cannot be resolved | Check the exact item name, uniqueness, and stored TOTP setup |
| HTTP origin refused | Use HTTPS, or the exact private-network setup documented above |
| Browser sandbox fails | Keep the supplied seccomp profile and Compose capabilities |
| An unfinished authentication attempt blocks another run | Retain its journal and inspect the failure before an explicit recovery |

Do not loop failed broker logins or remove authentication journals to bypass a
fence. A successfully closed session permits a later deliberate launch; it does
not enable automatic retries or scheduling.

The optional `docker compose run --rm bitwarden inspect` checks vault item
identity and logout without submitting credentials to Bourse Direct.

### Safe support reports

Docker log retention is disabled (`logging: driver: none`). The attached terminal
still receives account-selection prompts and fixed JSON result/error codes;
`docker logs` cannot recover them after the run. Note the final `code` field and
exit code when a run fails. Do not relaunch a failed authentication just to collect
output, and do not enable raw browser, vault or HTTP debug logging.

For a public issue, share only the fixed code (for example,
`SOURCE_CONNECT_REFUSED`), exit code, connector release/image digest, CPU
architecture, and Docker/Compose versions. Copy the image reference from
`compose.yaml` or the release's `IMAGE_DIGEST`; use `uname -m`, `docker --version`
and `docker compose version` for platform details. Never paste `.env`, resolved
`docker compose config`, container inspection output, terminal account choices,
raw HTML, URLs, snapshots, reports or acquisition receipts. Those can contain
credentials or personal account data. Preserve the private state volume for
diagnosis; reporting an error does not authorize another broker attempt.

If the broker page or authentication flow changes, stop and follow the
[source requalification procedure](docs/operations/source-connection.md#broker-site-changes-and-requalification).

## Documentation and development

- [Documentation map](docs/README.md): start here for user, contributor, and auditor material.
- [Contributing](CONTRIBUTING.md): local builds and synthetic verification.
- [Release process](docs/operations/releasing.md) and [changelog](CHANGELOG.md).
- [Design contracts](docs/design/index.md): current acquisition, account, financial,
  preview, and recovery boundaries.

The project uses the terms in its [MIT Non-AI License](LICENSE). The bundled
browser includes third-party components; see the
[Playwright Apache 2.0 license](collector/licenses/playwright-LICENSE) and its
attribution notices. See the [build and release guarantees](.github/BUILD.md)
for image scanning and artifact publication.

</details>

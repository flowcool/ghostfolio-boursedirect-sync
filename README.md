# Bourse Direct → Ghostfolio

The v0.2 rebuild imports BUY, SELL and net coupon activities through Docker
Compose. Use one explicitly configured PEA or PEA-PME, an existing Ghostfolio
account and a readable YAML mapping file. Simulation is the default.

Account discovery runs once without a terminal and needs only Bitwarden
configuration. Deduplication and holdings checks run before proposals. Set `DRY_RUN=0` explicitly to import. Set `CRON` to schedule nonoverlapping runs.

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
   private YAML (`chmod 600`). An empty mapping (`{}`) enables automatic
   resolution. To select a specific candidate, supply its verified Yahoo symbol
   and explicit EUR currency:

   ```yaml
   FR0000000002:
     symbol: VERIFIED.PA
     currency: EUR
   ```

   This example ISIN is synthetic. Replace it with your actual instrument.
   YAML overrides take priority, followed by unique existing Ghostfolio profiles
   with the same ISIN, then Ghostfolio ISIN lookup. Automatic selection requires
   one distinct Yahoo symbol with explicit EUR currency. Venue text never selects
   a ticker. Missing, ambiguous or failed lookup logs candidate tickers, skips that
   ISIN and fails the run; resolved supported rows still produce proposals. Add a verified
   YAML entry to resolve the failure on a later deliberate run.
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
| `DRY_RUN` | `1`/`true`/`yes`/`on`, or absent, simulates; `0`/`false`/`no`/`off` imports; other values refuse |
| `CRON` | Empty runs once; five numeric cron fields schedule nonoverlapping runs |
| `APPRISE_URLS` | Optional JSON list of at most 10 Apprise URLs; failure alerts in import mode only |
| `APPRISE_TIMEOUT` | Whole alert-worker deadline in seconds, 1–30; default 10 |

The existing acquisition reads notices for the selected account and closes the
vault and browser before simulation. The connector authenticates to Ghostfolio
and reads accounts/activities; the authentication POST is not a financial write.
The rolling window includes today and the previous 89 days in Europe/Zurich.
`NOTICE_WINDOW_COMPLETED` reports its exact bounds, expected and observed
calendar months, confirmed empty months, selected-account verification, logout
and browser exit. Every expected month and every offered in-window notice must
be captured before simulation. A confirmed empty month succeeds. Missing
coverage, an unexpected calendar or a different account refuses the run with
zero financial writes. Monthly statements are never selected. The first month
is read in full; proposals use the financial row date within the exact window.

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

### Scheduling and failure reporting

Set `CRON=0 6 * * *` and run `docker compose up -d --build`. Supercronic
validates the five numeric fields before broker access. Invalid syntax emits a
fixed configuration error. Runs use the container timezone (UTC by default).
Supercronic waits for a running job before starting its next invocation; the
persistent broker lock also serializes services that share the state volume.
Keep that volume across restarts. Discovery receipts, unresolved login attempts
and uncertain writes still refuse on later scheduled runs. Do not clear them to
resume a schedule. Inspect logs with `docker compose logs boursedirect-sync`.

Each run ends with `NOTICE_RUN_COMPLETED`: status, fixed error code and
proposed/imported/duplicate/skipped/failed-row, error and dispatched-write counts.
Counts on an early refusal cover only the work reached, not unseen notices.
A confirmed empty window succeeds with zero counts.

For optional failure delivery, set `APPRISE_URLS` to a private JSON list such as
`["discord://webhook_id/webhook_token"]`. An absent value or `[]` disables alerts.
Simulation never sends alerts. Each failed import run sends at most one message,
containing only the final fixed-code/count summary. The isolated Apprise worker
has no broker or Ghostfolio credentials and no log output. Its whole lifetime
is limited by `APPRISE_TIMEOUT`; timeout kills and reaps it, without retry.
Invalid notification settings disable delivery with a fixed warning. Delivery
failure does not change the sync exit status. Each later failed scheduled run
can send one new alert. Never commit destination URLs or their credentials.

## Import and verify

Review a simulation first. Resolve manual overlaps, missing mappings and
insufficient holdings before setting `DRY_RUN=0` in your private ENV. Use the
same Compose command. Every financial payload contains activities only;
existing activities, account balances and cash are never updated or deleted.

The connector stores a durable pending intent before each POST. Success requires
exact account, identity comment, UTC date, symbol, data source, EUR currency,
quantity, price and fee in both the response and a complete activities readback.
`NOTICE_IMPORT_CONFIRMED` reports both checks. Only confirmed BUYs fund later
SELLs. A rejected Yahoo symbol is logged and skipped; other imports continue,
and the run fails. A rejected BUY cannot fund a SELL.

`NOTICE_IMPORT_COMPLETED` reports proposed, imported, duplicate, skipped and
failed counts. `financial_writes` counts dispatched financial POSTs, including
rejected or uncertain requests. An absent response, changed field, incomplete
readback or unexpected HTTP result leaves the pending intent in
`notice-writes-<destination-hash>.yaml`. Restarts refuse with
`NOTICE_WRITE_UNRESOLVED` before network access, including simulation. Preserve
the journal and private `runs/<run-id>/import-response-*.json` and
`import-readback-*.json` for explicit operator resolution. Never clear an intent
or repeat a POST to guess its outcome. Normal startup never recovers an intent.

An operator can recover one selected notice only when the pending body, saved
HTTP 201 response, pre-import baseline, saved complete readback and one fresh
complete Ghostfolio readback all agree. Preservation ignores only `activitiesCount`
and the profile refresh `updatedAt` inside `assetProfile` or `SymbolProfile`;
the activity's own timestamp, all financial and identity fields, and every other
profile field remain exact. Record the exact pending `run_id` and
`ordinal`, stop scheduled runs, and take a recoverable backup of the `/state`
volume. Use the exact deployed image that contains the recovery command. Supply
a pre-obtained Ghostfolio session bearer for this operation; the long-lived
Security Token is not used and the command performs no token exchange or broker
request.

First preview the proof:

```console
GHOST_SESSION_BEARER='<session-jwt>' docker compose run --rm --no-deps \
  -e GHOST_SESSION_BEARER boursedirect-sync recover-notice-write \
  --expected-run-id '<retained-run-uuid>' --expected-ordinal '<retained-ordinal>'
```

`NOTICE_RECOVERY_VERIFIED` means one activities GET proved one exact active
remote ID and the journal bytes were retained. After separate authorization,
repeat the same command with `--confirm-local-state`. A successful result is
`NOTICE_RECOVERY_CONFIRMED`; it only moves that marker and remote ID from
`pending` to `confirmed`. It sends no financial POST.

Any missing, incomplete, changed, ambiguous or contradictory proof returns
`NOTICE_RECOVERY_REFUSED` and leaves the journal bytes unchanged. Do not edit the
journal, restore the pre-import state, or replay the POST. If local persistence
has an uncertain outcome, preserve the current state and inspect it before any
new operation. A subsequent normal run must recognize the recovered notice as
a duplicate before another import is authorized.

After confirmed import, a deliberate repeat reads the exact owned activities
and creates zero new activities. Simulation never writes an import journal or
marks a proposal imported.

## Review a dry run

Each `DRY_RUN_PROPOSAL` log line shows type, row date, ISIN, symbol, quantity,
EUR unit price and brokerage fee. Domestic and foreign BUY/SELL retain the exact
source quantities, prices and brokerage; SELL quantities are positive in the
proposal. The observed euro debit/credit headers and exact gross/net arithmetic
establish EUR trade amounts. A EUR instrument mapping cannot prove source
currency on its own. No currency conversion is inferred.

COUPONS become DIVIDEND with quantity `1`, the credited net EUR amount as unit
price and fee `0`. The source gross amount and commission do not become an
inferred withholding tax. Dates use each financial row's date at midnight UTC,
not the notice header date. Decimal values are serialized as exact strings.
`NOTICE_SIMULATION_COMPLETED` reports `financial_writes=0`, `imported=0`,
`proposed`, `duplicates`, `skipped` and `failed_rows`.

Each excluded row logs one error. DROITS DE GARDE, TAXE TRANSACT FINANCIERES,
DIVISION, DET DROIT DE SOUSCRIPTION, RETRAIT TITRES FISCALISE, TRANSFERT VALEUR
and INVESTISSEMENT ESPECES are known exclusions. These and supported rows
without ISIN do not fail the run. Unknown operations, unproved currency and
nonzero TVA skip the row and make the run exit nonzero, even without an ISIN.
Other valid rows continue. An unresolved instrument also skips and fails the run.
Structural or arithmetic inconsistencies refuse the run. Review these errors
before any later import.

The connector reads all destination activities in one request and checks the
reported count. Missing or redacted financial fields refuse the run. Each
proposal has a stable identity comment scoped to the source and destination
accounts. It uses normalized notice fields and preserves identical-row
multiplicity; ticker, capture URL and capture time do not affect identity.
An owned activity must match the exact account, date, type, symbol, data source,
currency, quantity, price and fee. Changed or repeated owned identities refuse.
Manual BUY/SELL entries match on an established civil day, even when their stored
timestamp is not midnight UTC. Account, instrument, type, quantity, unit price,
currency, data source and fee must match exactly. Each entry is consumed once;
source and destination multiplicities must be equal. Source execution time stays
in notice identity and ordering. Owned recognition still requires the exact stored
midnight UTC date and financial fields.

Manual DIVIDEND entries use the same established-day evidence and exact account,
instrument, type, currency, data source and fee checks. Their Decimal quantity ×
unit price must equal the notice's credited net EUR amount. Equivalent quantity
and price representations match automatically, with equal one-to-one
multiplicity, zero new proposals and no confirmation request. No gross amount or
withholding is inferred. A conflicting manual dividend within four civil days,
or unaccepted day uncertainty, refuses the whole run before writes. Existing fields
stay unchanged; owned dividends still require exact quantity, price and stored date.

Retain historical entry-day evidence in private `/state/manual-day-context.yaml`.
This keyed file is optional; its absence proves no manual activity's civil day.
Each activity ID maps to its exact account, original stored timestamp, financial
fingerprint, established day and a reference to retained entry-context evidence:

```yaml
schema_version: 1
activities:
  synthetic-activity-id:
    account_id: synthetic-destination
    stored_date: '2019-02-06T15:00:00.000Z'
    financial_fingerprint: '<64 lowercase hexadecimal characters>'
    civil_day: '2019-02-06'
    provenance:
      path: 'entries/synthetic-activity-id.yaml'
      sha256: '<SHA-256 of the retained entry-context file>'
```

The referenced private YAML must be the retained entry context, not a day
assertion reconstructed from current runtime settings. Its exact fields are
`schema_version: 1`, `activity_id`, `account_id`, `stored_date`,
`financial_fingerprint`, `entered_day` and `entry_timezone` (the historical IANA
entry timezone). Paths must stay under `/state/`; symlinks are refused. The
connector checks the retained bytes against SHA-256, binds the context to the
same activity/account/timestamp/fingerprint, and verifies that the stored instant
in the retained entry timezone yields the original entered day and `civil_day`.
A missing file, changed hash, inconsistent context or unsupported timezone leaves
the day unverified. A free-text reference cannot establish a day. Retain original
entry evidence; do not fabricate historical context to pass reconciliation.

The fingerprint is `activity_financial_fingerprint` of the normalized captured
activity. It binds account, UTC day, type, symbol, data source, currency, quantity,
unit price and fee. The separate stored timestamp binds the original time exactly.
A changed row invalidates its evidence. Use only evidence that establishes the
historical entry day; today's server timezone or matching UTC/local display dates
do not establish it. This file records provenance, not permission to import or
correct financial data. Keep it and its supporting evidence off Git, with private
permissions. Runs never ask for confirmation or create this evidence implicitly.

Without explicit legacy acceptance, unverified day provenance for the same account/instrument/type cannot prove that
a notice is new, even when its stored UTC date is distant. Uncertain dates,
financial conflicts and ambiguous multiplicity stop the entire run with
`NOTICE_MANUAL_OVERLAP_AMBIGUOUS`, zero financial writes and a diagnostic reason.
Malformed evidence refuses with `NOTICE_DAY_CONTEXT_INVALID` before broker access.
No existing activity is changed or adopted by writing a comment.

For explicitly approved existing history, the same private file can additionally
contain this grant. It records a known limitation, not historical proof:

```yaml
approved_legacy_baseline:
  snapshot_path: legacy-snapshot.json
  snapshot_sha256: '<SHA-256 of the complete retained activities snapshot>'
  account_id: synthetic-destination
  display_timezone: Europe/Zurich
  approval_reference: 'Explicit operator approval of this bounded existing history'
```

The snapshot must contain all activities and an exact `count`. It stays private
under `/state/`, without symlinks. The connector binds every manual row in the
approved account by ID, stored timestamp, exact financial fields, profile identity,
comments and activity/account inclusion context. Changed, missing or additional
manual history refuses with `NOTICE_LEGACY_BASELINE_MISMATCH`; invalid configuration,
hash, path or snapshot refuses with `NOTICE_LEGACY_BASELINE_INVALID` before broker
access. New connector-owned rows retain independent exact checks. Runs never
create or refresh approval automatically.

Displayed days in the declared timezone carry
`approved_legacy_display_convention` provenance. They remain an uncertain
convention. Genuine retained entry receipts take precedence. This grant supplies
no execution order, financial correction or import permission. Exact amounts,
fees, instruments, multiplicities and nearby-conflict refusal remain enforced.
Complete offline simulation must pass before distinct real-import authorization.
Historical stock-day proof applies only to instruments with a pending SELL;
purchase-only and dividend-only instruments do not require that proof.

Before overlap refusal, `NOTICE_SIMILAR_ACTIVITY` lists every same-account,
established-symbol and same-type candidate within inclusive ±3 civil days for
trades or ±4 for dividends. There is no amount or fee cutoff. Each source row's
candidates are ordered by absolute total difference; unavailable comparisons
come last. Diagnostics show source/destination days and provenance, signed day
gap, quantities, unit prices, Decimal quantity × price totals and fees. EUR and
percentage differences mean destination minus source; the percentage is relative
to the source total. A zero source total leaves the percentage `unverified`.
Unproved days or financial context remain `unverified` and cannot establish that
an activity is new. Dividend source totals are net credits, with no inferred
gross amount or withholding.

`automatic_duplicate` means an exact owned match or a proven one-to-one manual
match. `represented_other_notice` identifies a row already consumed by another
exact notice match. Unresolved candidates show `review_required`. All rows and
missing evidence are reported before whole-run refusal, without confirmation or
financial writes.
Reconcile conflicts outside the run, retain the entry evidence for the resulting
snapshot, then rerun simulation. The same automatic rules apply again; remaining
conflicts still refuse. These diagnostics never select an instrument mapping or
change an existing activity. Actual import acceptance remains a separate step.

After deduplication, each pending SELL is checked against stock on its civil
day. Existing destination sales from the first pending operation onward are
also checked, so later sales cannot consume the same stock twice.
The complete active account/instrument history contributes, including
purchases older than 90 days and prior sales. Later purchases cannot fund an
earlier sale. Pre-window stock and corporate actions must already be represented
in Ghostfolio. Manual history requires retained civil-day entry evidence.
Represented notices count once and retain their proven source execution order;
a manual stored timestamp alone never proves intraday order. Equal manual rows
retain the source quantity/time multiset for stock without inferring a timestamp
association with any particular manual row.

Preceding-day stock can cover same-day sales without proving the order of
same-day purchases. Otherwise only proven earlier source purchases contribute.
`NOTICE_INSUFFICIENT_HOLDINGS` or `NOTICE_HOLDINGS_ORDER_UNPROVED` stops the whole
run before writes, including simulation. Diagnostics include ISIN, symbol,
`sale_day`, `preceding_day_available`, `available`, `sale`, and dependent
purchases with missing order evidence. Candidate reporting finishes before this
check. No confirmation is requested.

Pending BUYs fund simulation only when they precede the sale. Skipped and
represented BUYs add no second quantity. The guard's confirmed-only mode excludes
every pending BUY: only
exact readback-confirmed destination purchases with proven chronology can fund
sales. Recheck after a rejected purchase before dispatching a dependent sale.

The private `boursedirect-state` volume retains source notices, acquisition
receipts, login journals, `discovery.yaml`, source bindings under `accounts/`,
`manual-day-context.yaml` and `runs/<id>/simulation.yaml`. The previous
`community-binding.yaml` is retained and reused for its original source account.
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

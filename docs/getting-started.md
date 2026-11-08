# Getting started

Check the [release availability](../README.md) before using folder input.

Use Docker Engine and Compose v2 on Linux amd64 or arm64. Prepare a reachable
Ghostfolio instance and its backup procedure first. Keep the final service URL:
redirects are rejected before credentials can leave the configured origin.
Use HTTPS across hosts. Private HTTP is suitable only on your trusted network.
The connector requires complete, unmasked account and activity responses.
A release watcher baseline is not a minimum supported Ghostfolio version.
Use the retained lab receipt for the tested destination of each release;
compatibility with an untested version is not guaranteed.

## 1. Get the operator bundle

Download the versioned archive and `SHA256SUMS` from the selected
[release](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases).
Verify the checksum before extraction. Commands below use the extracted bundle.
They need no source checkout or local image build. Keep `IMAGE_DIGEST` with it.
It identifies the exact qualified image; keep the previous bundle for rollback.

```sh
umask 077
version=2.2.0
release="https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/download/v$version"
curl --fail --location --remote-name "$release/ghostfolio-boursedirect-sync-v$version.tar.gz"
curl --fail --location --remote-name "$release/SHA256SUMS"
sha256sum --check SHA256SUMS --ignore-missing
tar -xzf "ghostfolio-boursedirect-sync-v$version.tar.gz"
cd "ghostfolio-boursedirect-sync-v$version"
cp .env.example .env
chmod 600 .env
sudo install -d -m 0700 -o 10001 -g 10001 review
```

Require the archive checksum to report `OK`. Stop if a download or verification
fails. `--ignore-missing` skips other release assets that you did not download.
The extracted bundle contains `IMAGE_DIGEST`. For another release, change
`version` and read that release's instructions.

Use one installation directory and one service for each source/target account.
A second account needs separate `.env`, review directory and Compose project
(`COMPOSE_PROJECT_NAME`). Never share review journals between targets.

## 2. Set Ghostfolio and choose one source

In Ghostfolio, open **Account → Access → Security Token**. Keep that token
private. Set `GHOST_ACCESS_TOKEN` to it and leave `GHOST_TOKEN` empty. The importer
exchanges the Security Token for a session bearer on each run. A copied session
bearer in `GHOST_TOKEN` is an alternative, but it can expire between runs.
Set exactly one credential mode. Never put a token on a command line or in an issue.

Set `GHOST_HOST` and the exact `GHOST_ACCOUNT_NAME`. The account must be unique,
active and included in analysis. Use full account access, not restricted public
view access. Set `BD_ACCOUNT_REF` to the account reference after `COMPTE N°` on
the PDF. Remove spaces. Exclude the currency suffix `EUR` and the account type
`PEA` or `PEA-PME`. Text extraction can join `EUR` to the reference.
If `other_account_notices` excludes your intended files, fix this setting before
importing. Exit 0 alone does not prove that the intended account was selected.

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
Follow [Paperless setup](configuration.md#paperless-setup) before the first simulation.

Keep `MAPPING_FILE` empty for automatic lookup. To keep the same symbols across
simulation, import and repeat, freeze the mapping for every selected ISIN.
In Ghostfolio's activity editor, search for each Yahoo ticker and check its
currency. Close the editor without saving an activity. For a foreign share
bought in EUR, use the [EUR listing guide](troubleshooting.md#foreign-shares-bought-in-eur).
Live lookup can be ambiguous or change between runs.

Copy `config/mappings.example.yaml` to private `config/mappings.yaml`. Replace
the synthetic entry with your verified `ISIN: TICKER` lines under `symbol_mapping`.
Set `MAPPING_FILE=/config/mappings.yaml`. Keep that file unchanged for the three
runs. Give GID 10001 read access as described in [mapping setup](../config/README.md).

The base Compose uses the public image and normal Docker egress. For an existing
private Docker network, append `:compose.ghostfolio.yaml` to `COMPOSE_FILE`, set
`GHOSTFOLIO_NETWORK` to its exact name, and use reachable internal service URLs.
The override adds that network. Use the Ghostfolio service name and its container
port on that network. `localhost` or `127.0.0.1` inside the importer refers to the
importer itself. A host-only loopback URL is not reachable through normal Docker
egress. Do not expose a private destination publicly to work around this.
A source checkout can use `compose.build.yaml` for development; release users
must not need it. `BOURSEDIRECT_IMAGE` can select an immutable digest explicitly.

## 3. Simulate and inspect

Keep `DRY_RUN=1` and `CRON=` in `.env`. Validate without printing resolved secrets.
Pull the image, then force one non-interactive simulation:

```sh
docker compose config --quiet
docker compose pull
docker compose run --rm -T --no-deps -e DRY_RUN=1 -e CRON= importer > simulation.log 2>&1
echo "Exit status: $?"
less simulation.log
```

Read the exit status and each proposed date, type, symbol, quantity, price and
fee. Inspect the source-file/document counts, unreadable count and review/action
counts. Exit 0 can still require a user action. Preserve private logs locally.
Never share full financial logs or resolved Compose output. `--rm` removes the
one-off container. Save stdout and stderr as above; `docker compose logs` cannot
retrieve that removed container's output. Save coverage, import and repeat logs
in separate private files in the same way.

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
Review every proposal before enabling writes. See [review rules](maintenance.md#operator-review-and-reconciliation).

## 4. Import once, verify, then schedule

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
Read [recovery](troubleshooting.md) before another run.

After a confirmed import, repeat the same command once. Require zero new
activities and zero repeated corrections. File renaming, copies, relocation and
switching sources retain `BD#v3` financial identities. Identical bytes share a
`sha256:` document identity. Different bytes change source evidence; they do not
replace destination duplicate checks or authorize another activity.

Only then set `DRY_RUN=0`, an explicit `TZ` and `CRON` in `.env`, for example
`CRON=0 6 * * *`. Use `docker compose up -d` only with a nonempty valid `CRON`.
The `unless-stopped` policy repeats an empty-CRON run after it exits.
An invalid CRON can repeat failure notifications. Stop the service immediately
with `docker compose stop importer`, fix `.env`, then recreate it. Use
`docker compose run --rm` for one-off work. Check private logs and the
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

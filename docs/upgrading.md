# Upgrading

Read the selected [GitHub Release](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases)
before changing the image. Check its tested destination and retained qualification.
Do not assume compatibility with untested Ghostfolio versions.

1. Stop the scheduled importer with `docker compose stop importer`.
2. Verify a Ghostfolio backup. Save `.env`, mapping, originals and the complete
   private review directory while stopped. Keep its ownership and modes.
3. Download the new operator bundle and verify `SHA256SUMS`. Keep the old bundle
   and `IMAGE_DIGEST`. Compare new ENV defaults before transferring private settings.
4. Select the qualified image. Remove a stale `BOURSEDIRECT_IMAGE` override or
   set the intended exact digest. Run `docker compose config --quiet`, then pull.
5. Follow [Getting started](getting-started.md#3-simulate-and-inspect) with forced
   `DRY_RUN=1` and `CRON=`. Inspect proposals, duplicates, holds and coverage.
6. Run one deliberate import and verify its result. Resume the schedule only
   after exact readback and the duplicate check succeed.

v2.2 adds folder input. Keep Paperless configured until you deliberately select
the folder override. Do not mix sources. A source switch preserves financial
identities. Changed source evidence can clear review consent. It never settles
pending write uncertainty.

v2 requires a private `ACTIVITY_REVIEW_FILE` for corrections, including TTF with
profile `off`. Keep its companions across upgrades. v0.1.1 is a legacy preview;
its broker collector is not part of the current importer.

## Image tags and rollback

`:latest` tracks the current stable release. Version tags use `X.Y.Z`.
Pin `@sha256:...` for controlled upgrades. Candidate tags never replace `:latest`.
The operator bundle pins the exact qualified version and digest. The release
process promotes those bytes without rebuilding them.

To roll back the program, stop the service and select the previous bundle's
image digest and compatible ENV. Retain every review and recovery file.
Simulate and inspect before restarting. An image rollback cannot undo accepted
financial activities. Restore data only through the verified backup procedure.

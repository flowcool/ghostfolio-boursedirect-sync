# Changelog

User-visible changes are listed by release. Older statement-based CLI and lab
history remains available in Git (tag `legacy-wip`).

## v2.2.0 (unreleased)

- Add read-only PDF folder input with content identity, unchanged financial
  duplicate checks and digest-bound stop waivers. Keep Paperless optional.
- Retain unreadable write blocks, printed-date cut-offs, review and coverage.
- Use a portable released-image Compose path and optional source/network mounts.
- Include the optional mapping example in the operator bundle.
- Update installation, Paperless permissions, recovery, support and privacy guidance.
- Prepare community announcement text as an unsent draft. No release or topic change.

## v2.1.0

Released manual reconciliation and available-notice coverage. See the
[release record](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/tag/v2.1.0)
for qualified artifacts and changes.

## v2.0.0

Released persistent operator review and reconciliation profiles. See the
[release record](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/tag/v2.0.0).

## v1.0.0

Released the PDF-notice importer with read-only Paperless input, BUY/SELL/coupon
imports, exact readback, charged TTF, duplicate guards and unattended scheduling.
See the [release record](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases/tag/v1.0.0).

## v0.1.1

- Made the public quick start Docker-first with copyable Compose and environment
  settings; downloading the operator archive is optional.
- Added clearer configuration, synthetic preview examples, a README banner,
  safe support reporting and broker-site requalification guidance.
- Removed build-only curl, unzip and Python venv tooling from the final image,
  while retaining system Python, application dependencies and pinned CLI/browser.
- Aligned image builds and CI with the supported AMD64-only connection path.
- Pinned release archive Compose and README image references to the exact pushed
  image digest, verified against the image that passed scan and offline smoke.
- Added a checksummed `IMAGE_DIGEST` release asset and image smoke regressions.
- Corrected release/security scan documentation and added hostile-title label tests.
- Acquisition remains one-shot and preview-only; account, credential and financial
  behavior is unchanged. Existing published v0.1.0 assets remain available.

## v0.1.0

- Added a one-shot AMD64 Docker Compose flow that unlocks a Bitwarden-compatible
  vault, connects to Bourse Direct and saves operation notices offered during a
  rolling 90-day window.
- Added selection and persistent binding of one Bourse Direct PEA or PEA-PME and
  one existing Ghostfolio account. Explicit account fields are honored, and
  conflicts with retained selection stop the run.
- Added a local Ghostfolio snapshot and preview for supported EUR buys, sells and
  net-received dividends using Bourse Direct's booking date.
- Added private retention of original documents, receipts, account and activity
  snapshots, preview reports and recovery journals in a named Compose volume.
- Added diagnostics for missing mappings, currency conflicts, unsupported
  operations and differences from existing Ghostfolio activity.
- Added a narrowly scoped option for an existing private Docker network using
  exactly `http://ghostfolio:3333`; other HTTP origins are refused.
- Financial writes and automatic scheduling are not part of this release.

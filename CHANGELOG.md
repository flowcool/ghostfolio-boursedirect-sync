# Changelog

User-visible changes are listed by release. Older statement-based CLI and lab
history remains available through the [documentation archive](docs/archive/README.md).

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

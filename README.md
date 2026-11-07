# Bourse Direct to Ghostfolio

Import original Bourse Direct PDF operation notices into one Ghostfolio account.
Use a read-only folder or an existing Paperless-ngx service. The importer has no
broker login and no vault access. It adds activities and prevents duplicates.
Simulation is the default. Paperless is always read only.

**v2.2.0 is unreleased.** Folder input and digest waivers require this candidate
or a later released bundle. The last stable release is v2.1.0. Its image does not
support folder input. Its immutable image is
`ghcr.io/flowcool/ghostfolio-boursedirect-sync:2.1.0@sha256:2949c5773dab862590a3dabbaf2bb52495d759f37c615f9cfdb72b66bbcd6c76`.
The release process replaces the bundle image reference
with its qualified digest. Do not use a v2.1.0 image to test the v2.2 instructions.

[Releases](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases) ·
[Questions and bugs](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues) ·
[Contribute](CONTRIBUTING.md) · [Changes](CHANGELOG.md)

## Install

Follow [Getting started](docs/getting-started.md) for the operator bundle,
folder or Paperless setup, simulation, one verified import and scheduling.
Use one service and private review directory per source/target account.

`:latest` tracks the current stable release. Version tags use `X.Y.Z`.
Pin `@sha256:...` for controlled upgrades. Candidate tags never replace `:latest`.
The operator bundle pins its qualified version and digest.

## Documentation

- [Getting started](docs/getting-started.md): install and verify the first run.
- [Configuration](docs/configuration.md): ENV, Paperless permissions, mapping and logs.
- [Troubleshooting](docs/troubleshooting.md): exact log symptoms and safe recovery.
- [Upgrading](docs/upgrading.md): image tags, backups and rollback limits.
- [Maintenance](docs/maintenance.md): financial limits, review, coverage and notifications.
- [Contributing](CONTRIBUTING.md): source setup and offline checks.

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

## License

The project uses the [MIT NON-AI License](LICENSE). It includes additional
restrictions and is not the standard MIT license. Read it before use or contribution.

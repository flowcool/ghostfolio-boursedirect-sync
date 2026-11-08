# Documentation

Start with [Getting started](getting-started.md) for installation, simulation and
the first verified import. Return to the [project overview](../README.md).

## User reference

| Reference | Contents |
| --- | --- |
| [Configuration](configuration.md) | ENV settings, Paperless permissions, mapping, schedule and logs |
| [Supported notices](supported-notices.md) | Account types, operation labels and financial limits |
| [Maintenance](maintenance.md) | Amount checks, corrections, review files, coverage and notifications |
| [Troubleshooting](troubleshooting.md) | Error codes, blocked operations and safe recovery |
| [Upgrading](upgrading.md) | Image selection, backups, source changes and rollback |
| [Symbol mapping](../config/README.md) | Verified EUR ticker overrides |

Use the instructions supplied with your selected release. See
[GitHub Releases](https://github.com/flowcool/ghostfolio-boursedirect-sync/releases)
and the [changelog](../CHANGELOG.md) for published changes.

## Project reference

| Reference | Contents |
| --- | --- |
| [Contributing](../CONTRIBUTING.md) | Development setup, offline checks and contribution scope |
| [Build guarantees](../.github/BUILD.md) | Package contents, image qualification and security checks |
| [Release process](operations/releasing.md) | Maintainer publication procedure |
| [Upstream references](upstreams.md) | Ghostfolio release watch and BillCollector interfaces |

Historical release notes apply to their original versions. The removed broker
collector and laboratory procedures remain in Git history. Provider recipes
belong to `billcollector-recipes`. BillCollector owns the engine and broker/vault
access. Infra owns production deployment and Paperless delivery.

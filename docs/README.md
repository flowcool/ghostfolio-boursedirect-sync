# Documentation map

The published v1 reads Bourse Direct PDF notices from Paperless. Start with the
[top-level README](../README.md). The published v0.1.1 is a legacy preview only.

- [Contributing](../CONTRIBUTING.md): source setup and offline checks.
- [Build guarantees](../.github/BUILD.md): package, image and security checks.
- [Release process](operations/releasing.md): retained publication tooling.
- [Upstream references](upstreams.md): Ghostfolio release watch and BillCollector interfaces.
- [Configuration mappings](../config/README.md): optional symbol overrides.
- [Changelog](../CHANGELOG.md): published version history.

Historical release notes describe their original versions. The removed broker
collector and laboratory procedures remain in Git history. BillCollector owns
broker acquisition. The v1 importer has no broker login or vault access.

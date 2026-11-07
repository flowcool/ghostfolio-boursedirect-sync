# Documentation map

Start with the current [installation guide](../README.md#install). v2 includes
operator review and coverage. v2.2.0 adds optional folder input and is unreleased.
Paperless remains supported. v0.1.1 is a legacy preview only.

- [Contributing](../CONTRIBUTING.md): source setup and offline checks.
- [Build guarantees](../.github/BUILD.md): package, image and security checks.
- [Release process](operations/releasing.md): retained publication tooling.
- [Upstream references](upstreams.md): Ghostfolio release watch and BillCollector interfaces.
- [Configuration mappings](../config/README.md): optional symbol overrides.
- [Changelog](../CHANGELOG.md): published version history.

Historical release notes describe their original versions. The removed broker
collector and laboratory procedures remain in Git history. Provider recipes
belong to `billcollector-recipes`; BillCollector owns the engine and broker/vault
access. Infra owns production deployment and Paperless delivery. The importer
has no broker login or vault access.

# Documentation map

Use this page to find the current operator guidance and the historical project
record. The product's supported path is the AMD64 Docker Compose acquisition and
preview described in the [top-level README](../README.md).

## Use the release

- [v0.1.0 release notes](releases/v0.1.0.md): supported behavior and known limits.
- [Configuration mappings](../config/README.md): private, verified ISIN mappings.
- [Source connection](operations/source-connection.md): authorized connection and
  recovery procedure.
- [Release process](operations/releasing.md): tagged image and archive publication.
- [Build and release guarantees](../.github/BUILD.md): CI, scanning and rollback.
- [Changelog](../CHANGELOG.md): user-visible changes by release.
- [License](../LICENSE) and [Playwright third-party license](../collector/licenses/playwright-LICENSE).

## Understand or change behavior

- [Design contracts](design/index.md): current acquisition, account, financial,
  preview and recovery boundaries.
- [Plans](plans/README.md): historical proposals and implementation plans.
- [Reviews](reviews/README.md): historical independent review findings.

Plans, reviews and archived CLI material record earlier project stages. They are
not additional product entrypoints or a substitute for the v0.1.0 release notes.
The previous statement-based CLI guide is preserved in the
[archive](archive/README.md) for source-checkout research only.

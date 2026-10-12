# Security

Report suspected credential leaks or security vulnerabilities privately using
[GitHub private vulnerability reporting](https://github.com/flowcool/ghostfolio-boursedirect-sync/security/advisories/new).
Do not include Bourse Direct credentials or one-time codes, Ghostfolio tokens,
account identifiers, statements or contract notes in public issues or pull
requests.

Security fixes target the current `main` branch. Older revisions do not receive
separate backports. Dependency checks run on pull requests and weekly. This
repository publishes an AMD64 connector image to GHCR and a checksummed operator
archive through the [release workflow](workflows/release-image.yml). Images are
scanned for fixable HIGH/CRITICAL vulnerabilities and smoke-checked offline before
publication. See the [build guarantees](BUILD.md) and
[release procedure](../docs/operations/releasing.md). No workflow deploys services
or writes financial activity in Ghostfolio.

For non-security support, share only fixed terminal error codes, the connector
version/image digest, architecture, and Docker/Compose versions. Follow the
[safe reporting procedure](../README.md#troubleshooting); Docker log retention is
disabled and private acquisition receipts must not be posted publicly.

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

## Dependency updates

Keep the dependency graph, Dependabot alerts and Dependabot security updates
enabled. Dependabot remains the security update PR author; Renovate owns
ordinary dependency updates. The Dependabot version PR limit is zero, which
does not disable security PRs. Renovate's `vulnerabilityAlerts` and
`osvVulnerabilityAlerts` are disabled. Container base image updates wait 3 days
after release. All merges remain manual.

See [dependency update rules](BUILD.md#dependency-updates), [Dependabot security
updates](https://docs.github.com/en/code-security/dependabot/dependabot-security-updates/about-dependabot-security-updates)
and [Renovate vulnerability alerts](https://docs.renovatebot.com/configuration-options/#vulnerabilityalerts).

For non-security support, share only fixed terminal error codes, the connector
version/image digest, architecture, and Docker/Compose versions. Follow the
[safe reporting procedure](../README.md#troubleshooting); Docker log retention is
disabled and private acquisition receipts must not be posted publicly.

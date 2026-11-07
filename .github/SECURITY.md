# Security

Report suspected credential leaks or security vulnerabilities privately. Use
[GitHub private vulnerability reporting](https://github.com/flowcool/ghostfolio-boursedirect-sync/security/advisories/new)
when the **Report a vulnerability** button is available. If it is unavailable,
open a [contact request](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues/new)
that says only "Private security contact requested". Include no vulnerability
details or private evidence. Wait for a private route before sharing them.
Do not include Bourse Direct credentials or one-time codes, Ghostfolio tokens,
account identifiers, statements or contract notes in public issues or pull
requests.

Security fixes target the current stable line through `main`; install the latest
patched stable release when available. Older revisions do not receive
separate backports. Dependency checks run on pull requests and weekly. This
repository publishes amd64 and arm64 connector images to GHCR and a checksummed operator
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
[safe reporting procedure](../README.md#troubleshooting); Docker retains logs according to your daemon configuration. Keep full financial
logs, originals, review files and acquisition receipts private.

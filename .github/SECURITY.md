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

## Dependency security handover

Keep the dependency graph and Dependabot alerts enabled throughout the handover.
Keep Dependabot security updates enabled until both conditions are confirmed:

1. Renovate's onboarding PR is merged after CI and the final-head review.
2. The [hosted Renovate job](https://developer.mend.io/github/flowcool/ghostfolio-boursedirect-sync)
   completes successfully using the merged configuration, with read access to
   Dependabot alerts and no unresolved dependency lookup or configuration errors.

Then disable **Dependabot security updates** in repository Settings, Advanced
Security. Keep **Dependabot alerts** and **Dependency graph** enabled. This leaves
Renovate as the sole ordinary and security update PR author. Re-enable Dependabot
security updates if Renovate stops processing alerts. A local validator or an
onboarding preview alone does not prove the hosted handover.

See [dependency update rules](BUILD.md#dependency-updates) and
[Renovate vulnerability alerts](https://docs.renovatebot.com/configuration-options/#vulnerabilityalerts).

For non-security support, share only fixed terminal error codes, the connector
version/image digest, architecture, and Docker/Compose versions. Follow the
[safe reporting procedure](../README.md#troubleshooting); Docker log retention is
disabled and private acquisition receipts must not be posted publicly.

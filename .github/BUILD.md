# Build and release guarantees

## Pull request checks

Every pull request runs the versioned offline Python suite, the
documentation catalogue and local-link check, and a whitespace check. The
container workflow builds, smoke-checks and scans the native connector image for
AMD64 and ARM64 without publishing it. CodeQL analyzes Python, and Dependency Review blocks
new moderate-or-higher dependency findings, including development dependencies.
All workflows use read-only repository access unless a specific job needs a
narrower permission grant.

CI tests use anonymized notice text, mocked requests and isolated state. They
never use broker credentials or production Ghostfolio. Shared lab tooling stays
in Infra. The importer has no broker collector, browser or vault client.

The offline job uses GitHub's Python build. The native image smoke uses the
shipped Docker build and requires C `_decimal`. Different Decimal backends are
accepted when both builds pass qualification. Run the full offline suite with
both builds when qualifying a Python release.
CI repeats the full suite with the GitHub build. Its image smoke checks exact
Decimal values from a real anonymized BUY with the shipped C backend. This
smoke check does not replace the full suite during runtime qualification.

## Dependency updates

GitHub's dependency graph and Dependabot alerts stay enabled. Renovate is the
ordinary update PR author, configured in [`renovate.json`](../renovate.json).
Dependabot version PR limits are zero; this does not disable security PRs.

Ordinary updates run before 9am on Monday in Europe/Zurich. Renovate opens at
most three concurrent pull requests and two per hour. Python
releases wait 14 days; GitHub Actions wait 3 days.
Container base image updates wait 3 days. Minor, patch and digest updates are
grouped by ecosystem; major updates stay separate and require Dependency
Dashboard approval. Exact Python versions, Action commit SHAs and existing
image digests stay pinned for reproducible checks. Follow the latest stable
Python, Node and base-image releases without version ceilings. Renovate proposes
updates; tests, security scans and required review gate integration. Python CI
and the native image use the same release. Docker tag suffixes retain the
selected image variant.
Compose references are local builds, so the docker-compose manager is excluded.
The collector npm manifests and browser/vault download watches are removed.

Dependabot security updates remain enabled in repository settings. Renovate's
`vulnerabilityAlerts` and `osvVulnerabilityAlerts` are disabled, so Dependabot
remains the security update PR author while Renovate handles ordinary updates.
Dependabot version PR limits are zero; this does not disable security PRs. All
merges remain manual. Existing CI and final-head Pullfrog review requirements
still apply; review filters include `renovate.json`.

Validate repository configuration with the official validator (Node 24.11+):

```sh
npx --yes --package renovate -- renovate-config-validator --strict
```

## Qualified release

`Prepare release candidate image` runs manually on `main`. It uploads native
AMD64 and ARM64 candidates by digest. It scans and smoke-checks those exact
images, then assembles and signs their index. Each native candidate builds once.
No stable version or `latest` changes during preparation.

After both Infra labs qualify that exact index and end stopped, attach the
bounded `lab-qualification.json` to a prepared stable GitHub release. Require
operator approval before publishing. A tag push alone does not publish.
The release workflow verifies the signature, source, native identity and both
lab receipts. It copies the exact index to `X.Y.Z` and reads back its digest.
It updates and verifies `latest` only for the current stable release.
No RC channel or rebuild is required. A failed publication stops for inspection.

The publication workflow retains the digest-pinned operator archive,
`IMAGE_DIGEST` and `SHA256SUMS`. It verifies the index and both native digests
against the qualified record before packaging. Source Compose retains its local
build; bundled Compose uses the qualified image. The archive includes public
configuration examples and tracked docs, plus the public GitHub release notes.
It excludes application source, build context and private files.
See the [release procedure](../docs/operations/releasing.md) for candidate
failure recovery, registry visibility and the operator checklist.

## Release notes and automation

`release.yml` groups GitHub-generated notes by label. `pr-release-labels.yml`
derives advisory labels from conventional PR titles. It runs on
`pull_request_target` using the base-branch workflow and script; it must not
check out or execute PR-head code. A breaking-change or compatibility PR should
fill in the release-impact section of the PR template.

## Rollback

Correct a released defect with a new versioned release and retain earlier image
tags and archives so operators can intentionally return to a prior version.
Revert maintenance changes through a reviewed pull request and required checks.
No GitHub workflow deploys to or writes financial activity in Ghostfolio.

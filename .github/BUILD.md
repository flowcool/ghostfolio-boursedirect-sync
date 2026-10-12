# Build and release guarantees

## Pull request checks

Every pull request runs the versioned offline Python and Node.js suites, the
documentation catalogue and local-link check, and a whitespace check. The
container workflow builds and scans the connector image for AMD64 and ARM64
without publishing either image. The ARM64 build-and-scan check detects build
and image-vulnerability regressions; it does not qualify the browser-dependent
product path, which remains AMD64-only. A separate build and scan covers the
saved-input preview image. CodeQL analyzes
Python and JavaScript, and Dependency Review blocks new moderate-or-higher
dependency findings, including development dependencies.
All workflows use read-only repository access unless a specific job needs a
narrower permission grant.

The opt-in disposable acceptance lab is not run by CI. It uses local Docker,
synthetic data and resources owned by the invocation. CI tests use synthetic
inputs and isolated state; they must never use broker credentials or production
Ghostfolio.

## Tagged release

Pushing a version tag starts `release-image.yml`. The release job builds the
AMD64 container, scans it, and runs an offline smoke check. Only after those
checks pass does it publish the versioned image to GHCR and create a
GitHub draft release with the Compose archive and `SHA256SUMS`. An operator then
verifies an anonymous pull of the versioned image and publishes the draft;
the publication event promotes that same version to `latest`. A new GHCR package defaults to private and may need its visibility changed to public in
package settings before it can be pulled anonymously; see GitHub's
[container registry visibility guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
The release archive pins the matching image version and includes the required Compose files,
browser seccomp profile, example environment file, configuration guide,
third-party license text and tracked documentation. It excludes application
source and local build inputs.

See the [release procedure](../docs/operations/releasing.md) for the operator
checklist and the [v0.1.0 notes](../docs/releases/v0.1.0.md) for the initial
supported product scope. The normal Compose file uses the published image;
`compose.build.yaml` is only for a local source checkout.

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

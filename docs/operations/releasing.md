# Releasing

Releases are produced from a reviewed version tag. A tag push starts the
`release-image.yml` workflow, which builds the `linux/amd64` image, scans it, and
runs its offline smoke check before publishing. On success, it publishes the
versioned GHCR image, then creates a GitHub draft release
with the Compose user archive and its `SHA256SUMS` attached. A failed earlier
stage must not leave a release that appears ready to operators.

Before publishing the draft, verify that the versioned image can be pulled from
GHCR anonymously. GitHub's first publication of a package defaults to private;
for the first release, make the package public in its package settings before
the anonymous-pull check. Only then publish the draft release. The publication event promotes the checked
version to `latest` after confirming that it is still the latest stable release. See GitHub's
[container registry visibility guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

The user archive contains the Compose files and required browser seccomp profile,
third-party license text, example environment file, mapping guide, README,
CONTRIBUTING, CHANGELOG, LICENSE, and tracked documentation. It does not contain
the application source, Docker build context, or local build override. The image
tag is pinned to the release version in the bundled default Compose file.

## Release checklist

1. Update the changelog, release notes, versioned image reference and release
   documentation together.
2. Review the final diff and confirm the source connection, account binding,
   preview-only and credential-handling claims against the implementation.
3. Require final-head CI and review. The release workflow must build, scan and
   smoke-check the AMD64 image from the pushed tag before publishing the image.
4. Push the approved `vX.Y.Z` tag. Wait for the workflow to publish the versioned
   image tag and attach the archive and checksums to a draft release.
5. For a new GHCR package, set package visibility to public. Verify an anonymous
   pull of the versioned image, then publish the GitHub draft release. Confirm the
   publication workflow promotes that version to `latest`.
6. Download the archive and checksum file from the published release, verify
   them with `sha256sum -c SHA256SUMS`, and inspect the extracted Compose files
   and documentation links.

The first product release is documented in [v0.1.0 notes](../releases/v0.1.0.md).
The source checkout's [build guarantees](../../.github/BUILD.md) describe the
checks that run before release. Roll back a bad release by publishing a corrected
version; retain prior versioned images and artifacts for users who need to return
to them.

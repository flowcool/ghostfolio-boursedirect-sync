# Releasing

Releases are produced from a reviewed version tag. A tag push starts the
`release-image.yml` workflow, which builds the `linux/amd64` image, scans it, and
runs its offline smoke check before publishing. On success, it publishes the
versioned GHCR image, then creates a GitHub draft release
with the Compose user archive, `IMAGE_DIGEST`, and `SHA256SUMS` attached. A failed earlier
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
reference is pinned to the release version and the pushed image's SHA256 digest
in the bundled default Compose file. `IMAGE_DIGEST` contains that exact reference
inside the archive and as a separate release asset. `SHA256SUMS` covers the archive
and the separate reference file. The workflow validates public inputs before
building, then packages only after the scanned/smoked image is pushed and its
repository digest is available. Existing published archives are never rewritten.
Before packaging, the workflow verifies that the raw registry manifest hashes to
that digest and its `config.digest` equals the local image ID retained before the
scan. The tag must still identify that same checked local image before push. This
binds the published manifest to the scanned/smoked image without confusing a local
image ID with a registry digest. See Docker's
[registry manifest inspection](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/).

## Release checklist

1. Update the changelog, release notes, versioned image reference and release
   documentation together.
2. Review the final diff and confirm the source connection, account binding,
   preview-only and credential-handling claims against the implementation.
3. Require final-head CI and review. The release workflow must build, scan and
   smoke-check the AMD64 image from the pushed tag before publishing the image.
4. Push the approved `vX.Y.Z` tag. Wait for the workflow to publish the versioned
   image tag and attach the digest-pinned archive, `IMAGE_DIGEST` and checksums to
   a draft release.
5. For a new GHCR package, set package visibility to public. Verify an anonymous
   pull using the exact reference in `IMAGE_DIGEST`, then publish the GitHub draft release. Confirm the
   publication workflow promotes that version to `latest`.
6. Download the archive and checksum file from the published release, verify
   them with `sha256sum -c SHA256SUMS`, and inspect the extracted Compose files
   and documentation links. Confirm Compose and both copies of `IMAGE_DIGEST`
   contain the same repository/version/digest reference. Digest pinning establishes
   content identity; it does not sign or attest the publisher.

The first product release is documented in [v0.1.0 notes](../releases/v0.1.0.md).
The source checkout's [build guarantees](../../.github/BUILD.md) describe the
checks that run before release. Roll back a bad release by publishing a corrected
version; retain prior versioned images and artifacts for users who need to return
to them.

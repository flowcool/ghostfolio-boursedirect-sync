# Releasing

Release preparation and stable publication are separate actions. Neither action
establishes product readiness. Require the relevant service acceptance first.
No GitHub workflow writes financial activities to Ghostfolio.

## Prepare and qualify

1. Review the final source and require green CI and the completed Pullfrog review.
2. Run `Prepare release candidate image` on `main` with the intended `vX.Y.Z`.
   This uploads each native candidate by digest, with SBOM and provenance.
   It checks native AMD64 and ARM64 runtime and security. It builds each once.
3. Download the `candidate-image` artifact. It records the exact source commit,
   signed index digest and both checked native manifest digests.
4. Use the existing Infra labs to qualify that exact index in empty and golden
   scenarios. Retain proof and verify that both owned labs are stopped.
5. Add `labs.empty` and `labs.golden` to `candidate-image.json`. Each entry needs
   `status: PASS`, `cleanup: stopped` and the retained proof's `evidence_sha256`.
   Save the result as `lab-qualification.json`. Never reuse another image's proof.

No RC channel is required. Candidate names use `candidate-X.Y.Z-<full-commit>`.
A candidate name is immutable. The signing step can retry transient signing
failures within its original job. If that job fails after index creation, stop.
Do not rerun it or rebuild automatically. Retain the index and Action logs.
There is no automatic recovery command. A new candidate needs a new source
commit and new qualification. An approved manual recovery can reuse retained
bytes only after exact registry and signature checks.

## Publish on approval

Prepare a GitHub draft release for the intended `vX.Y.Z`. Its tag must identify
the exact qualified source commit. Attach `lab-qualification.json`. Write clear
operator notes and use GitHub's generated changelog with `.github/release.yml`.
Existing `docs/releases/` notes remain historical source documents. The new
bundle takes its release notes from the public GitHub release body.

Before publication, verify an anonymous pull of the candidate's exact digest.
A new GHCR package can default to private. Set its visibility to public when
needed. See [GitHub's registry visibility guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

Publish the draft only after explicit operator approval. A tag push alone runs
no release publication. `release-image.yml` checks source ancestry, authenticated
version absence, the bounded qualification record, signature, native manifests
and runtime/OCI identity. It copies the qualified index to `X.Y.Z`. It changes
`latest` only when this release is the current stable release. It reads back
both tags and requires the same exact index digest. It never rebuilds.

## Operator bundle

The publication workflow retains the deterministic Compose archive,
`IMAGE_DIGEST` and `SHA256SUMS`. The archive uses the exact qualified multiarch
index. It contains public Compose/configuration examples and tracked docs.
It excludes application source, build context and private files. Source Compose
keeps its local build. Bundled Compose replaces that build with the version and
digest-pinned image. The archive's release notes come from the public release.

Before packaging, require the raw index hash and both native manifest digests
to match the qualification record already verified by promotion. The image tag
is `X.Y.Z`; the GitHub release tag is `vX.Y.Z`. `SHA256SUMS` covers the archive
and the separate `IMAGE_DIGEST`. Verify downloaded assets with
`sha256sum -c SHA256SUMS`. Compare the bundled and separate image references.

Never replace published assets or overwrite an existing version tag. A failed
write or readback stops publication. It can leave a partial release. Inspect
Action logs and registry state before any recovery. Keep prior images and proof.
Fix a released defect with a new version. Runtime rollback does not undo
financial activities. See the [build guarantees](../../.github/BUILD.md).

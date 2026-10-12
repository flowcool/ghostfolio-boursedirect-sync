import hashlib
import json
import subprocess
import sys
import tarfile

import pytest

from scripts import release_package as package
from scripts.release_package import bundle_entries, create_bundle, image_reference, render_compose, require_stable_tag, verify_pushed_manifest


DIGEST = "sha256:" + "a" * 64


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def minimal_release_tree(root, tag):
    files = {
        ".env.example": "EXAMPLE=true\n",
        "CHANGELOG.md": "# Changes\n",
        "CONTRIBUTING.md": "# Contributing\n",
        "LICENSE": "license\n",
        "README.md": "# Operator bundle\n",
        "compose.yaml": "image: ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0\n",
        "compose.ghostfolio.yaml": "services: {}\n",
        ".github/BUILD.md": "# Build\n",
        "config/README.md": "# Config\n",
        "collector/browser-seccomp.json": "{}\n",
        "collector/licenses/playwright-LICENSE": "third party\n",
        "docs/releases/" + tag + ".md": "# Release\n",
    }
    for name, content in files.items():
        write(root, name, content)


def test_release_bundle_has_versioned_compose_and_only_public_allowlisted_files(tmp_path):
    root = tmp_path / "repo"
    output = tmp_path / "dist"
    files = {
        ".env.example": "EXAMPLE=true\n",
        "CHANGELOG.md": "# Changes\n",
        "CONTRIBUTING.md": "# Contributing\n",
        "LICENSE": "license\n",
        "README.md": "# Operator bundle\n[Build source](Dockerfile)\n[Bundle docs](docs/)\n[Source scripts](scripts/)\n",
        "Dockerfile": "FROM scratch\n",
        "compose.yaml": "services:\n  bitwarden:\n    image: ${BOURSEDIRECT_IMAGE:-ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0}\n",
        "compose.ghostfolio.yaml": "services:\n  bitwarden:\n    networks: [ghostfolio]\n",
        ".github/BUILD.md": "# Build\n",
        "config/README.md": "# Config\n",
        "collector/browser-seccomp.json": "{}\n",
        "collector/licenses/playwright-LICENSE": "third party\n",
        "docs/README.md": "# Docs\n",
        "docs/assets/readme-banner.svg": "<svg/>\n",
        "docs/releases/v1.2.3.md": "# Release\n",
        "docs/operations/guide.md": "# Guide\n[Import script](../../scripts/import.py)\n",
        "docs/archive/secret.md": "internal archive\n",
        "scripts/import.py": "print('source')\n",
        "config/mappings.yaml": "private: true\n",
        ".env": "SECRET=never\n",
        "tmp/receipt.json": "private\n",
    }
    for name, content in files.items():
        write(root, name, content)

    archive_path, sums_path = create_bundle(
        root,
        "v1.2.3",
        output,
        ["docs/README.md", "docs/assets/readme-banner.svg", "docs/releases/v1.2.3.md", "docs/operations/guide.md"],
        DIGEST,
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getnames()
        content = {name.split("/", 1)[1]: archive.extractfile(name).read() for name in members}

    prefix = "ghostfolio-boursedirect-sync-v1.2.3/"
    assert prefix + "collector/browser-seccomp.json" in members
    assert prefix + "docs/assets/readme-banner.svg" in members
    assert prefix + "docs/releases/v1.2.3.md" in members
    assert prefix + "config/mappings.yaml" not in members
    assert prefix + ".env" not in members
    assert prefix + "tmp/receipt.json" not in members
    assert prefix + "scripts/import.py" not in members
    assert prefix + "docs/archive/secret.md" not in members
    assert b"v1.2.3" in content["compose.yaml"]
    assert b"v0.1.0" not in content["compose.yaml"]
    reference = "ghcr.io/flowcool/ghostfolio-boursedirect-sync:v1.2.3@" + DIGEST
    assert reference.encode() in content["compose.yaml"]
    assert content["IMAGE_DIGEST"] == (reference + "\n").encode()
    assert (output / "IMAGE_DIGEST").read_bytes() == content["IMAGE_DIGEST"]
    assert b"[Bundle docs](docs/)" in content["README.md"]
    assert b"tree/v1.2.3/scripts)" in content["README.md"]
    assert b"blob/v1.2.3/scripts/import.py" in content["docs/operations/guide.md"]
    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    image_hash = hashlib.sha256(content["IMAGE_DIGEST"]).hexdigest()
    assert sums_path.read_text(encoding="utf-8") == (
        archive_hash + "  " + archive_path.name + "\n" + image_hash + "  IMAGE_DIGEST\n"
    )
    duplicate_archive, duplicate_sums = create_bundle(
        root,
        "v1.2.3",
        tmp_path / "repeat",
        ["docs/README.md", "docs/assets/readme-banner.svg", "docs/releases/v1.2.3.md", "docs/operations/guide.md"],
        DIGEST,
    )
    assert duplicate_archive.read_bytes() == archive_path.read_bytes()
    assert duplicate_sums.read_bytes() == sums_path.read_bytes()


@pytest.mark.parametrize("tag", ["latest", "edge", "v1.2", "v01.2.3", "v1.2.3-rc.1", "1.2.3"])
def test_only_stable_semver_release_tags_are_accepted(tag):
    with pytest.raises(ValueError, match="stable vX.Y.Z"):
        require_stable_tag(tag)


def test_release_entrypoint_rejects_invalid_tag_before_git_lookup(tmp_path):
    result = subprocess.run(
        ["python3", "scripts/release_package.py", "--tag", "edge", "--output-dir", str(tmp_path)],
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "stable vX.Y.Z" in result.stderr


def test_compose_refuses_missing_or_ambiguous_image_default():
    with pytest.raises(ValueError, match="exactly one"):
        render_compose(b"services: {}\n", "v1.2.3", DIGEST)
    with pytest.raises(ValueError, match="exactly one"):
        render_compose(
            b"image: ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0\n"
            b"image: ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0\n",
            "v1.2.3",
            DIGEST,
        )


def test_release_bundle_requires_a_regular_release_note(tmp_path):
    root = tmp_path / "repo"
    minimal_release_tree(root, "v1.2.3")
    (root / "docs/releases/v1.2.3.md").unlink()
    with pytest.raises(ValueError, match="release notes are missing"):
        create_bundle(root, "v1.2.3", tmp_path / "dist", [], DIGEST)

    minimal_release_tree(root, "v1.2.3")
    outside = tmp_path / "outside.md"
    outside.write_text("not part of this checkout\n", encoding="utf-8")
    (root / "docs/releases/v1.2.3.md").unlink()
    (root / "docs/releases/v1.2.3.md").symlink_to(outside)
    with pytest.raises(ValueError, match="release notes are missing"):
        create_bundle(root, "v1.2.3", tmp_path / "other-dist", [], DIGEST)


def test_compose_replaces_the_previous_digest_without_leaving_a_second_suffix():
    old = b"image: ${BOURSEDIRECT_IMAGE:-ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0@sha256:" + b"b" * 64 + b"}\n"
    expected = ("image: ${BOURSEDIRECT_IMAGE:-" + image_reference("v1.2.3", DIGEST) + "}\n").encode()
    assert render_compose(old, "v1.2.3", DIGEST) == expected


@pytest.mark.parametrize("digest", ["", "latest", "sha256:" + "a" * 63, "sha256:" + "A" * 64,
                                    "sha256:" + "g" * 64, DIGEST + "\n", DIGEST + ";echo bad"])
def test_invalid_image_digests_refuse_before_creating_any_release_output(tmp_path, digest):
    output = tmp_path / "dist"
    with pytest.raises(ValueError, match="image digest"):
        create_bundle(tmp_path / "missing-repo", "v1.2.3", output, [], digest)
    assert not output.exists()


def test_release_preflight_validates_inputs_without_creating_artifacts(tmp_path):
    root = tmp_path / "repo"
    minimal_release_tree(root, "v1.2.3")
    assert set(bundle_entries(root, "v1.2.3", [])) >= {"compose.yaml", "docs/releases/v1.2.3.md"}
    assert not (root / "IMAGE_DIGEST").exists()
    write(root, "README.md", "[Missing source](missing.py)\n")
    with pytest.raises(ValueError, match="broken local Markdown link"):
        bundle_entries(root, "v1.2.3", [])


@pytest.mark.parametrize("existing", ["IMAGE_DIGEST", "SHA256SUMS", "ghostfolio-boursedirect-sync-v1.2.3.tar.gz"])
def test_release_refuses_existing_outputs_without_replacing_them(tmp_path, existing):
    root = tmp_path / "repo"
    output = tmp_path / "dist"
    minimal_release_tree(root, "v1.2.3")
    write(output, existing, "previous artifact\n")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        create_bundle(root, "v1.2.3", output, [], DIGEST)
    assert (output / existing).read_bytes() == b"previous artifact\n"
    assert len(list(output.iterdir())) == 1


@pytest.mark.parametrize("media_type", ["application/vnd.docker.distribution.manifest.v2+json",
                                       "application/vnd.oci.image.manifest.v1+json"])
def test_pushed_manifest_binds_registry_bytes_to_scanned_local_image(media_type):
    raw = json.dumps({"schemaVersion": 2, "mediaType": media_type,
                      "config": {"digest": DIGEST}}).encode()
    registry_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert registry_digest != DIGEST
    verify_pushed_manifest(raw, registry_digest, DIGEST)
    with pytest.raises(ValueError, match="bytes do not match"):
        verify_pushed_manifest(raw + b"\n", registry_digest, DIGEST)
    with pytest.raises(ValueError, match="does not identify"):
        verify_pushed_manifest(raw, registry_digest, "sha256:" + "b" * 64)


@pytest.mark.parametrize("manifest", [None, [], {}, {"schemaVersion": 2, "config": {"digest": DIGEST}},
    {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "config": {"digest": DIGEST}},
    {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json", "config": "invalid"}])
def test_invalid_or_index_manifests_cannot_establish_scanned_image_identity(manifest):
    raw = json.dumps(manifest).encode()
    with pytest.raises(ValueError, match="does not identify"):
        verify_pushed_manifest(raw, "sha256:" + hashlib.sha256(raw).hexdigest(), DIGEST)


@pytest.mark.parametrize("mode", ["preflight", "complete", "missing-proof", "wrong-image"])
def test_release_cli_requires_registry_identity_proof_before_artifact_creation(tmp_path, monkeypatch, mode):
    root = tmp_path / "repo"
    output = tmp_path / "dist"
    minimal_release_tree(root, "v1.2.3")
    monkeypatch.setattr(package, "__file__", str(root / "scripts/release_package.py"))
    monkeypatch.setattr(package, "verify_tag_checkout", lambda _root, tag: None)
    monkeypatch.setattr(package, "tracked_docs", lambda _root: [])
    args = ["release_package.py", "--tag", "v1.2.3"]
    if mode == "preflight":
        args += ["--check-only"]
    else:
        raw = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                          "config": {"digest": DIGEST}}).encode()
        manifest = tmp_path / "manifest.json"
        manifest.write_bytes(raw)
        args += ["--output-dir", str(output), "--image-digest", "sha256:" + hashlib.sha256(raw).hexdigest()]
        if mode != "missing-proof":
            args += ["--image-manifest", str(manifest), "--checked-image-id",
                     DIGEST if mode == "complete" else "sha256:" + "b" * 64]
    monkeypatch.setattr(sys, "argv", args)
    if mode in ("missing-proof", "wrong-image"):
        with pytest.raises(SystemExit) as error:
            package.main()
        assert error.value.code == 2
    else:
        package.main()
    assert output.exists() is (mode == "complete")

import hashlib
import subprocess
import tarfile

import pytest

from scripts.release_package import create_bundle, render_compose, require_stable_tag


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
        ["docs/README.md", "docs/releases/v1.2.3.md", "docs/operations/guide.md"],
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getnames()
        content = {name.split("/", 1)[1]: archive.extractfile(name).read() for name in members}

    prefix = "ghostfolio-boursedirect-sync-v1.2.3/"
    assert prefix + "collector/browser-seccomp.json" in members
    assert prefix + "docs/releases/v1.2.3.md" in members
    assert prefix + "config/mappings.yaml" not in members
    assert prefix + ".env" not in members
    assert prefix + "tmp/receipt.json" not in members
    assert prefix + "scripts/import.py" not in members
    assert prefix + "docs/archive/secret.md" not in members
    assert b"v1.2.3" in content["compose.yaml"]
    assert b"v0.1.0" not in content["compose.yaml"]
    assert b"[Bundle docs](docs/)" in content["README.md"]
    assert b"tree/v1.2.3/scripts)" in content["README.md"]
    assert b"blob/v1.2.3/scripts/import.py" in content["docs/operations/guide.md"]
    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert sums_path.read_text(encoding="utf-8") == archive_hash + "  " + archive_path.name + "\n"
    duplicate_archive, duplicate_sums = create_bundle(
        root,
        "v1.2.3",
        tmp_path / "repeat",
        ["docs/README.md", "docs/releases/v1.2.3.md", "docs/operations/guide.md"],
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
        render_compose(b"services: {}\n", "v1.2.3")
    with pytest.raises(ValueError, match="exactly one"):
        render_compose(
            b"image: ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0\n"
            b"image: ghcr.io/flowcool/ghostfolio-boursedirect-sync:v0.1.0\n",
            "v1.2.3",
        )


def test_release_bundle_requires_a_regular_release_note(tmp_path):
    root = tmp_path / "repo"
    minimal_release_tree(root, "v1.2.3")
    (root / "docs/releases/v1.2.3.md").unlink()
    with pytest.raises(ValueError, match="release notes are missing"):
        create_bundle(root, "v1.2.3", tmp_path / "dist", [])

    minimal_release_tree(root, "v1.2.3")
    outside = tmp_path / "outside.md"
    outside.write_text("not part of this checkout\n", encoding="utf-8")
    (root / "docs/releases/v1.2.3.md").unlink()
    (root / "docs/releases/v1.2.3.md").symlink_to(outside)
    with pytest.raises(ValueError, match="release notes are missing"):
        create_bundle(root, "v1.2.3", tmp_path / "other-dist", [])

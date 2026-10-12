#!/usr/bin/env python3
"""Create the public, deterministic operator bundle for a stable release."""

import argparse
import gzip
import hashlib
import io
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tarfile


IMAGE_PREFIX = "ghcr.io/flowcool/ghostfolio-boursedirect-sync:"
SAFE_ROOT_FILES = (
    ".env.example",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "compose.yaml",
    "compose.ghostfolio.yaml",
)
SAFE_EXTRA_FILES = (
    ".github/BUILD.md",
    "config/README.md",
    "collector/browser-seccomp.json",
    "collector/licenses/playwright-LICENSE",
)
SAFE_DOC_SUFFIXES = {".md", ".json", ".svg", ".yaml", ".yml"}
RELEASE_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
INLINE_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)]+)\)")
IMAGE_REFERENCE = re.compile(
    r"ghcr\.io/flowcool/ghostfolio-boursedirect-sync:v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)


def require_stable_tag(tag):
    if not RELEASE_TAG.fullmatch(tag):
        raise ValueError("release tag must be a stable vX.Y.Z version")


def verify_tag_checkout(root, tag):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tagged = subprocess.check_output(
        ["git", "rev-parse", "refs/tags/" + tag + "^{commit}"], cwd=root, text=True
    ).strip()
    if head != tagged:
        raise ValueError("checked-out commit does not match release tag")
    return head


def public_paths(root, tracked_paths):
    paths = list(SAFE_ROOT_FILES) + list(SAFE_EXTRA_FILES)
    for name in tracked_paths:
        path = PurePosixPath(name)
        if path.parts and path.parts[0] == "docs" and path.suffix.lower() in SAFE_DOC_SUFFIXES:
            paths.append(path.as_posix())
    selected = sorted(set(paths))
    for name in selected:
        if name.startswith((".env/", "config/mappings", "input/", "inputs/", "tmp/", "state/")):
            raise ValueError("private path rejected from release bundle: " + name)
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("required public release file is missing or unsafe: " + name)
    return selected


def tracked_docs(root):
    result = subprocess.check_output(["git", "ls-files", "-z", "--", "docs"], cwd=root)
    return [item.decode("utf-8") for item in result.split(b"\0") if item]


def render_compose(data, tag):
    text = data.decode("utf-8")
    replacement = IMAGE_PREFIX + tag
    rendered, count = IMAGE_REFERENCE.subn(replacement, text)
    if count != 1:
        raise ValueError("compose.yaml must contain exactly one canonical release image")
    return rendered.encode("utf-8")


def rewrite_markdown_links(name, data, included, root, tag):
    text = data.decode("utf-8")
    source_prefix = "https://github.com/flowcool/ghostfolio-boursedirect-sync/"

    def replace(match):
        target = match.group(2).strip()
        if not target or target.startswith(("#", "http://", "https://", "mailto:", "data:")):
            return match.group(0)
        path_part, marker, fragment = target.partition("#")
        path_part, query_marker, query = path_part.partition("?")
        if not path_part:
            return match.group(0)
        target_path = posixpath.normpath(
            path_part.lstrip("/") if path_part.startswith("/") else posixpath.join(posixpath.dirname(name), path_part)
        )
        if target_path == ".." or target_path.startswith("../") or target_path.startswith("/"):
            raise ValueError("local Markdown link escapes repository in " + name + ": " + target)
        local_target = root / target_path
        if not local_target.exists() or local_target.is_symlink():
            raise ValueError("broken local Markdown link in " + name + ": " + target)
        if target_path in included or (local_target.is_dir() and any(item.startswith(target_path.rstrip("/") + "/") for item in included)):
            return match.group(0)
        url = source_prefix + ("tree/" if local_target.is_dir() else "blob/") + tag + "/" + target_path
        if query_marker:
            url += "?" + query
        if marker:
            url += "#" + fragment
        return "[" + match.group(1) + "](" + url + ")"

    return INLINE_LINK.sub(replace, text).encode("utf-8")


def create_bundle(root, tag, output_dir, tracked_paths):
    require_stable_tag(tag)
    release_note = "docs/releases/" + tag + ".md"
    paths = public_paths(root, tracked_paths)
    if release_note not in paths:
        paths.append(release_note)
        paths.sort()
    if release_note not in paths or not (root / release_note).is_file() or (root / release_note).is_symlink():
        raise ValueError("required release notes are missing: " + release_note)

    included = set(paths)
    bundle_name = "ghostfolio-boursedirect-sync-" + tag
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / (bundle_name + ".tar.gz")
    sums_path = output_dir / "SHA256SUMS"
    if archive_path.exists() or sums_path.exists():
        raise ValueError("release output already exists; refusing to overwrite artifacts")
    entries = {}
    for name in paths:
        source = root / name
        data = source.read_bytes()
        if name == "compose.yaml":
            data = render_compose(data, tag)
        if name.lower().endswith(".md"):
            data = rewrite_markdown_links(name, data, included, root, tag)
        entries[name] = data

    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w|", format=tarfile.USTAR_FORMAT) as archive:
                for name in paths:
                    data = entries[name]
                    info = tarfile.TarInfo(bundle_name + "/" + name)
                    info.size = len(data)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(data))

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    sums_path.write_text(digest + "  " + archive_path.name + "\n", encoding="utf-8")
    return archive_path, sums_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        require_stable_tag(args.tag)
        root = Path(__file__).resolve().parent.parent
        verify_tag_checkout(root, args.tag)
        archive, sums = create_bundle(root, args.tag, args.output_dir, tracked_docs(root))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))
    print(archive)
    print(sums)


if __name__ == "__main__":
    main()

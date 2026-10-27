"""Prepare one native candidate per architecture; never write a stable image tag.

Adapted from IBKR 9716103 release_image.py and release-image.yml:79-158.
BD builds once before lab qualification. Candidate publication is by digest.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from release_image import STABLE_TAG, registry_version_absent, release_identity
from verify_release_image import native_manifest_digest


def output(*args):
    return subprocess.check_output(args, timeout=90)


def prepare(tag):
    repository = os.environ["GITHUB_REPOSITORY"].lower()
    if (os.environ["GITHUB_EVENT_NAME"] != "workflow_dispatch"
            or os.environ["GITHUB_REF"] != "refs/heads/main"
            or not re.fullmatch(r"[a-z0-9_.-]+/[a-z0-9_.-]+", repository)
            or not STABLE_TAG.fullmatch(tag)):
        raise RuntimeError("Prepare a stable release candidate from main only")
    commit = output("git", "rev-parse", "HEAD").decode().strip()
    version, revision = release_identity(tag, commit)
    candidate = "candidate-" + version + "-" + revision
    registry_version_absent(repository, candidate, os.environ["GITHUB_ACTOR"], os.environ["GH_TOKEN"])
    registry_version_absent(repository, version, os.environ["GITHUB_ACTOR"], os.environ["GH_TOKEN"])
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(f"tag={tag}\nversion={version}\nrevision={revision}\ncandidate={candidate}\n")


def receipt(tag):
    """Record exact checked native manifests, as in IBKR's qualification record."""
    repository = os.environ["GITHUB_REPOSITORY"].lower()
    commit = output("git", "rev-parse", "HEAD").decode().strip()
    release_identity(tag, commit)
    raw = Path("release-manifest.json").read_bytes()
    index = json.loads(raw)
    record = {"schema": 1, "repository": repository, "tag": tag,
              "commit": commit, "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
              "native": {arch: native_manifest_digest(index, arch) for arch in ("amd64", "arm64")}}
    Path("candidate-image.json").write_text(json.dumps(record, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--receipt", action="store_true")
    args = parser.parse_args()
    if args.receipt:
        receipt(args.tag)
    else:
        prepare(args.tag)


if __name__ == "__main__":
    main()

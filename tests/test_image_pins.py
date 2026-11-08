"""Offline check: the public READMEs use the moving :latest tag (Florent 2026-11-08).

Release bundles pin the exact digest at packaging time (scripts/release_package.py).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
IMAGE = "ghcr.io/flowcool/ghostfolio-boursedirect-sync"
# The tag is optional so a bare reference (implicit tag) is caught and rejected.
PIN = re.compile(re.escape(IMAGE) + r"(?![\w./-])(?::([^\s}`'\"]+))?")
STABLE = re.compile(r"v?(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)@sha256:[0-9a-f]{64}\Z")


def single_stable_pin(texts):
    found = {pin for text in texts for pin in PIN.findall(text)}
    assert len(found) == 1, f"expected one image pin, found {sorted(found)}"
    pin = found.pop()
    assert STABLE.fullmatch(pin), f"pin is not a stable vX.Y.Z@sha256 reference: {pin}"
    return pin


def test_readmes_use_latest_only():
    for name in ("README.md", "README.fr.md"):
        found = set(PIN.findall((ROOT / name).read_text(encoding="utf-8")))
        assert found == {"latest"}, f"{name}: expected only :latest, found {sorted(found)}"


def test_mismatched_pin_fails():
    digest = "@sha256:" + "a" * 64
    with pytest.raises(AssertionError, match="expected one image pin"):
        single_stable_pin([f"image: {IMAGE}:v0.2.0{digest}\n", f"image: {IMAGE}:v0.1.1{digest}\n"])


def test_prerelease_pin_fails():
    with pytest.raises(AssertionError, match="not a stable"):
        single_stable_pin([f"image: {IMAGE}:v0.2.0-rc.1@sha256:" + "a" * 64])


def test_bare_reference_fails():
    with pytest.raises(AssertionError):
        single_stable_pin([f"image: {IMAGE}\n"])


def test_sub_path_image_is_ignored():
    digest = "@sha256:" + "a" * 64
    assert single_stable_pin([f"image: {IMAGE}:v0.2.0{digest}\n", f"image: {IMAGE}/sidecar:v1\n"]) == "v0.2.0" + digest

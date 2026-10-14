"""Offline check: README image pins name one stable release, so Renovate bumps them together."""

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).parents[1]
IMAGE = "ghcr.io/flowcool/ghostfolio-boursedirect-sync"
# The tag is optional so a bare reference (implicit tag) is caught and rejected.
PIN = re.compile(re.escape(IMAGE) + r"(?![\w.-])(?::([^\s}`'\"]+))?")
STABLE = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)@sha256:[0-9a-f]{64}\Z")


def single_stable_pin(texts):
    found = {pin for text in texts for pin in PIN.findall(text)}
    assert len(found) == 1, f"expected one image pin, found {sorted(found)}"
    pin = found.pop()
    assert STABLE.fullmatch(pin), f"pin is not a stable vX.Y.Z@sha256 reference: {pin}"
    return pin


def test_readme_pins_one_stable_release():
    single_stable_pin([(ROOT / "README.md").read_text(encoding="utf-8")])


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

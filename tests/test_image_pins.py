"""Offline check: the public READMEs use the moving :latest tag (Florent 2026-11-08).

Release bundles pin the exact digest at packaging time (scripts/release_package.py).
"""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
IMAGE = "ghcr.io/flowcool/ghostfolio-boursedirect-sync"
# The tag is optional so a bare reference (implicit tag) is caught and rejected.
PIN = re.compile(re.escape(IMAGE) + r"(?![\w./-])(?::([^\s}`'\"]+))?")


def test_readmes_use_latest_only():
    for name in ("README.md", "README.fr.md"):
        found = set(PIN.findall((ROOT / name).read_text(encoding="utf-8")))
        assert found == {"latest"}, f"{name}: expected only :latest, found {sorted(found)}"

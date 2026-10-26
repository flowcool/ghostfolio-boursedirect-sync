#!/usr/bin/env bash
# Every required check stands alone: a failed check stops the sequence.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
.venv/bin/python scripts/check-docs.py
.venv/bin/python -m pytest -q
git diff --check
git diff --cached --check

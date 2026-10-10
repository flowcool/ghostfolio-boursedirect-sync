"""Development checks use synthetic documents and isolated command stubs."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts/check-docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def catalogue(tmp_path):
    design = tmp_path / "docs/design"
    design.mkdir(parents=True)
    (design / "contract.md").write_text("# Contract\n\nA synthetic contract.\n")
    (design / "index.md").write_text("| [Contract](contract.md) | A synthetic contract. |\n")
    (tmp_path / "AGENTS.md").write_text("[Index](docs/design/index.md)\n")
    (tmp_path / "CLAUDE.md").write_text("Read the owning contract.\n")
    return design


def test_valid_catalogue(tmp_path):
    catalogue(tmp_path)
    assert docs.check_docs(tmp_path) == []


@pytest.mark.parametrize("change", ["missing", "duplicate", "stale", "broken", "malformed"])
def test_invalid_catalogue(tmp_path, change):
    design = catalogue(tmp_path)
    index = design / "index.md"
    if change == "missing":
        index.write_text("")
    elif change == "duplicate":
        index.write_text(index.read_text() * 2)
    elif change == "stale":
        (design / "contract.md").write_text("# Renamed\n\nChanged purpose.\n")
    elif change == "broken":
        (tmp_path / "CLAUDE.md").write_text("[Missing](missing.md)\n")
    else:
        index.write_text("| [Contract](contract.md) |\n")
    assert docs.check_docs(tmp_path)


@pytest.mark.parametrize("failed_stage", ["docs", "pytest", "npm", "git", "staged", ""])
def test_verification_stops_at_failed_stage(tmp_path, failed_stage):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts/verify-local.sh", scripts / "verify-local.sh")
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/bash\nif [[ $1 == scripts/check-docs.py ]]; then stage=docs; else stage=pytest; fi\nprintf '%s\\n' \"$stage\" >> \"$CHECK_LOG\"\nif [[ $stage == $FAILED_STAGE ]]; then exit 17; fi\n")
    python.chmod(0o755)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for stage in ["npm", "git"]:
        stub = binaries / stage
        stub.write_text("#!/bin/bash\nstage=" + stage + "\nif [[ $stage == git && $2 == --cached ]]; then stage=staged; fi\nprintf '%s\\n' \"$stage\" >> \"$CHECK_LOG\"\nif [[ $FAILED_STAGE == $stage ]]; then exit 17; fi\n")
        stub.chmod(0o755)
    log = tmp_path / "checks.log"
    env = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"],
               CHECK_LOG=str(log), FAILED_STAGE=failed_stage)
    result = subprocess.run(["/bin/bash", str(scripts / "verify-local.sh")], env=env, capture_output=True)
    assert result.returncode == (17 if failed_stage else 0)
    stages = ["docs", "pytest", "npm", "git", "staged"]
    expected = stages[:stages.index(failed_stage) + 1] if failed_stage else stages
    assert log.read_text().splitlines() == expected

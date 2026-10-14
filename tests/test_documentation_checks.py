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


def entry_documents(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/guide.md").write_text("# Guide\n")
    (tmp_path / "AGENTS.md").write_text("[Guide](docs/guide.md) [Site](https://example.com)\n")
    (tmp_path / "CLAUDE.md").write_text("Read [AGENTS.md](AGENTS.md).\n")


def test_valid_links(tmp_path):
    entry_documents(tmp_path)
    assert docs.check_docs(tmp_path) == []


@pytest.mark.parametrize("name", ["AGENTS.md", "README.md", "docs/README.md"])
def test_broken_link(tmp_path, name):
    entry_documents(tmp_path)
    (tmp_path / name).write_text("[Missing](missing.md)\n")
    assert docs.check_docs(tmp_path) == ["broken local link in " + name + ": missing.md"]


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

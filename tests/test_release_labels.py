"""Offline tests for PR release-note labeling."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("release_labels", Path(__file__).parents[1] / "scripts/label_pr_release.py")
labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(labels)


def test_title_types_map_to_labels():
    assert labels.labels_for_title("fix: stop duplicate dividends") == {"fix"}
    assert labels.labels_for_title("feat(cleanup): resume journals") == {"feature"}
    assert labels.labels_for_title("docs: refresh README") == {"documentation"}
    assert labels.labels_for_title("chore(deps): bump requests") == {"maintenance"}


def test_bang_marks_breaking_change():
    assert labels.labels_for_title("feat!: drop JSON resume") == {"feature", "breaking-change"}
    assert labels.labels_for_title("refactor(api)!: rename flag") == {"maintenance", "breaking-change"}


def test_type_is_case_insensitive():
    assert labels.labels_for_title("Feat!: drop JSON resume") == {"feature", "breaking-change"}
    assert labels.labels_for_title("FIX: x") == {"fix"}


def test_non_conventional_title_gets_nothing():
    assert labels.labels_for_title("Update stuff") == set()
    assert labels.labels_for_title("") == set()
    assert labels.labels_for_title(None) == set()


def test_impact_section_requires_real_text():
    template = "## Behavior\nx\n\n## Release impact\n\n<!-- bump, migration, rollback; write None if no impact -->\n\n## Verification\ny"
    assert not labels.impact_section_filled(template)
    assert not labels.impact_section_filled("no section here")
    assert not labels.impact_section_filled(None)
    filled = "## Release impact\nMinor bump. Migration: re-run dry-run. Rollback: previous digest.\n## Verification\n"
    assert labels.impact_section_filled(filled)


@pytest.mark.parametrize("title", [
    'fix: $(touch injected) `touch injected` ; echo bad >> "$GITHUB_ENV"',
    'feat!: unsafe\n::set-output name=bad::value\nBAD=value\nEOF',
    'chore: $(echo bad >> "$GITHUB_OUTPUT")',
    '$(touch injected): arbitrary',
])
def test_hostile_pr_title_stays_data_and_never_reaches_shell_or_github_files(tmp_path, monkeypatch, capsys, title):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 58, "title": title,
        "labels": [], "body": ""}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "synthetic/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "SYNTHETIC_TOKEN")
    destinations = [tmp_path / "env", tmp_path / "output"]
    for variable, path in zip(("GITHUB_ENV", "GITHUB_OUTPUT"), destinations):
        path.write_bytes(b"unchanged\n")
        monkeypatch.setenv(variable, str(path))

    def forbidden(*_args, **_kwargs):
        pytest.fail("PR title reached process/shell execution")

    for module, names in ((subprocess, ("run", "Popen", "call", "check_call", "check_output")),
                          (os, ("system", "popen"))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    calls = []
    monkeypatch.setattr(labels, "api", lambda token, method, path, payload: calls.append((token, method, path, payload)))
    assert labels.main() == 0
    for token, method, path, payload in calls:
        assert token == "SYNTHETIC_TOKEN" and method == "POST"
        if path == "repos/synthetic/repo/labels":
            assert set(payload) == {"name", "color"}
            assert payload["name"] in labels.LABEL_COLORS
            assert payload["color"] == labels.LABEL_COLORS[payload["name"]]
        else:
            assert path == "repos/synthetic/repo/issues/58/labels"
            assert set(payload) == {"labels"}
            assert all(name in labels.LABEL_COLORS for name in payload["labels"])
        assert title not in json.dumps(payload)
    assert all(path.read_bytes() == b"unchanged\n" for path in destinations)
    assert title not in capsys.readouterr().out
    assert not (tmp_path / "injected").exists()


def test_write_token_label_workflow_never_interpolates_title_or_checks_out_head():
    import yaml
    workflow = Path(__file__).parents[1] / ".github/workflows/pr-release-labels.yml"
    raw = workflow.read_text()
    assert "${{ github.event.pull_request.title" not in raw
    document = yaml.safe_load(raw)
    triggers = document.get("on", document.get(True))
    assert set(triggers) == {"pull_request_target"}
    steps = document["jobs"]["label"]["steps"]
    checkout = next(step for step in steps if step.get("uses", "").startswith("actions/checkout@"))
    assert "ref" not in checkout.get("with", {})
    assert [step["run"] for step in steps if "run" in step] == ["python3 scripts/label_pr_release.py"]

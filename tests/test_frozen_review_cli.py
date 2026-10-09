import hashlib
import json
import os
from pathlib import Path
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_review_cli import setup, run, output


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("No network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def fixture(**kwargs):
    setup(**kwargs)
    run()
    Path("inputs/report.yaml").write_bytes(output().read_bytes())
    return hashlib.sha256(output().read_bytes()).hexdigest()


def invoke(pin, **kwargs):
    args = {"config": "inputs/review.yaml", "review": "inputs/report.yaml",
            "review-sha256": pin, "input-root": "inputs", "max-bytes": "100000"}
    args.update(kwargs)
    return bd.main(["check-review", *[item for k, v in args.items() for item in ("--" + k, v)]])


def retained():
    return {str(p): (p.read_bytes(), p.stat().st_mode & 0o777)
            for p in Path(".").rglob("*") if p.is_file() and not p.is_symlink()}


@pytest.mark.parametrize("case", [{}, {"existing": True}, {"missing": True}])
def test_operator_check_reads_once_and_never_publishes(monkeypatch, capsys, case):
    pin = fixture(**case)
    before = retained()
    reader = bd.read_local_bytes
    calls = []
    def capture(path, root, limit):
        calls.append(str(path))
        return reader(path, root, limit)
    monkeypatch.setattr(bd, "read_local_bytes", capture)
    def forbidden(*args, **kwargs):
        raise AssertionError("Check must not write, lock, publish, or read credentials")
    for name in ("atomic_private_yaml", "atomic_private_bytes", "private_directory", "persist_write_transition", "review_local_snapshot"):
        monkeypatch.setattr(bd, name, forbidden)
    for name in ("mkdir", "chmod", "write_bytes", "write_text"):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setattr(bd.fcntl, "flock", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    assert invoke(pin) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary["review_verified"] is True and summary["import_ready"] is False
    assert summary["new_activities"] == (0 if case.get("existing") else 3)
    assert summary["adopted_activities"] == (3 if case.get("existing") else 0)
    assert bool(summary["holdings_shortfalls"]) == bool(case.get("missing"))
    assert set(summary) == {"review_verified", "import_ready", "new_activities", "owned_activities", "adopted_activities", "holdings_shortfalls", "blockers"}
    assert len(calls) == len(set(calls)) == 6
    assert retained() == before


@pytest.mark.parametrize("bad", ["pin", "report", "input"])
def test_failed_operator_check_preserves_everything_and_logs_only_codes(capsys, caplog, bad):
    pin = fixture()
    if bad == "pin": pin = "0" * 64
    elif bad == "report":
        path = Path("inputs/report.yaml")
        path.write_bytes(path.read_bytes() + b"extra: secret-looking-private-field\n")
        pin = hashlib.sha256(path.read_bytes()).hexdigest()
    else: Path("inputs/resolutions.yaml").write_bytes(b"{}\n ")
    before = retained()
    assert invoke(pin) == 1
    assert capsys.readouterr().out == ""
    assert "FROZEN_REVIEW_" in caplog.text
    assert "secret-looking" not in caplog.text and "synthetic-ghostfolio-account" not in caplog.text
    assert retained() == before


@pytest.mark.parametrize("kind", ["missing", "outside", "symlink", "directory", "oversized"])
@pytest.mark.parametrize("role", ["review", "config", "snapshot"])
def test_each_local_capture_obeys_reader_boundary(tmp_path, capsys, caplog, kind, role):
    pin = fixture()
    path = output() if role == "review" else Path("inputs/review.yaml" if role == "config" else "inputs/snapshot.json")
    kwargs = {"input-root": "inputs"}
    # Put the report within the selected root for ordinary-path isolation.
    Path("inputs/report.yaml").write_bytes(output().read_bytes())
    kwargs["review"] = "inputs/report.yaml"
    if role == "review": path = Path("inputs/report.yaml")
    if kind == "missing": path.unlink()
    elif kind == "symlink":
        copy = Path("inputs/copy.bytes")
        copy.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(copy.resolve())
    elif kind == "directory":
        path.unlink()
        path.mkdir()
    elif kind == "oversized": path.write_bytes(b"x" * 100001)
    else:
        external = tmp_path / "outside-private.bytes"
        external.write_bytes(path.read_bytes())
        if role == "snapshot":
            config = bd.parse_keyed_yaml(Path("inputs/review.yaml").read_bytes())
            config["snapshot"] = str(external)
            Path("inputs/review.yaml").write_text(bd.yaml.safe_dump(config))
        else: kwargs[role] = str(external)
    before = retained()
    assert invoke(pin, **kwargs) == 1
    assert capsys.readouterr().out == ""
    assert str(tmp_path) not in caplog.text
    assert retained() == before


@pytest.mark.parametrize("budget", [True, 0, -1, 1.0, None])
def test_bad_budget_fails_before_read(monkeypatch, budget):
    def forbidden(*args, **kwargs): raise AssertionError("Must reject before capture")
    monkeypatch.setattr(bd, "read_local_bytes", forbidden)
    with pytest.raises(RuntimeError, match="^INVALID_FROZEN_REVIEW_BYTE_LIMIT$"):
        bd.check_local_frozen_review("config", "report", "0" * 64, ".", budget)


def test_existing_report_under_outputs_with_common_root_is_never_replaced(capsys):
    fixture()
    config_path = Path("inputs/review.yaml")
    config = bd.parse_keyed_yaml(config_path.read_bytes())
    for key in ("prepared", "snapshot", "resolutions", "history_evidence"):
        config[key] = "inputs/" + config[key]
    config_path.write_text(bd.yaml.safe_dump(config))
    bd.review_local_snapshot(config_path, ".", 100000)
    pin = hashlib.sha256(output().read_bytes()).hexdigest()
    before = retained()
    assert invoke(pin, **{"input-root": ".", "review": str(output())}) == 2
    assert json.loads(capsys.readouterr().out)["review_verified"]
    assert retained() == before

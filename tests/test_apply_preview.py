import hashlib
import json
import os
from pathlib import Path
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_frozen_review_cli import fixture, retained


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DRY_RUN", raising=False)
    def forbidden(*args, **kwargs): raise AssertionError("Offline apply forbids network/intents")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(bd, "dispatch_single_lab_intent", forbidden)
    monkeypatch.setattr(bd, "persist_write_transition", forbidden)
    monkeypatch.setattr(bd.http.client, "HTTPSConnection", forbidden)


def invoke(pin, export=None, execute=False):
    args = ["apply", "--config", "inputs/review.yaml", "--review", "inputs/report.yaml",
            "--review-sha256", pin, "--input-root", "inputs", "--max-bytes", "100000"]
    if export is not None: args += ["--export", str(export)]
    if execute: args += ["--execute"]
    return bd.main(args)


@pytest.mark.parametrize("dry_run", [None, "0", "1", "true", "", " 1"])
@pytest.mark.parametrize("execute", [False, True])
def test_dry_run_truth_table_credential_and_publication_free(monkeypatch, capsys, dry_run, execute):
    pin = fixture()
    if dry_run is not None: monkeypatch.setenv("DRY_RUN", dry_run)
    getter = type(os.environ).get
    def get(environment, name, *args):
        if name.startswith("GHOST") or name.startswith("BD_"):
            raise AssertionError("Preview must not read destination/broker credentials")
        return getter(environment, name, *args)
    monkeypatch.setattr(type(os.environ), "get", get)
    before = retained()
    if dry_run not in (None, "0", "1") or dry_run == "0" and execute:
        assert invoke(pin, execute=execute) == 1
        assert capsys.readouterr().out == ""
    else:
        assert invoke(pin, execute=execute) == 2
        summary = json.loads(capsys.readouterr().out)
        assert summary["dry_run"] is True and summary["import_ready"] is False
        assert summary["new_activities"] == 3 and summary["proposal_exported"] is False
        assert "accepted" not in summary and "target_account_id" not in summary
    assert retained() == before
    assert not list(Path("state").glob("writes-*"))


def test_execute_gate_and_invalid_switch_fail_before_reads(monkeypatch):
    def forbidden(*args): raise AssertionError("Must refuse before input access")
    monkeypatch.setattr(bd, "capture_local_frozen_review", forbidden)
    monkeypatch.setenv("DRY_RUN", "0")
    with pytest.raises(RuntimeError, match="^APPLICATION_EXECUTION_GATE_REQUIRED$"):
        bd.preview_local_application("missing", "missing", "0" * 64, ".", 100000, execute=True)
    monkeypatch.setenv("DRY_RUN", "invalid")
    with pytest.raises(RuntimeError, match="^INVALID_DRY_RUN$"):
        bd.preview_local_application("missing", "missing", "0" * 64, ".", 100000)


@pytest.mark.parametrize("case", [{"existing": True}, {"missing": True}])
def test_diagnostic_preview_valid_but_export_refused(case, capsys):
    pin = fixture(**case)
    assert invoke(pin) == 2
    result = json.loads(capsys.readouterr().out)
    assert bool(result["holdings_shortfalls"]) == bool(case.get("missing"))
    before = retained()
    assert invoke(pin, "outputs/proposal.json") == 1
    assert capsys.readouterr().out == ""
    assert retained() == before


@pytest.mark.parametrize("nested", [False, True])
def test_exact_private_proposal_without_financial_or_state_mutation(capsys, nested):
    pin = fixture()
    expected = bd.parse_keyed_yaml(Path("inputs/report.yaml").read_bytes())["wire"]["body_utf8"].encode()
    directory = Path("outputs/nested") if nested else Path("outputs")
    if nested: directory.mkdir(mode=0o755)
    directory.chmod(0o755)
    export = directory / "proposal.json"
    export.write_bytes(b"old proposal")
    before = retained()
    assert invoke(pin, export) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["proposal_exported"] is True and result["dry_run"] is True
    assert result["import_ready"] is False
    assert export.read_bytes() == expected and export.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    for path, original in before.items():
        if Path(path) != export:
            assert (Path(path).read_bytes(), Path(path).stat().st_mode & 0o777) == original
    assert not list(Path("state").glob("writes-*"))


@pytest.mark.parametrize("mode", ["outside", "symlink", "ancestor-symlink", "directory", "fifo", "missing-parent", "input-hardlink", "root-symlink"])
def test_destination_refusal_before_chmod_or_publication(mode, capsys):
    pin = fixture()
    Path("outputs").chmod(0o755)
    path = Path("outputs/proposal.json")
    if mode == "outside": path = Path("inputs/proposal.json")
    elif mode == "symlink": path.symlink_to(Path("inputs/snapshot.json").resolve())
    elif mode == "ancestor-symlink":
        Path("outputs/alias").symlink_to(Path("inputs").resolve(), target_is_directory=True)
        path = Path("outputs/alias/proposal.json")
    elif mode == "directory": path.mkdir()
    elif mode == "fifo": os.mkfifo(path)
    elif mode == "missing-parent": path = Path("outputs/missing/proposal.json")
    elif mode == "input-hardlink": path.hardlink_to(Path("inputs/snapshot.json"))
    elif mode == "root-symlink":
        Path("outputs").rename("old-outputs")
        Path("outputs").symlink_to(Path("old-outputs").resolve(), target_is_directory=True)
    files = [p for folder in ("inputs", "state") for p in Path(folder).rglob("*") if p.is_file()]
    before = {p: (p.read_bytes(), p.stat().st_mode) for p in files}
    original_mode = Path("outputs").stat().st_mode
    assert invoke(pin, path) == 1
    assert capsys.readouterr().out == ""
    assert before == {p: (p.read_bytes(), p.stat().st_mode) for p in files}
    assert Path("outputs").stat().st_mode == original_mode


@pytest.mark.parametrize("role", ["config", "review", "prepared", "snapshot", "resolutions", "history_evidence"])
def test_every_captured_input_path_alias_preserved(role):
    config = __import__("test_review_cli").setup()
    # Use a common root; a target file may legally be one of the captured inputs.
    config = {k: v if k == "schema_version" else "inputs/" + v for k, v in config.items()}
    target = Path("outputs/proposal.json")
    config_path = Path("inputs/review.yaml")
    if role == "config": config_path = target
    elif role not in ("review",):
        target.write_bytes(Path(config[role]).read_bytes())
        config[role] = str(target)
    config_path.write_text(bd.yaml.safe_dump(config))
    bd.review_local_snapshot(config_path, ".", 100000)
    original_report = __import__("test_review_cli").output()
    report = target if role == "review" else original_report
    if role == "review": target.write_bytes(original_report.read_bytes())
    pin = hashlib.sha256(report.read_bytes()).hexdigest()
    before = retained()
    with pytest.raises(RuntimeError, match="^OUTPUT_INPUT_COLLISION$"):
        bd.preview_local_application(config_path, report, pin, ".", 100000, export_path=target)
    assert retained() == before


def test_report_tamper_preserves_previous_export(capsys, caplog):
    pin = fixture()
    export = Path("outputs/proposal.json")
    export.write_bytes(b"old")
    Path("inputs/report.yaml").write_bytes(Path("inputs/report.yaml").read_bytes() + b"private: secret\n")
    before = retained()
    assert invoke(pin, export) == 1
    assert capsys.readouterr().out == ""
    assert "secret" not in caplog.text
    assert retained() == before


def test_apply_captures_exactly_once_and_can_create_only_outputs(monkeypatch, capsys):
    pin = fixture()
    Path("outputs").rename("retained-outputs")
    calls = []
    read = bd.read_local_bytes
    def capture(path, root, limit):
        calls.append(str(path))
        return read(path, root, limit)
    monkeypatch.setattr(bd, "read_local_bytes", capture)
    assert invoke(pin, "outputs/proposal.json") == 2
    assert json.loads(capsys.readouterr().out)["proposal_exported"]
    assert len(calls) == len(set(calls)) == 6
    assert Path("outputs").stat().st_mode & 0o777 == 0o700


def test_postrename_directory_sync_failure_never_reports_export_success(monkeypatch, capsys):
    import stat
    pin = fixture()
    sync = os.fsync
    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("Private directory failure")
        sync(descriptor)
    monkeypatch.setattr(os, "fsync", fail_directory)
    assert invoke(pin, "outputs/proposal.json") == 1
    assert capsys.readouterr().out == ""
    # Rename occurred; crash durability is unknown, never a successful export.
    assert Path("outputs/proposal.json").exists()
    assert not list(Path("state").glob("writes-*"))

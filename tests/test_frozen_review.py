import copy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_review_cli import setup, run, output


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("No network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def bundle(**kwargs):
    config = setup(**kwargs)
    run()
    captures = {k: (Path("inputs") / config[k]).read_bytes()
                for k in ("prepared", "snapshot", "resolutions", "history_evidence")}
    return output().read_bytes(), Path("inputs/review.yaml").read_bytes(), captures


def validate(raw, config, captures, limit=100000):
    return bd.validate_frozen_review(raw, hashlib.sha256(raw).hexdigest(), config, captures, limit)


@pytest.mark.parametrize("case", [{}, {"existing": True}, {"missing": True}])
def test_full_computation_and_validation_have_no_io_or_mutation(monkeypatch, case):
    raw, config, captures = bundle(**case)
    before = copy.deepcopy(captures)
    def forbidden(*args, **kwargs):
        raise AssertionError("Pure boundary must not access files or persistence")
    for name in ("read_local_bytes", "atomic_private_bytes", "atomic_private_yaml", "persist_write_transition"):
        monkeypatch.setattr(bd, name, forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "write_bytes", forbidden)
    expected = bd.parse_keyed_yaml(raw)
    assert bd.compute_offline_review(config, captures, 100000) == expected
    assert validate(raw, config, captures) == expected
    assert captures == before and expected["import_ready"] is False
    if case.get("existing"):
        assert expected["wire"] is None
    if case.get("missing"):
        assert expected["wire"] is not None and expected["holdings"]["shortages"]


@pytest.mark.parametrize("field", ["schema", "engine", "ready", "extra", "missing", "count_bool",
    "holdings_bool", "blocker", "binding", "source", "input", "body", "digest", "adoption", "order"])
def test_entire_report_compared_type_sensitively(field):
    raw, config, captures = bundle()
    report = bd.parse_keyed_yaml(raw)
    if field == "schema": report["schema_version"] = True
    elif field == "engine": report["engine_contract"] = "other"
    elif field == "ready": report["import_ready"] = 0
    elif field == "extra": report["extra"] = None
    elif field == "missing": del report["source_digests"]
    elif field == "count_bool": report["wire"]["activity_count"] = 3.0
    elif field == "holdings_bool": report["holdings"]["coverage_verified"] = 1
    elif field == "blocker": report["blockers"] = []
    elif field == "binding": report["target_account_id"] = "other"
    elif field == "source": report["source_digests"] = {}
    elif field == "input": report["input_sha256"]["config"] = "0" * 64
    elif field == "body": report["wire"]["body_utf8"] += " "
    elif field == "digest": report["wire"]["sha256"] = "0" * 64
    elif field == "adoption": report["adoption"]["new"] = []
    elif field == "order": report["blockers"].reverse()
    changed = yaml.safe_dump(report).encode()
    with pytest.raises(RuntimeError, match="^FROZEN_REVIEW_CONTENT_CONFLICT$"):
        validate(changed, config, captures)


def test_reordered_keys_normalize_but_external_pin_still_binds_bytes():
    raw, config, captures = bundle()
    reordered = yaml.safe_dump(bd.parse_keyed_yaml(raw), sort_keys=True).encode()
    assert reordered != raw
    assert validate(reordered, config, captures) == bd.parse_keyed_yaml(raw)
    with pytest.raises(RuntimeError, match="^FROZEN_REVIEW_DIGEST_CONFLICT$"):
        bd.validate_frozen_review(reordered, hashlib.sha256(raw).hexdigest(), config, captures, 100000)


@pytest.mark.parametrize("pin", ["0" * 64, "A" * 64, "", None, True])
def test_external_pin_required(pin):
    raw, config, captures = bundle()
    with pytest.raises(RuntimeError, match="^FROZEN_REVIEW_DIGEST_CONFLICT$"):
        bd.validate_frozen_review(raw, pin, config, captures, 100000)


@pytest.mark.parametrize("role", ["config", "prepared", "snapshot", "resolutions", "history_evidence"])
def test_exact_input_bytes_and_reference_strings_bound(role):
    raw, config, captures = bundle()
    if role == "config":
        changed = bd.parse_keyed_yaml(config)
        changed["prepared"] = "different-path.yaml"
        config = yaml.safe_dump(changed).encode()
    else:
        captures[role] += b"\n "
    with pytest.raises(RuntimeError, match="^(FROZEN_REVIEW_CONTENT_CONFLICT|COMPLETE_ACQUISITION_HISTORY_EVIDENCE_REQUIRED)$"):
        validate(raw, config, captures)


@pytest.mark.parametrize("limit", [True, 0, -1, 1.0, None])
def test_invalid_budget(limit):
    with pytest.raises(RuntimeError, match="^INVALID_FROZEN_REVIEW_BYTE_LIMIT$"):
        bd.compute_offline_review(b"", {}, limit)


@pytest.mark.parametrize("role", ["report", "config", "prepared", "snapshot", "resolutions", "history_evidence"])
def test_input_size_checked_before_parse(role):
    raw, config, captures = bundle()
    if role == "report": raw = b"x" * 100001
    elif role == "config": config = b"x" * 100001
    else: captures[role] = b"x" * 100001
    with pytest.raises(RuntimeError, match="^FROZEN_REVIEW_INPUT_LIMIT_EXCEEDED$"):
        validate(raw, config, captures)


@pytest.mark.parametrize("role", ["report", "config", "prepared", "resolutions", "history_evidence"])
@pytest.mark.parametrize("payload,code", [(b"x: &a [*a]", "YAML_ALIAS_NOT_SUPPORTED"),
    (b"x: 1\nx: 2", "YAML_DUPLICATE_KEY"), (b"x: " + b"[" * 34 + b"0" + b"]" * 34, "YAML_TOO_DEEP")])
def test_restricted_yaml_policy_applies_to_every_role(role, payload, code):
    raw, config, captures = bundle()
    if role == "report": raw = payload
    elif role == "config": config = payload
    else: captures[role] = payload
    with pytest.raises(RuntimeError, match="^" + code + "$"):
        validate(raw, config, captures)


def replace_snapshot(captures, data):
    captures["snapshot"] = json.dumps(data).encode()
    # Decimal scientific literals represent JSON numbers, not rejected numeric strings.
    import re
    captures["snapshot"] = re.sub(rb'"(1e[0-9]+)"', rb'\1', captures["snapshot"])
    history = bd.parse_keyed_yaml(captures["history_evidence"])
    history["snapshot_sha256"] = hashlib.sha256(captures["snapshot"]).hexdigest()
    captures["history_evidence"] = yaml.safe_dump(history).encode()


@pytest.mark.parametrize("value", [None, "1e5000", "1e9999999999999999999999999999999999"])
def test_snapshot_redaction_and_exponent_overflow_fail_safely(value):
    raw, config, captures = bundle()
    data = json.loads(captures["snapshot"])
    data["activities"][0]["quantity"] = value
    replace_snapshot(captures, data)
    with pytest.raises(RuntimeError, match="^(REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED|VERIFICATION_DECIMAL_LIMIT_EXCEEDED|INVALID_REMOTE_ACTIVITY_JSON)$"):
        validate(raw, config, captures)


@pytest.mark.parametrize("excess", [0, 1])
def test_aggregate_precision_exact_boundary_includes_inactive_rows(excess):
    raw, config, captures = bundle()
    data = json.loads(captures["snapshot"])
    prepared = bd.validated_prepared_review(captures["prepared"])["activities"]
    quantities = [Decimal(a["quantity"]) for a in prepared.values()]
    remote = bd.bounded_remote_snapshot(captures["snapshot"], 100000)
    quantities += [r["quantity"] for r in remote]
    cost = sum(len(q.as_tuple().digits) + abs(q.as_tuple().exponent) for q in quantities) + 8
    # Individually bounded, inactive rows still count toward potential holdings cost.
    remaining = bd.FROZEN_REVIEW_PRECISION_LIMIT - cost + excess
    while remaining:
        contribution = min(remaining, 3000)
        row = copy.deepcopy(data["activities"][0])
        row.update(id="budget-" + str(remaining), isDraft=True, quantity="1e" + str(contribution - 1))
        data["activities"].append(row)
        remaining -= contribution
    data["count"] = len(data["activities"])
    replace_snapshot(captures, data)
    if excess:
        with pytest.raises(RuntimeError, match="^FROZEN_REVIEW_PRECISION_LIMIT_EXCEEDED$"):
            bd.compute_offline_review(config, captures, 100000)
    else:
        assert bd.compute_offline_review(config, captures, 100000)["holdings"]["coverage_verified"]


def test_clock_eligibility_drift_invalidates_frozen_report(monkeypatch):
    raw, config, captures = bundle()
    data = json.loads(captures["snapshot"])
    extra = copy.deepcopy(data["activities"][0])
    extra.update(id="future-extra", date="2026-10-11T00:00:00.000Z")
    data["activities"].append(extra)
    data["count"] += 1
    replace_snapshot(captures, data)
    def clock(day):
        return type("Clock", (), {"now": staticmethod(lambda tz: datetime(2026, 10, day, tzinfo=timezone.utc)), "strptime": staticmethod(datetime.strptime), "fromisoformat": staticmethod(datetime.fromisoformat)})
    monkeypatch.setattr(bd, "datetime", clock(9))
    report = yaml.safe_dump(bd.compute_offline_review(config, captures, 100000)).encode()
    monkeypatch.setattr(bd, "datetime", clock(12))
    with pytest.raises(RuntimeError, match="^FROZEN_REVIEW_CONTENT_CONFLICT$"):
        validate(report, config, captures)

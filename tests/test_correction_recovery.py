"""Derived target states; real lab response qualification remains separate."""

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest
import requests
import yaml
from test_activity_review import sample
from test_pdf_buy import settings as settings

from ghostfolio_boursedirect_sync import activity_review as review


def transport(monkeypatch, row, on_put=None):
    rows = [deepcopy(row)]
    def get(*args, **kwargs):
        return Mock(status_code=200, content=json.dumps({"count": len(rows), "activities": rows},
                    default=lambda n: str(n) if not isinstance(n, Decimal) else float(n)).encode())
    def put(*args, **kwargs):
        payload = json.loads(kwargs["data"], parse_float=Decimal)
        if on_put:
            on_put(payload)
        target = next(row for row in rows if row["id"] == payload["id"])
        for key in ("date", "quantity", "unitPrice", "fee", "comment", "type", "currency"):
            target[key] = payload[key]
        return Mock(status_code=200)
    sender = Mock(side_effect=put)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", sender)
    monkeypatch.setattr(review, "RECOVERY_WAITS", (0,))
    return rows, sender


def test_ttf_off_without_timezone_journals_before_one_fee_only_put(settings, tmp_path, monkeypatch):
    row, event, events = sample()
    row.update(fee=1, comment="Manual note")
    event_id = event.comment
    events[event_id]["brokerage"] = "1"
    events[event_id]["values"]["fee"] = "1.30"
    events[event_id]["payload"]["fee"] = Decimal("1.30")
    path = tmp_path / "review.yaml"
    def journal_before_dispatch(payload):
        journal = review.read_yaml(path.with_suffix(".yaml.journal.yaml").read_bytes())
        entry = next(iter(journal["entries"].values()))
        assert entry["status"] == "pending"
        assert entry["authority"] == "ttf"
        assert payload["comment"] == "Manual note"
        assert payload["fee"] == Decimal("1.30")
    _, sender = transport(monkeypatch, row, journal_before_dispatch)
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("isolated-test-admission", 1, 0.0))
    state = review.open_review(str(path), [])
    try:
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert result.corrected == 1
        assert not result.blocked_accounts
        assert sender.call_count == 1
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert result.corrected == 0
        assert sender.call_count == 1
    finally:
        review.close_review(state)


def test_pending_request_never_resends_and_simulation_cannot_settle(settings, tmp_path, monkeypatch):
    row, event, events = sample()
    row["fee"] = 1
    events[event.comment]["brokerage"] = "1"
    events[event.comment]["values"]["fee"] = "1.30"
    events[event.comment]["payload"]["fee"] = Decimal("1.30")
    rows, sender = transport(monkeypatch, row)
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("isolated-test-admission", 1, 0.0))
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        # The request is sent, but confirmation still returns the old result.
        sender.side_effect = lambda *a, **kw: Mock(status_code=200)
        first = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert first.blocked_accounts == {"target"}
        assert sender.call_count == 1
    finally:
        review.close_review(state)
    state = review.open_review(str(path), [])
    try:
        second = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert second.blocked_accounts == {"target"}
        rows[0]["fee"] = Decimal("1.30")
        simulated = review.process_review(state, settings, "token", events)
        assert simulated.blocked_accounts == {"target"}
        assert next(iter(state["journal"]["entries"].values()))["status"] == "pending"
        recovered = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert not recovered.blocked_accounts
        assert next(iter(state["journal"]["entries"].values()))["status"] == "confirmed"
        assert sender.call_count == 1
    finally:
        review.close_review(state)


def test_extra_matching_readback_keeps_request_pending(settings, tmp_path, monkeypatch):
    row, event, events = sample()
    row["fee"] = 1
    events[event.comment]["brokerage"] = "1"
    events[event.comment]["values"]["fee"] = "1.30"
    events[event.comment]["payload"]["fee"] = Decimal("1.30")
    rows, sender = transport(monkeypatch, row)
    def add_duplicate(payload):
        duplicate = {**rows[0], **payload, "id": "unexpected-extra"}
        rows.append(duplicate)
    # Transport applies the requested result and also exposes an extra match.
    original_put = sender.side_effect
    sender.side_effect = lambda *args, **kwargs: (add_duplicate(
        json.loads(kwargs["data"], parse_float=Decimal)), original_put(*args, **kwargs))[1]
    monkeypatch.setattr(review, "QUALIFIED_EXECUTION", ("isolated-test-admission", 1, 0.0))
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    try:
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert result.blocked_accounts == {"target"}
        assert next(iter(state["journal"]["entries"].values()))["status"] == "pending"
        sender.assert_called_once()
    finally:
        review.close_review(state)


def test_manual_yes_without_timezone_survives_restart_and_preserves_tags(settings, tmp_path, monkeypatch):
    row, event, events = sample()
    row["tags"] = [{"id": "tag-1", "name": "Keep tag"}]
    row["comment"] += "\n\nKeep notes"
    rows, sender = transport(monkeypatch, row)
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        preview = review.process_review(state, settings, "token", events)
        assert preview.codes == {"review_approval"}
        sender.assert_not_called()
    finally:
        review.close_review(state)
    document = review.read_yaml(path.read_bytes())
    next(iter(document["activity_corrections"].values()))["decision"] = "yes"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    state = review.open_review(str(path), [])
    try:
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert result.corrected == 1
        assert not result.codes
        assert rows[0]["comment"].endswith("\n\nKeep notes")
        assert rows[0]["tags"] == row["tags"] and rows[0]["userId"] == "owner"
        payload = json.loads(sender.call_args.kwargs["data"], parse_float=Decimal)
        assert payload["tags"] == ["tag-1"]
        assert payload["quantity"] == event.quantity
    finally:
        review.close_review(state)


@pytest.mark.parametrize("profile", ["conservative", "balanced", "permissive"])
def test_profile_one_update_budget_and_deferred_choice_survive_restart(settings, tmp_path, monkeypatch, profile):
    row, event, events = sample()
    other = replace(event, date="2025-02-04T00:00:00+00:00", comment=event.comment[:-1] + "a")
    events.update(review.source_events([other], "TESTACCOUNT", {other.comment: [{"sha256": "b" * 64}]}))
    rows, sender = transport(monkeypatch, row)
    rows.append({**deepcopy(row), "id": "second", "date": other.date, "comment": other.comment})
    configured = replace(settings, dry_run=False, activity_reconciliation=profile, timezone="Europe/Paris")
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        result = review.process_review(state, configured, "token", events)
        assert result.corrected == 1
        assert sender.call_count == 1
        assert result.counts["automatic work deferred"] == 1
    finally:
        review.close_review(state)
    state = review.open_review(str(path), [])
    try:
        repeated = review.process_review(state, configured, "token", events)
        assert repeated.corrected == 1
        assert sender.call_count == 2
        assert {Decimal(str(row["fee"])) for row in rows} == {Decimal(1)}
        clean = review.process_review(state, configured, "token", events)
        assert clean.corrected == 0
        assert sender.call_count == 2
    finally:
        review.close_review(state)


def test_profile_normalizes_coupon_to_validated_net_without_changing_gross(settings, tmp_path, monkeypatch):
    from test_pdf_coupon import coupon_activity
    event = coupon_activity()
    row = {"id": "coupon", "accountId": "target", "userId": "owner", "tags": [],
           "date": event.date, "type": "DIVIDEND", "currency": "EUR", "comment": event.comment,
           "quantity": 2, "unitPrice": Decimal("2.43"), "fee": 0,
           "assetProfile": {"symbol": event.symbol, "isin": event.isin, "dataSource": "YAHOO"}}
    events = review.source_events([event], "TESTACCOUNT", {event.comment: [{"sha256": "a" * 64}]})
    rows, sender = transport(monkeypatch, row)
    state = review.open_review(str(tmp_path / "review.yaml"), [])
    try:
        result = review.process_review(state, replace(settings, dry_run=False,
            activity_reconciliation="conservative", timezone="Europe/Paris"), "token", events)
        assert result.corrected == 1
        assert rows[0]["quantity"] == 1
        assert rows[0]["unitPrice"] == Decimal("4.86")
        assert rows[0]["fee"] == 0
        sender.assert_called_once()
    finally:
        review.close_review(state)


@pytest.mark.parametrize("damage", ["remove", "empty-valid-document"])
def test_missing_or_replaced_journal_cannot_release_uncertain_request(settings, tmp_path, monkeypatch, damage):
    row, event, events = sample()
    row["fee"] = 1
    events[event.comment]["brokerage"] = "1"
    events[event.comment]["values"]["fee"] = "1.30"
    events[event.comment]["payload"]["fee"] = Decimal("1.30")
    _, sender = transport(monkeypatch, row)
    sender.side_effect = lambda *args, **kwargs: Mock(status_code=200)
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    journal = state["journal_path"]
    try:
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert result.blocked_accounts == {"target"}
    finally:
        review.close_review(state)
    if damage == "remove":
        journal.unlink()
    else:
        journal.write_text("version: 2\nentries: {}\n")
    with pytest.raises(RuntimeError, match="journal"):
        review.open_review(str(path), [])
    sender.assert_called_once()

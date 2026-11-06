"""Real anonymized notice shapes with explicitly derived destination states."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest
import yaml
from test_activity_review import sample
from test_correction_recovery import transport
from test_pdf_buy import settings as settings
from test_pdf_coupon import coupon_activity

from ghostfolio_boursedirect_sync import activity_review as review


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("fee", ["0.99", "14.80", "1.000"])
def test_manual_fee_only_preserves_every_other_value_and_requires_manual_yes(side, fee):
    row, event, _ = sample()
    event = replace(event, type=side, comment=event.comment.replace(":BUY:", f":{side}:"))
    events = review.source_events([event], "TESTACCOUNT", {})
    row.update(type=side, comment="Keep full\n\nmanual note", fee=Decimal(fee))
    proposals, held = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"},
                                             reconciliation="permissive", timezone="Europe/Paris")
    if Decimal(fee) == event.fee:
        assert not proposals
        assert not held
        return
    item = next(iter(proposals.values()))
    assert item["changed fields"] == ["fee"]
    assert item["proposed values"]["comment"] == row["comment"]
    assert not item["automatic eligible"]
    assert review.selected_proposals(proposals)[0] == []
    item["approve"] = "yes"
    assert len(review.selected_proposals(proposals)[0]) == 1


def coupon_case(currency="EUR", days=25):
    from datetime import timedelta

    event = coupon_activity()
    row = {"id": "coupon", "accountId": "target", "userId": "owner", "tags": [],
           "date": (review.instant(event.date) + timedelta(days=days)).isoformat(),
           "type": "DIVIDEND", "currency": currency, "comment": "Keep manual coupon note",
           "quantity": 2, "unitPrice": Decimal("9.32"), "fee": Decimal("0.10"),
           "assetProfile": {"id": "same-profile", "symbol": event.symbol, "isin": event.isin,
                            "dataSource": "YAHOO", "currency": currency}}
    events = review.source_events([event], "TESTACCOUNT", {})
    return event, row, events


@pytest.mark.parametrize("days,expected", [(31, True), (-31, True), (32, False), (-32, False)])
def test_manual_coupon_calendar_window(days, expected):
    event, row, events = coupon_case(days=days)
    proposals, held = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"}, timezone="Europe/Paris")
    assert bool(proposals) is expected
    assert (event.comment in held) is expected


def test_manual_coupon_mutual_uniqueness_and_recognized_identity_precedence():
    event, row, events = coupon_case()
    proposals, _ = review.refresh_proposals({}, events, [row, {**row, "id": "competitor"}],
                                          {"TESTACCOUNT": "target"})
    for item in proposals.values():
        item["approve"] = "yes"
        assert not item["actionable"]
    assert not review.selected_proposals(proposals)[0]
    exact = {**row, "id": "recognized", "comment": event.comment}
    proposals, _ = review.refresh_proposals({}, events, [row, exact], {"TESTACCOUNT": "target"})
    assert {item["activity id"] for item in proposals.values()} == {"recognized"}


def approve(path):
    document = review.read_yaml(path.read_bytes())
    for item in document["activity_corrections"].values():
        item["decision"] = "yes"
    path.write_text(yaml.safe_dump(document, sort_keys=False))


def test_manual_coupon_eur_keeps_sek_profile_and_is_idempotent(settings, tmp_path, monkeypatch):
    event, row, events = coupon_case("SEK")
    rows, sender = transport(monkeypatch, row)
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        preview = review.process_review(state, settings, "token", events)
        assert preview.corrected == 0
        item = next(iter(state["document"]["proposals"].values()))
        assert item["proposed values"]["currency"] == "EUR"
        assert not item["automatic eligible"]
    finally:
        review.close_review(state)
    approve(path)
    state = review.open_review(str(path), [])
    try:
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert result.corrected == 1
        assert rows[0]["currency"] == "EUR" and rows[0]["assetProfile"]["currency"] == "SEK"
        assert rows[0]["comment"] == row["comment"]
        assert rows[0]["quantity"] == 1 and rows[0]["unitPrice"] == event.unit_price and rows[0]["fee"] == 0
        assert review.process_review(state, replace(settings, dry_run=False), "token", events).corrected == 0
        sender.assert_called_once()
    finally:
        review.close_review(state)


@pytest.mark.parametrize("uncertain", [False, True])
def test_manual_fee_execution_chain_readback_pacing_and_restart(settings, tmp_path, monkeypatch, uncertain):
    row, event, _ = sample()
    row.update(comment="Manual note", fee=9)
    other = replace(event, symbol="OTHER.PA", comment=event.comment + "x", isin="FR0000000002")
    events = review.source_events([event, other], "TESTACCOUNT", {})
    rows, sender = transport(monkeypatch, row)
    second = deepcopy(row)
    second.update(id="second", assetProfile={"symbol": other.symbol, "isin": other.isin, "dataSource": "YAHOO"})
    rows.append(second)
    sleeps = []
    monkeypatch.setattr(review.time, "sleep", sleeps.append)
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        review.process_review(state, settings, "token", events)
    finally:
        review.close_review(state)
    approve(path)
    if uncertain:
        from unittest.mock import Mock
        sender.side_effect = lambda *a, **k: Mock(status_code=200)
    state = review.open_review(str(path), [])
    try:
        result = review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert sender.call_count == (1 if uncertain else 2)
        assert result.corrected == (0 if uncertain else 2)
        assert bool(result.blocked_accounts) is uncertain
        assert sleeps == ([] if uncertain else [28.0])
        review.process_review(state, replace(settings, dry_run=False), "token", events)
        assert sender.call_count == (1 if uncertain else 2)
    finally:
        review.close_review(state)

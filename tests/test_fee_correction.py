"""Offline regressions for charged TTF and the narrow BUY fee correction."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from ghostfolio_boursedirect_sync import ghostfolio, notices, sync
from ghostfolio_boursedirect_sync.models import TTF, Notice, Settings, Trade


def settings() -> Settings:
    return Settings("http://ghostfolio.test", "Example", "ACCOUNT", "http://paperless.test",
                    "paperless", "ghost", None, "", "ghostfolio-done", False)


def test_unique_ttf_is_added_to_one_buy_and_keeps_brokerage():
    source = notices.parse_text((Path(__file__).parent / "fixtures" / "pdf_buy.txt").read_text())
    trade = source.trades[0]
    notice = Notice(source.account_ref, (trade,), ttf_rows=(TTF(
        trade.date, trade.isin, Decimal("0.30")),))
    attributed, failed = sync.attribute_ttf_rows(notice)
    assert failed == ()
    assert attributed.trades[0].fee == Decimal("1.30")
    assert attributed.trades[0].brokerage == Decimal("1")


def test_ambiguous_ttf_suspends_only_the_affected_isin():
    notice = Notice("ACCOUNT", (
        Trade(date(2026, 1, 2), "FR0000000002", Decimal("4"), Decimal("25"), Decimal("1"), "BUY", Decimal("1")),
        Trade(date(2026, 1, 2), "FR0000000002", Decimal("2"), Decimal("30"), Decimal("1"), "BUY", Decimal("1")),
        Trade(date(2026, 1, 2), "FR0000000003", Decimal("1"), Decimal("10"), Decimal("1"), "BUY", Decimal("1")),
    ), ttf_rows=(TTF(date(2026, 1, 2), "FR0000000002", Decimal("0.30")),))
    attributed, failed = sync.attribute_ttf_rows(notice)
    assert failed == ("FR0000000002",)
    assert [trade.isin for trade in attributed.trades] == ["FR0000000003"]


def existing_row(fee: Decimal = Decimal("1")) -> dict[str, object]:
    return {
        "id": "activity-1", "accountId": "account-1", "date": "2026-01-02T00:00:00+00:00",
        "type": "BUY", "quantity": Decimal("4"), "unitPrice": Decimal("25"), "fee": fee,
        "currency": "EUR", "comment": "manual-buy", "tags": [],
        "assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000002"},
    }


def test_fee_correction_put_changes_only_fee_and_confirms_full_row(monkeypatch):
    current = existing_row()
    updated = existing_row(Decimal("1.30"))
    get = Mock(return_value=Mock(status_code=200,
                                 content=json.dumps({"count": 1, "activities": [updated]},
                                                    default=lambda value: float(value)).encode()))
    put = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    row = ghostfolio.index_existing_activities({"count": 1, "activities": [current]}).rows[0]
    ghostfolio.correct_activity_fee(settings(), "token", row, Decimal("1.30"))
    payload = json.loads(put.call_args.kwargs["data"])
    assert Decimal(str(payload["fee"])) == Decimal("1.3")
    assert payload["quantity"] == Decimal("4") and payload["unitPrice"] == Decimal("25")
    assert payload["comment"] == current["comment"] and payload["id"] == current["id"]
    assert get.call_count == 1


def test_fee_correction_uncertainty_never_retries_put(monkeypatch):
    current = existing_row()
    get = Mock(return_value=Mock(status_code=200,
                                 content=json.dumps({"count": 1, "activities": [current]},
                                                    default=lambda value: float(value)).encode()))
    put = Mock(side_effect=requests.Timeout())
    sleep = Mock()
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    monkeypatch.setattr(ghostfolio.time, "sleep", sleep)
    row = ghostfolio.index_existing_activities({"count": 1, "activities": [current]}).rows[0]
    with pytest.raises(RuntimeError, match="^import_unconfirmed$"):
        ghostfolio.correct_activity_fee(settings(), "token", row, Decimal("1.30"))
    put.assert_called_once()
    get.assert_called_once()
    sleep.assert_called_once_with(5)


def test_fee_correction_rejects_partial_duplicate_comment_readback(monkeypatch):
    current = existing_row()
    duplicate = {**existing_row(Decimal("1.30")), "id": "activity-2"}
    get = Mock(return_value=Mock(status_code=200, content=json.dumps(
        {"count": 2, "activities": [current, duplicate]},
        default=lambda value: float(value)).encode()))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", Mock(return_value=Mock(status_code=200)))
    row = ghostfolio.index_existing_activities({"count": 1, "activities": [current]}).rows[0]
    with pytest.raises(RuntimeError, match="^import_unconfirmed$"):
        ghostfolio.correct_activity_fee(settings(), "token", row, Decimal("1.30"))

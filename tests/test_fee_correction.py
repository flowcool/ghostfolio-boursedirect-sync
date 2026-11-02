"""Offline regressions for charged TTF and the narrow BUY fee correction."""

import json
import logging
import socket
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from ghostfolio_boursedirect_sync import (
    app,
    config,
    ghostfolio,
    notices,
    paperless,
    sync,
)
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


def test_derived_ambiguous_ttf_exits_one_without_writes(monkeypatch, caplog):
    """Derived error data, not an observed financial case or real-PDF proof."""
    text = (Path(__file__).parent / "fixtures" / "pdf_buy.txt").read_text()
    # Keep the anonymized BUY layout. Add a second valid same-day BUY and tax.
    second_buy = text[text.index("   03/02/2025"):]
    second_buy = (second_buy.replace("QUANTITE : 4", "QUANTITE : 2")
                  .replace("102.00", "51.00").replace("103.00", "52.00"))
    derived = text + "\n" + second_buy + "\n03/02/2025 TAXE TRANSACT FINANCIERES FR0000120271  0.30\n"
    parsed = notices.parse_text(derived)
    assert len(parsed.trades) == 2 and len(parsed.ttf_rows) == 1
    assert {trade.date for trade in parsed.trades} == {date(2025, 2, 3)}
    assert {trade.isin for trade in parsed.trades} == {"FR0000120271"}

    run_settings = settings()
    monkeypatch.setattr(config, "load", lambda: replace(run_settings, bd_account_ref=parsed.account_ref))
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"derived-notice-placeholder")
    monkeypatch.setattr(notices, "extract_text", lambda _: derived)
    network = Mock(side_effect=AssertionError("network forbidden"))
    post = Mock(side_effect=AssertionError("POST forbidden"))
    put = Mock(side_effect=AssertionError("PUT forbidden"))
    monkeypatch.setattr(requests.sessions.Session, "request", network)
    monkeypatch.setattr(socket.socket, "connect", network)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "put", put)

    errors = set()
    with caplog.at_level(logging.INFO):
        assert app.run_sync(errors) == 1

    assert errors == {"ttf_attribution_failed"}
    assert "ttf_attribution_failed document=1" in caplog.text
    assert "created=0" in caplog.text
    post.assert_not_called()
    put.assert_not_called()
    network.assert_not_called()


def existing_row(fee: Decimal = Decimal("1")) -> dict[str, object]:
    return {
        "id": "activity-1", "accountId": "account-1", "date": "2026-01-02T00:00:00+00:00",
        "type": "BUY", "quantity": Decimal("4"), "unitPrice": Decimal("25"), "fee": fee,
        "currency": "EUR", "comment": "manual-buy", "tags": [],
        "assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000002"},
    }



@pytest.mark.parametrize("note", ["Manual note", "__DECIMAL__1__", "___DECIMAL__1__"])
def test_review_update_sends_exact_decimals_once(monkeypatch, note):
    payload = {"id": "activity-1", "accountId": "account-1", "currency": "EUR",
               "date": "2026-01-02T00:00:00Z", "type": "BUY", "comment": note,
               "symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "quantity": Decimal("4"),
               "unitPrice": Decimal("25.1234567890123456789"), "fee": Decimal("1.30"), "tags": []}
    put = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(requests, "put", put)
    ghostfolio.update_reviewed_activity(settings(), "token", payload)
    sent = json.loads(put.call_args.kwargs["data"], parse_float=Decimal)
    assert sent == payload
    put.assert_called_once()
    assert put.call_args.kwargs["allow_redirects"] is False


def test_review_update_timeout_never_resends(monkeypatch):
    payload = {"id": "activity-1", "accountId": "account-1", "currency": "EUR",
               "date": "2026-01-02T00:00:00Z", "type": "BUY", "comment": "Manual note",
               "symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "quantity": Decimal("4"),
               "unitPrice": Decimal("25"), "fee": Decimal("1.30"), "tags": []}
    put = Mock(side_effect=requests.Timeout())
    monkeypatch.setattr(requests, "put", put)
    with pytest.raises(RuntimeError, match="^import_unconfirmed$"):
        ghostfolio.update_reviewed_activity(settings(), "token", payload)
    put.assert_called_once()

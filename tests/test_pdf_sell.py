"""SELL/custody layouts extracted from retained real PDFs, with identifiers removed.

pdf_sell_custody: foreign sale and a separate custody debit.
pdf_sells: two domestic sales; a shared anonymized ISIN exercises cumulative sales.
pdf_custody: a custody-only notice. Fixtures omit holder data and page furniture.
These tests are offline evidence, not Paperless or Ghostfolio service acceptance.
"""

import json
import logging
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from ghostfolio_boursedirect_sync import app, ghostfolio, notices, sync
from ghostfolio_boursedirect_sync.models import ActivityIndex

FIXTURES = Path(__file__).parent / "fixtures"


def test_real_foreign_sell_and_custody_are_separate():
    notice = notices.parse_text((FIXTURES / "pdf_sell_custody.txt").read_text())
    sale, = notice.trades
    assert notice.custody_fees == 1
    result = sync.activity(sale, {sale.isin: "EXAMPLE.PA"}, "target", notice.account_ref,
                           sync.notice_namespace(notice), 0)
    assert result.type == "SELL"
    assert result.quantity == Decimal(47)
    assert result.unit_price == Decimal("24.02")
    assert result.fee == Decimal("5.64")
    assert result.currency == "EUR"
    assert result.date == "2026-07-01T00:00:00+00:00"
    assert result.comment.startswith("BD#v3#TESTACCOUNT:SELL:")


def test_two_real_sells_cannot_spend_the_same_position_twice():
    notice = notices.parse_text((FIXTURES / "pdf_sells.txt").read_text())
    candidates = [sync.activity(trade, {trade.isin: "EXAMPLE.PA"}, "target", notice.account_ref,
                                sync.notice_namespace(notice), rank)
                  for rank, trade in enumerate(notice.trades)]
    existing = ActivityIndex((), {}, {("target", "EXAMPLE.PA"): Decimal(150)})
    result = sync.select_account_activities(list(reversed(candidates)), existing)
    assert len(result.activities) == 1
    assert result.errors == ("sell_exceeds_holding",)
    assert result.activities[0].quantity <= 150
    assert existing.positions == {("target", "EXAMPLE.PA"): Decimal(150)}


def sale_activity():
    notice = notices.parse_text((FIXTURES / "pdf_sell_custody.txt").read_text())
    trade, = notice.trades
    return sync.activity(trade, {trade.isin: "EXAMPLE.PA"}, "target", notice.account_ref,
                         sync.notice_namespace(notice), 0)


@pytest.mark.parametrize("buy_day,sale_allowed", [(date(2026, 6, 30), True),
                                                (date(2026, 7, 1), False),
                                                (date(2026, 7, 2), False)])
def test_only_an_earlier_new_buy_supports_a_sell(buy_day, sale_allowed):
    notice = notices.parse_text((FIXTURES / "pdf_buy.txt").read_text())
    buy = replace(notice.trades[0], date=buy_day, quantity=Decimal(47), isin="FR0000000002")
    purchase = sync.activity(buy, {buy.isin: "EXAMPLE.PA"}, "target", notice.account_ref,
                             sync.notice_namespace(replace(notice, trades=(buy,))), 0)
    sale = sale_activity()
    for candidates in ([purchase, sale], [sale, purchase]):
        result = sync.select_account_activities(candidates, ActivityIndex((), {}, {}))
        assert result.activities == ((purchase, sale) if sale_allowed else (purchase,))
        assert result.errors == (() if sale_allowed else ("sell_exceeds_holding",))


@pytest.mark.parametrize("shortfall", [Decimal(0), Decimal("0.00000000000000000000000000001")])
def test_exact_decimal_sell_guard_has_no_tolerance(shortfall):
    sale = replace(sale_activity(), quantity=Decimal("47.12345678901234567890123456789"))
    # The literal position is below the sale by 1e-29 in the second case.
    holding = Decimal("47.12345678901234567890123456789") if not shortfall else Decimal(
        "47.12345678901234567890123456788")
    result = sync.select_account_activities([sale], ActivityIndex((), {}, {("target", "EXAMPLE.PA"): holding}))
    assert result.activities == (() if shortfall else (sale,))
    assert result.errors == (("sell_exceeds_holding",) if shortfall else ())


@pytest.mark.parametrize("manual", [True, False])
def test_existing_sell_is_a_duplicate_before_the_holdings_guard(manual):
    sale = sale_activity()
    ledger = ghostfolio.index_existing_activities({"count": 1, "activities": [{
        "id": "existing-sell", "accountId": "target", "date": sale.date,
        "type": "SELL", "quantity": 47, "unitPrice": Decimal("24.02"), "fee": Decimal("5.64"),
        "currency": "EUR", "comment": "" if manual else sale.comment,
        "assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": sale.isin},
    }]})
    result = sync.select_account_activities([sale], ledger)
    assert result.activities == ()
    assert result.errors == ()
    assert result.duplicates == 1


def test_another_accounts_position_cannot_support_the_sell():
    result = sync.select_account_activities([sale_activity()], ActivityIndex(
        (), {}, {("other", "EXAMPLE.PA"): Decimal(1000)}))
    assert result.activities == ()
    assert result.errors == ("sell_exceeds_holding",)


def test_rejected_sell_does_not_consume_holdings_or_block_an_independent_security():
    sale = sale_activity()
    large = replace(sale, quantity=Decimal(48), date="2026-06-30T00:00:00+00:00",
                    comment=sale.comment + "large")
    independent = replace(sale, symbol="OTHER.PA", comment=sale.comment + "other")
    result = sync.select_account_activities([sale, independent, large], ActivityIndex(
        (), {}, {("target", "EXAMPLE.PA"): Decimal(47), ("target", "OTHER.PA"): Decimal(47)}))
    assert set(result.activities) == {sale, independent}
    assert result.errors == ("sell_exceeds_holding",)


@pytest.mark.parametrize("change", ["unknown-operation", "unknown-field", "custody-field", "invalid-date"])
def test_sell_or_custody_with_an_unknown_layout_fails_closed(change):
    text = (FIXTURES / "pdf_sell_custody.txt").read_text()
    if change == "unknown-operation":
        text = text.replace("VENTE ETRANGER", "VENTE INCONNUE")
    elif change == "unknown-field":
        text = text.replace("COURTAGE", "INCONNU")
    elif change == "custody-field":
        text += "\nQUANTITE : 1\n"
    else:
        text = text.replace("01/07/2026", "32/07/2026")
    with pytest.raises(RuntimeError, match="^notice_unreadable$"):
        notices.parse_text(text)


@pytest.mark.parametrize("fixture,holding,expected,simulated", [
    ("pdf_sell_custody.txt", 0, 1, 0),
    ("pdf_sell_custody.txt", 47, 0, 1),
    ("pdf_custody.txt", 0, 0, 0),
])
def test_sell_and_custody_simulation(fixture, holding, expected, simulated, monkeypatch, caplog):
    for name in ("GHOST_ACCESS_TOKEN", "DRY_RUN", "MAPPING_FILE"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        "GHOST_HOST": "http://ghostfolio.test", "GHOST_TOKEN": "offline-token",
        "GHOST_ACCOUNT_NAME": "Example PEA", "BD_ACCOUNT_REF": "TESTACCOUNT",
        "PAPERLESS_URL": "http://paperless.test", "PAPERLESS_TOKEN": "offline-token",
    }.items():
        monkeypatch.setenv(name, value)
    text = (FIXTURES / fixture).read_text()
    monkeypatch.setattr(notices, "extract_text", lambda _: text)

    def get(url, **kwargs):
        if url.endswith("/api/documents/"):
            body = {"count": 1, "next": None, "results": [{"id": 123}]}
        elif url.endswith("/api/documents/123/download/"):
            return Mock(status_code=200, content=b"offline PDF extraction boundary")
        elif url.endswith("/api/v1/account"):
            body = {"accounts": [{"id": "target", "name": "Example PEA"}]}
        elif url.endswith("/api/v1/activities"):
            rows = [] if not holding else [{
                "id": "existing-buy", "accountId": "target", "date": "2025-01-01T00:00:00Z",
                "type": "BUY", "quantity": holding, "unitPrice": 20, "fee": 0,
                "currency": "EUR", "comment": "", "assetProfile": {
                    "symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000002"},
            }]
            body = {"count": len(rows), "activities": rows}
        elif url.endswith("/api/v1/symbol/lookup"):
            body = {"items": [{"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "currency": "EUR"}]}
        else:
            raise AssertionError("unexpected URL")
        return Mock(status_code=200, content=json.dumps(body).encode(), json=lambda: body)

    monkeypatch.setattr(requests, "get", Mock(side_effect=get))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected write")))
    with caplog.at_level(logging.INFO):
        assert app.main() == expected
    assert "custody_fee_ignored document=123" in caplog.text
    assert f"simulated={simulated}" in caplog.text
    assert ("sell_exceeds_holding" in caplog.text) == bool(expected)
    assert ("type=SELL" in caplog.text) == bool(simulated)
    assert "CONSERV" not in caplog.text
    assert "offline-token" not in caplog.text

"""COUPONS layout from retained PDFs, with the existing anonymized coupon values.

pdf_coupon.txt transcribes note-coupon-anonymized-real.html's first coupon.
Its printed net differs from BRUT. These tests prove offline decisions only.
Changed labels, dates and financial fields below are deliberate alterations.
"""

import logging
import socket
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from ghostfolio_boursedirect_sync import app, config, ghostfolio, notices, paperless, sync
from ghostfolio_boursedirect_sync.models import ActivityIndex, Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline coupon test attempted network access")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def coupon_text():
    return (FIXTURES / "pdf_coupon.txt").read_text()


def coupon_activity():
    notice = notices.parse_text(coupon_text())
    return sync.activity(notice.trades[0], {"FR0000000002": "EXAMPLE.PA"}, "target",
                         notice.account_ref, sync.notice_namespace(notice), 0)


def ledger(candidate, **changes):
    row = {
        "id": "existing", "accountId": "target", "date": candidate.date,
        "type": "DIVIDEND", "quantity": 1, "unitPrice": Decimal("4.86"), "fee": 0,
        "currency": "EUR", "comment": "", "assetProfile": {
            "symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000002"},
    }
    row.update(changes)
    return ghostfolio.index_existing_activities({"count": 1, "activities": [row]})


def test_coupon_uses_printed_net_and_does_not_infer_tax_from_gross():
    notice = notices.parse_text(coupon_text())
    trade, = notice.trades
    assert (trade.type, trade.quantity, trade.unit_price, trade.fee) == (
        "DIVIDEND", Decimal(1), Decimal("4.86"), Decimal(0))
    assert notice.inferred_brokerages == notice.custody_fees == 0
    candidate = coupon_activity()
    assert candidate.date == "2026-07-02T00:00:00+00:00"
    assert candidate.currency == "EUR"
    assert candidate.comment.startswith("BD#v3#TESTACCOUNT:DIVIDEND:")


@pytest.mark.parametrize("old,new,code", [
    ("4,86", "0,00", "amount_check_failed"),
    ("4,86", "-4,86", "amount_check_failed"),
    ("EUR PEA", "USD PEA", "notice_unreadable"),
    ("COMMISSION", "WITHHOLDING", "notice_unreadable"),
    ("FR0000000002", "", "notice_unreadable"),
])
def test_coupon_retains_field_and_amount_guards(old, new, code):
    with pytest.raises(RuntimeError, match=f"^{code}$"):
        notices.parse_text(coupon_text().replace(old, new))


@pytest.mark.parametrize("days", [-4, -3, 0, 3, 4])
def test_manual_coupon_matches_identical_net_within_three_calendar_days(days):
    candidate = coupon_activity()
    day = ghostfolio.activity_instant(candidate.date) + timedelta(days=days)
    existing = ledger(candidate, date=day.isoformat(), quantity=2, unitPrice=Decimal("2.43"))
    result = sync.select_account_activities([candidate], existing)
    assert result.errors == ()
    assert result.duplicates == int(abs(days) <= 3)
    assert result.activities == (() if abs(days) <= 3 else (candidate,))


def test_different_nearby_net_is_possible_duplicate():
    candidate = coupon_activity()
    result = sync.select_account_activities([candidate], ledger(candidate, unitPrice=Decimal("5.72")))
    assert result.activities == () and result.duplicates == 0
    assert result.errors == ("possible_duplicate",)


@pytest.mark.parametrize("price,fee,duplicate", [
    ("4.86", "0.86", False), ("5.72", "0.86", True),
])
def test_manual_dividend_net_subtracts_only_explicit_existing_fee(price, fee, duplicate):
    candidate = coupon_activity()
    result = sync.select_account_activities([candidate], ledger(
        candidate, unitPrice=Decimal(price), fee=Decimal(fee)))
    assert result.activities == ()
    assert result.duplicates == int(duplicate)
    assert result.errors == (() if duplicate else ("possible_duplicate",))


@pytest.mark.parametrize("changes", [
    {"accountId": "other"}, {"type": "BUY"},
    {"isDraft": True}, {"assetProfile": {"symbol": "OTHER.PA", "dataSource": "YAHOO"}},
])
def test_ineligible_or_unrelated_row_is_not_a_coupon_match(changes):
    candidate = coupon_activity()
    result = sync.select_account_activities([candidate], ledger(candidate, **changes))
    assert result.activities == (candidate,)
    assert result.duplicates == 0 and result.errors == ()


def test_nearby_dividend_in_another_currency_requires_review():
    candidate = coupon_activity()
    result = sync.select_account_activities([candidate], ledger(candidate, currency="USD"))
    assert result.activities == () and result.duplicates == 0
    assert result.errors == ("possible_duplicate",)


@pytest.mark.parametrize("changed", [False, True])
def test_owned_identity_requires_all_fields_exact(changed):
    candidate = coupon_activity()
    result = sync.select_account_activities([candidate], ledger(
        candidate, comment=candidate.comment, fee=Decimal("0.01") if changed else Decimal(0)))
    assert result.activities == ()
    assert result.duplicates == int(not changed)
    assert result.errors == (("owned_activity_conflict",) if changed else ())


def test_competing_net_matches_use_one_to_one_assignment():
    first = coupon_activity()
    second = replace(first, comment=first.comment + "second",
                     date="2026-07-05T00:00:00+00:00")
    existing = ledger(first, quantity=2, unitPrice=Decimal("2.43"))
    for candidates in ([first, second], [second, first]):
        result = sync.select_account_activities(candidates, existing)
        assert result.duplicates == 1
        assert result.activities == (second,)
        assert result.errors == ()


def test_net_comparison_preserves_precision_under_small_decimal_context():
    candidate = replace(coupon_activity(), unit_price=Decimal("12345678901234567890.123456789"))
    existing = ledger(candidate, quantity=3, unitPrice=Decimal("4115226300411522630.041152263"))
    with localcontext() as context:
        context.prec = 4
        result = sync.select_account_activities([candidate], existing)
    assert result.duplicates == 1 and result.activities == () and result.errors == ()


def test_source_copies_and_identical_occurrences_remain_distinct():
    text = coupon_text()
    repeated = text + text.split("\n", 1)[1]
    notice = notices.parse_text(repeated)
    candidates = [sync.activity(t, {t.isin: "EXAMPLE.PA"}, "target", notice.account_ref,
                                sync.notice_namespace(notice), rank)
                  for rank, t in enumerate(notice.trades)]
    result = sync.select_account_activities(candidates + candidates, ActivityIndex((), {}, {}))
    assert len(result.activities) == 2 and result.duplicates == 2 and result.errors == ()
    assert len({a.comment for a in result.activities}) == 2


@pytest.mark.parametrize("duplicate", [False, True])
def test_application_coupon_simulation_without_protocol_emulation(duplicate, monkeypatch, caplog):
    candidate = coupon_activity()
    settings = Settings("http://ghostfolio.test", "Example PEA", "TESTACCOUNT",
                        "http://paperless.test", "offline", "offline", None, "", "done", True)
    monkeypatch.setattr(config, "load", lambda: settings)
    # Direct source/ledger function boundaries, no fake server or HTTP responses.
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"offline")
    monkeypatch.setattr(notices, "extract_text", lambda _: coupon_text())
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: (
        ledger(candidate) if duplicate else ActivityIndex((), {}, {})))
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
    with caplog.at_level(logging.INFO):
        assert app.main() == 0
    assert f"simulated={int(not duplicate)} duplicates={int(duplicate)}" in caplog.text
    assert ("type=DIVIDEND" in caplog.text) == (not duplicate)
    assert "created=0" in caplog.text

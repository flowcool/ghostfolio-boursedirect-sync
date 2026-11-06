"""Available-notice reporting uses real anonymized fixtures and derived ledgers."""

import logging
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_activity_review import sample
from test_manual_history import coupon_case
from test_pdf_buy import settings as settings

from ghostfolio_boursedirect_sync import (
    app,
    config,
    ghostfolio,
    notice_coverage,
    notices,
    paperless,
    sync,
)
from ghostfolio_boursedirect_sync.models import Notice, Trade


def test_coverage_absent_fee_difference_and_corrected_repeat(caplog):
    row, event, _ = sample()
    source = notices.parse_text((Path(__file__).parent / "fixtures/pdf_buy.txt").read_text())
    mapping = {source.trades[0].isin: event.symbol}
    row.update(comment="manual", fee=Decimal("9"))
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    codes, actions = set(), {}
    with caplog.at_level(logging.INFO):
        counts = notice_coverage.report([(1, source), (2, source)], mapping, "target", index, codes, actions, "UTC")
    assert counts == {"correction candidate": 1}
    assert "absent supported" not in counts
    assert "rows=2" in caplog.text
    row["fee"] = event.fee
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    assert notice_coverage.report([(1, source)], mapping, "target", index, set(), {}, "UTC") == {"conforming": 1}
    empty = ghostfolio.index_existing_activities({"count": 0, "activities": []})
    counts = notice_coverage.report([(1, source)], mapping, "target", empty, codes, actions, "UTC")
    assert counts == {"absent supported": 1}
    assert codes == {"coverage_gap", "position_mismatch"}


def test_normalized_quantity_is_uncertain_and_not_absent():
    row, event, _ = sample()
    source = notices.parse_text((Path(__file__).parent / "fixtures/pdf_buy.txt").read_text())
    row.update(comment="manual", quantity=Decimal("0.4"), unitPrice=Decimal("255"))
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    codes = set()
    counts = notice_coverage.report([(1, source)], {source.trades[0].isin: event.symbol}, "target", index, codes, {}, "UTC")
    assert counts == {"unresolved association": 1, "unverifiable positions": 1}
    assert "coverage_gap" not in codes


def test_wide_coupon_and_wrong_currency_are_existing_candidates():
    event, row, _ = coupon_case("SEK")
    trade = Trade(ghostfolio.activity_instant(event.date).date(), event.isin, event.quantity, event.unit_price, event.fee, "DIVIDEND")
    source = Notice("TESTACCOUNT", (trade,))
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    counts = notice_coverage.report([(1, source)], {event.isin: event.symbol}, "target", index, set(), {}, "UTC")
    assert counts == {"correction candidate": 1}


def test_coverage_mode_never_opens_review_or_writes_with_yes_and_pending(settings, tmp_path, monkeypatch):
    path = tmp_path / "review.yaml"
    path.write_text("unreadable YAML with pending request and yes")
    original = path.read_bytes()
    monkeypatch.setattr(config, "load", lambda: replace(settings, dry_run=False, notice_coverage=True, activity_review_file=str(path)))
    source = (Path(__file__).parent / "fixtures/pdf_buy.txt").read_text()
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1, 2])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"derived-source-boundary")
    monkeypatch.setattr(notices, "extract_text", lambda _: source)
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "lab")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities({"count": 0, "activities": []}))
    post, put = Mock(side_effect=AssertionError("no import")), Mock(side_effect=AssertionError("no correction"))
    monkeypatch.setattr(ghostfolio, "import_activities", post)
    monkeypatch.setattr(ghostfolio, "update_reviewed_activity", put)
    codes = set()
    assert app.run_sync(codes) == 0
    assert "coverage_gap" in codes
    assert path.read_bytes() == original
    assert not path.with_suffix(".yaml.state.yaml").exists()
    post.assert_not_called()
    put.assert_not_called()


@pytest.mark.parametrize("value,valid", [("0", True), ("1", True), ("", False), ("true", False), ("2", False)])
def test_notice_coverage_env(settings, monkeypatch, value, valid):
    monkeypatch.setenv("NOTICE_COVERAGE", value)
    if valid:
        assert config.load().notice_coverage is (value == "1")
    else:
        with pytest.raises(RuntimeError, match="NOTICE_COVERAGE"):
            config.load()


def test_missing_review_holds_fee_and_wide_coupon(settings, monkeypatch):
    source = (Path(__file__).parent / "fixtures/pdf_buy.txt").read_text()
    row, _, _ = sample()
    row.update(comment="manual", fee=Decimal("9"))
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"source-boundary")
    monkeypatch.setattr(notices, "extract_text", lambda _: source)
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "lab")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: index)
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    codes = set()
    assert app.run_sync(codes) == 0
    assert codes == {"review_evidence"}


def test_unverified_isin_alias_is_held_without_hiding_unrelated_absence():
    event, row, _ = coupon_case()
    event = replace(event, symbol=event.isin + ".SG")
    trade = Trade(ghostfolio.activity_instant(event.date).date(), event.isin, event.quantity,
                  event.unit_price, event.fee, "DIVIDEND")
    row.update(quantity=1, unitPrice=event.unit_price, fee=0)
    row["assetProfile"].pop("isin")
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    source = Notice("TESTACCOUNT", (trade,))
    assert sync.unresolved_alias_rows(event, index)
    codes = set()
    counts = notice_coverage.report([(1, source)], {event.isin: event.symbol}, "target", index, codes, {}, "UTC")
    assert counts == {"unresolved association": 1}
    assert codes == {"coverage_unverifiable"}
    assert not sync.unresolved_alias_rows(replace(event, symbol="UNRELATED.PA"), index)
    counts = notice_coverage.report([(1, source)], {event.isin: "UNRELATED.PA"}, "target", index, set(), {}, "UTC")
    assert counts == {"absent supported": 1}


def test_interval_trade_changes_before_and_after_backfill(caplog):
    from datetime import date

    first = Trade(date(2026, 2, 9), "BE0003739530", Decimal(18), Decimal("43.16"), Decimal("1.90"), "SELL")
    second = Trade(date(2026, 6, 4), "BE0003735496", Decimal(2), Decimal("257.8"), Decimal("1.90"), "BUY")
    mapping = {first.isin: "APAM.AS", second.isin: "UCB.BR"}
    source = Notice("TESTACCOUNT", (first, second))
    empty = ghostfolio.index_existing_activities({"count": 0, "activities": []})
    with caplog.at_level(logging.INFO):
        notice_coverage.report([(1, source)], mapping, "target", empty, set(), {}, "UTC")
    assert "unexplained_change=-18" in caplog.text
    assert "unexplained_change=2" in caplog.text
    row, _, _ = sample()
    rows = []
    for trade in source.trades:
        event = sync.activity(trade, mapping, "target", "TESTACCOUNT", sync.notice_namespace(source), 0)
        derived = {**row, "id": event.symbol, "date": event.date, "type": event.type,
                   "quantity": event.quantity, "unitPrice": event.unit_price, "fee": event.fee,
                   "comment": event.comment, "assetProfile": {"symbol": event.symbol, "isin": event.isin,
                                                                "dataSource": "YAHOO", "currency": "EUR"}}
        rows.append(derived)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        counts = notice_coverage.report([(1, source)], mapping, "target",
            ghostfolio.index_existing_activities({"count": 2, "activities": rows}), set(), {}, "UTC")
    assert counts == {"conforming": 2}
    assert caplog.text.count("unexplained_change=0") == 2


def test_conflicting_isin_under_same_symbol_is_uncertain_not_absent():
    row, event, _ = sample()
    source = notices.parse_text((Path(__file__).parent / "fixtures/pdf_buy.txt").read_text())
    row.update(comment="manual")
    row["assetProfile"]["isin"] = "FR9999999999"
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    codes = set()
    counts = notice_coverage.report([(1, source)], {source.trades[0].isin: event.symbol}, "target", index, codes, {}, "UTC")
    assert counts == {"unresolved association": 1, "unverifiable positions": 1}
    assert codes == {"coverage_unverifiable"}


def test_owned_ttf_holds_count_each_source_event(settings, monkeypatch):
    text = (Path(__file__).parent / "fixtures/pdf_buy.txt").read_text()
    originals = [text + "\n03/02/2025 TAXE TRANSACT FINANCIERES FR0000120271  0.30\n",
                 text.replace("03/02/2025", "05/02/2025") +
                 "\n05/02/2025 TAXE TRANSACT FINANCIERES FR0000120271  0.30\n"]
    rows = []
    for i, original in enumerate(originals):
        source, failed = sync.attribute_ttf_rows(notices.parse_text(original))
        assert not failed
        event = sync.activity(source.trades[0], {source.trades[0].isin: "EXAMPLE.PA"}, "target",
                              source.account_ref, sync.notice_namespace(source), 0)
        row, _, _ = sample()
        row.update(id=str(i), date=event.date, comment=event.comment, fee=1)
        row["assetProfile"]["isin"] = event.isin
        rows.append(row)
    monkeypatch.setattr(config, "load", lambda: settings)
    monkeypatch.setattr(paperless, "document_ids", lambda _: [0, 1])
    monkeypatch.setattr(paperless, "original_pdf", lambda _, document: str(document).encode())
    monkeypatch.setattr(notices, "extract_text", lambda pdf: originals[int(pdf)])
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities(
        {"count": len(rows), "activities": rows}))
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    codes, actions = set(), {}
    assert app.run_sync(codes, actions=actions) == 0
    assert codes == {"review_evidence"}
    assert len(actions["review_evidence"]) == 2


@pytest.mark.parametrize("damage", ["other-account", "draft", "wrong-type"])
def test_exact_identity_cannot_certify_an_ineligible_destination(damage):
    """Real notice text; destination eligibility states are derived."""
    row, event, _ = sample()
    source = notices.parse_text((Path(__file__).parent / "fixtures/pdf_buy.txt").read_text())
    event = sync.activity(source.trades[0], {source.trades[0].isin: event.symbol}, "target",
                          source.account_ref, sync.notice_namespace(source), 0)
    row.update(comment=event.comment, fee=event.fee)
    if damage == "other-account":
        row["accountId"] = "other"
    elif damage == "draft":
        row["isDraft"] = True
    else:
        row["type"] = "SELL"
        row["comment"] = ""
    index = ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    codes = set()
    counts = notice_coverage.report([(1, source)], {source.trades[0].isin: event.symbol},
                                    "target", index, codes, {}, "UTC")
    assert "conforming" not in counts
    assert "correction candidate" not in counts

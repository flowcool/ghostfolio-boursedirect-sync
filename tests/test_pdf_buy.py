"""Offline checks from the retained foreign-BUY PDF.

The fixture keeps the extracted account and BUY layout. Holder/address/footer
lines are excluded. Account, date, security, amounts and time are anonymized.
HTTP response shapes follow paperless-ngx 2b00cf6 and pinned ibkr account reads.
These checks do not replace the authorized real service acceptance run.
"""

import json
import logging
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
from ghostfolio_boursedirect_sync.models import Activity, ActivityIndex

FIXTURE = Path(__file__).parent / "fixtures" / "pdf_buy.txt"


@pytest.fixture
def settings(monkeypatch):
    for name in ("DRY_RUN", "GHOST_ACCESS_TOKEN", "MAPPING_FILE", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {
        "GHOST_HOST": "http://ghostfolio.test",
        "GHOST_TOKEN": "offline-ghost-token",
        "GHOST_ACCOUNT_NAME": "Example PEA",
        "BD_ACCOUNT_REF": "TESTACCOUNT",
        "PAPERLESS_URL": "http://paperless.test",
        "PAPERLESS_TOKEN": "offline-paperless-token",
    }.items():
        monkeypatch.setenv(name, value)
    return config.load()


def test_real_anonymized_buy():
    notice = notices.parse_text(FIXTURE.read_text())
    assert notice.account_ref == "TESTACCOUNT"
    assert len(notice.trades) == 1
    buy = notice.trades[0]
    assert (buy.date, buy.isin) == (date(2025, 2, 3), "FR0000120271")
    assert (buy.quantity, buy.unit_price, buy.fee) == (Decimal(4), Decimal("25.50"), Decimal(1))
    result = sync.activity(buy, {buy.isin: "EXAMPLE.PA"}, "target", notice.account_ref,
                           sync.notice_namespace(notice), 0)
    assert result.date == "2025-02-03T00:00:00+00:00"
    assert result.currency == "EUR"
    assert result.type == "BUY"
    assert isinstance(result.unit_price, Decimal)


@pytest.mark.parametrize("change", ["missing", "same_line", "second_line"])
def test_account_label_must_be_unique(change):
    text = FIXTURE.read_text()
    account = text.splitlines()[0]
    if change == "missing":
        text = text.replace(account, "")
    elif change == "same_line":
        text = text.replace(account, account + " " + account)
    else:
        text += "\n" + account
    with pytest.raises(RuntimeError, match="^notice_unreadable$"):
        notices.parse_text(text)


@pytest.mark.parametrize("edits", [
    {"102.00": "102.01", "103.00": "103.01"},
    {"103.00": "103.01"},
    {"TVA : 0.00": "TVA : 0.01", "103.00": "103.01"},
    {"COURTAGE : 1.00": "COURTAGE : -1.00", "103.00": "101.00"},
], ids=["quantity-price", "debit", "vat", "negative-fee"])
def test_each_amount_guard_fails_alone(edits):
    text = FIXTURE.read_text()
    for old, new in edits.items():
        assert old in text
        text = text.replace(old, new)
    with pytest.raises(RuntimeError, match="^amount_check_failed$"):
        notices.parse_text(text)


@pytest.mark.parametrize("value", ["", "false", "true", " 1", "01"])
def test_mode_values_are_exact(settings, monkeypatch, value):
    monkeypatch.setenv("DRY_RUN", value)
    with pytest.raises(RuntimeError, match="invalid_configuration DRY_RUN"):
        config.load()


def test_done_tag_defaults_and_rejects_control_characters(settings, monkeypatch):
    assert settings.paperless_done_tag == "ghostfolio-done"
    monkeypatch.setenv("PAPERLESS_DONE_TAG", "bad\n tag")
    with pytest.raises(RuntimeError, match="invalid_configuration PAPERLESS_DONE_TAG"):
        config.load()


def test_simulation_and_no_notification(settings, monkeypatch, caplog):
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    monkeypatch.setattr(paperless, "document_ids", lambda _: [123])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"original")
    monkeypatch.setattr(notices, "extract_text", lambda _: FIXTURE.read_text())
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    # Any unexpected I/O, including a notification or import, fails this test.
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected HTTP")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 0
    assert "DRY RUN" in caplog.text
    assert "type=BUY" in caplog.text
    assert "simulated=1" in caplog.text
    assert "date=2025-02-03T00:00:00+00:00" in caplog.text


def test_debug_preview_keeps_exact_decimal_and_original_source(settings, monkeypatch, caplog):
    """The native image exposes evidence; this isolated test is not a service replay."""
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    monkeypatch.setattr(paperless, "document_ids", lambda _: [123])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"original")
    monkeypatch.setattr(notices, "extract_text", lambda _: FIXTURE.read_text())
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected HTTP")))
    with caplog.at_level(logging.DEBUG):
        assert app.main() == 0
    records = [json.loads(r.message.split("LAB_EVIDENCE ", 1)[1])
               for r in caplog.records if "LAB_EVIDENCE " in r.message]
    source, preview = records
    assert source == {"kind": "source", "value": [{"id": 123, "sha256":
        "0682c5f2076f099c34cfdd15a9e063849ed437a49677e6fcc5b4198c76575be5"}]}
    assert preview["kind"] == "preview"
    row, = preview["value"]
    assert (row["quantity"], row["unitPrice"], row["fee"]) == ("4", "25.50", "1.00")
    assert row["accountId"] == "target"
    assert row["dataSource"] == "YAHOO"


def test_writes_remain_unavailable(settings, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr(paperless, "document_ids", lambda _: [])
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected POST")))
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected GET")))
    assert app.main() == 0


@pytest.mark.parametrize("items,expected,reason", [
    ([{"symbol": "EXAMPLE.PA", "currency": "EUR", "dataSource": "YAHOO"}], 0, None),
    ([], 1, None),
    ([{"symbol": "EXAMPLE", "currency": "USD", "dataSource": "YAHOO"}], 1, None),
    ([{"symbol": s, "currency": "EUR", "dataSource": "YAHOO"}
      for s in ("FIRST.PA", "SECOND.PA")], 1, None),
    ([{"symbol": "EXAMPLE.PA", "currency": "EUR", "dataSource": "YAHOO"},
      {"symbol": "EXAMPLE", "currency": "USD", "dataSource": "YAHOO"}], 0, None),
    ([{"symbol": "EXAMPLE.PA", "currency": "EUR", "dataSource": "MANUAL"}], 1, None),
    ([{"currency": "EUR", "dataSource": "YAHOO"}], 1, "reason=invalid_response"),
    ([{"symbol": "bad\nline", "currency": "EUR", "dataSource": "YAHOO"}], 1, "reason=invalid_response"),
    ([{"symbol": "EXAMPLE.PA", "dataSource": "YAHOO"}], 1, None),
    ([None], 1, "reason=invalid_response"),
    (None, 1, "reason=invalid_response"),
    ({"symbol": "EXAMPLE.PA"}, 1, "reason=invalid_response"),
    (302, 1, "HTTP 302"),
    (401, 1, "HTTP 401"),
    (500, 1, "HTTP 500"),
    (requests.Timeout("sensitive-provider-detail"), 1, "reason=transport"),
    (ValueError("sensitive-provider-detail"), 1, "reason=invalid_response"),
])
def test_security_lookup_from_real_buy(settings, monkeypatch, caplog, items, expected, reason):
    monkeypatch.setenv("GHOST_TOKEN", "offline-bearer")
    monkeypatch.setattr(paperless, "document_ids", lambda _: [123])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"original")
    monkeypatch.setattr(notices, "extract_text", lambda _: FIXTURE.read_text())

    def get(url, **kwargs):
        if url.endswith("/api/v1/account"):
            return Mock(status_code=200, json=lambda: {"accounts": [
                {"id": "target", "name": "Example PEA"}]})
        if url.endswith("/api/v1/activities"):
            return Mock(status_code=200, content=b'{"activities": [], "count": 0}')
        assert url == "http://ghostfolio.test/api/v1/symbol/lookup"
        assert kwargs["params"] == {"query": "FR0000120271"}
        assert kwargs["headers"] == {"Authorization": "Bearer offline-bearer"}
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == (10, 60)
        if isinstance(items, requests.RequestException):
            raise items
        if isinstance(items, ValueError):
            return Mock(status_code=200, json=Mock(side_effect=items))
        if isinstance(items, int):
            return Mock(status_code=items, json=Mock(side_effect=AssertionError("read error body")))
        return Mock(status_code=200, json=lambda: {"items": items})

    request = Mock(side_effect=get)
    monkeypatch.setattr(requests, "get", request)
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected POST")))
    with caplog.at_level(logging.INFO):
        assert app.main() == expected
    assert request.call_count == 3
    assert "sensitive-provider-detail" not in caplog.text
    assert "offline-bearer" not in caplog.text
    if reason is None:
        assert "Security lookup failed" not in caplog.text
    else:
        assert f"Security lookup failed isin=FR0000120271 {reason}" in caplog.text
    if expected:
        assert "unresolved_security" in caplog.text
        assert "FR0000120271: <yahoo ticker>" in caplog.text
        assert "type=BUY" not in caplog.text
    else:
        assert "type=BUY symbol=EXAMPLE.PA" in caplog.text
        assert "unresolved_security" not in caplog.text


def test_unresolved_isins_keep_mapped_rows_and_report_each_isin_once(settings, monkeypatch, caplog, tmp_path):
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text("symbol_mapping:\n  FR0000000002: VERIFIED.PA\n")
    monkeypatch.setenv("MAPPING_FILE", str(mapping))
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1, 2, 3, 4])
    monkeypatch.setattr(paperless, "original_pdf", lambda _, doc: str(doc).encode())
    monkeypatch.setattr(notices, "extract_text", lambda pdf: FIXTURE.read_text().replace(
        "FR0000120271", {b"1": "FR0000120271", b"2": "FR0000000010",
                         b"3": "FR0000000002", b"4": "FR0000120271"}[pdf]))
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    get = Mock(return_value=Mock(status_code=200, json=lambda: {"items": []}))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected POST")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert get.call_count == 2
    assert {c.kwargs["params"]["query"] for c in get.call_args_list} == {
        "FR0000120271", "FR0000000010"}
    errors = [r.message for r in caplog.records if "unresolved_security" in r.message]
    assert len(errors) == 2
    assert all(f"{isin}: <yahoo ticker>" in caplog.text for isin in (
        "FR0000120271", "FR0000000010"))
    assert "type=BUY symbol=VERIFIED.PA" in caplog.text
    assert "simulated=1" in caplog.text
    assert mapping.read_text() == "symbol_mapping:\n  FR0000000002: VERIFIED.PA\n"


@pytest.mark.parametrize("bad_first", [True, False])
@pytest.mark.parametrize("failure", ["parse", "extract", "amount", "unknown-field", "not-notice"])
def test_bad_document_keeps_readable_preview(settings, monkeypatch, caplog, bad_first, failure):
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1, 2] if bad_first else [2, 1])
    monkeypatch.setattr(paperless, "original_pdf", lambda _, doc: str(doc).encode())

    def extract(pdf):
        text = FIXTURE.read_text()
        if pdf == b"2":
            return text
        if failure == "extract":
            raise RuntimeError("notice_unreadable")
        if failure == "unknown-field":
            return text + "\nTAXE : 0.01\n"
        if failure == "not-notice":
            return "This document is not an operation notice."
        return text.replace("COMPTE", "MISSING") if failure == "parse" else text.replace("103.00", "103.01")

    monkeypatch.setattr(notices, "extract_text", extract)
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected HTTP")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert "type=BUY" in caplog.text
    assert "simulated=1" in caplog.text
    assert "unreadable_notices=1" in caplog.text
    code = "amount_check_failed" if failure == "amount" else "notice_unreadable"
    assert f"{code} document=1" in caplog.text


@pytest.mark.parametrize("failure", ["half-even-gross", "missing-brokerage-evidence"])
def test_rejected_cent_or_brokerage_evidence_blocks_all_writes(settings, monkeypatch, caplog, failure):
    monkeypatch.setenv("DRY_RUN", "0")
    if failure == "half-even-gross":
        bad = (FIXTURE.parent / "pdf_buy_half_cent.txt").read_text()
        bad = bad.replace("37.01", "37.00").replace("37.11", "37.10")
    else:
        bad = (FIXTURE.parent / "pdf_buy_no_brokerage.txt").read_text()
        bad = bad.replace("37.02\n", "37.03\n", 1)
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1, 2])
    monkeypatch.setattr(paperless, "original_pdf", lambda _, doc: str(doc).encode())
    monkeypatch.setattr(notices, "extract_text", lambda pdf: bad if pdf == b"1" else FIXTURE.read_text())
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected write")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert "amount_check_failed document=1" in caplog.text
    assert "created=0" in caplog.text
    assert "unreadable_notices=1" in caplog.text
    requests.post.assert_not_called()


@pytest.mark.parametrize("documents,other_account,expected", [
    ([], False, 0), ([1], True, 0), ([1], False, 1),
])
def test_no_matching_notice_avoids_target_reads(settings, monkeypatch, caplog, documents, other_account, expected):
    monkeypatch.setattr(paperless, "document_ids", lambda _: documents)
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"original")
    text = FIXTURE.read_text().replace("TEST ACCOUNT", "OTHER ACCOUNT") if other_account else "not a notice"
    monkeypatch.setattr(notices, "extract_text", lambda _: text)
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected HTTP")))
    with caplog.at_level(logging.INFO):
        assert app.main() == expected
    assert "Summary: simulated=0" in caplog.text


def test_account_name_requires_exact_unique_match(settings, monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"accounts": [{"id": "a", "name": "Example PEA"},
                                               {"id": "b", "name": "Example PEA"}]}
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(RuntimeError, match="invalid_configuration GHOST_ACCOUNT_NAME"):
        ghostfolio.find_account(settings, "offline")
    response.json.return_value["accounts"].pop()
    assert ghostfolio.find_account(settings, "offline") == "a"
    assert get.call_args.kwargs["allow_redirects"] is False


@pytest.mark.parametrize("account", [
    {"isExcluded": True},
    {"tags": [{"id": next(iter(ghostfolio.INACTIVE_TAGS))}]},
])
def test_excluded_or_inactive_target_account_is_refused(settings, monkeypatch, account):
    response = Mock(status_code=200)
    response.json.return_value = {"accounts": [{"id": "a", "name": "Example PEA", **account}]}
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    with pytest.raises(RuntimeError, match="invalid_configuration GHOST_ACCOUNT_NAME"):
        ghostfolio.find_account(settings, "offline")


def test_paperless_reads_original_and_ignores_response_url(settings, monkeypatch):
    first, second, filename, original = (Mock(status_code=200) for _ in range(4))
    first.json.return_value = {"count": 2, "next": "http://untrusted.test/?page=2",
                              "results": [{"id": 11}]}
    second.json.return_value = {"count": 2, "next": None, "results": [{"id": 12}]}
    filename.json.return_value = {"count": 0, "next": None, "results": []}
    original.content = b"%PDF-offline"
    get = Mock(side_effect=[first, second, filename, original])
    monkeypatch.setattr(requests, "get", get)
    assert paperless.document_ids(settings) == [11, 12]
    assert paperless.original_pdf(settings, 11) == original.content
    calls = get.call_args_list
    assert all(call.args[0].startswith(settings.paperless_url + "/api/") for call in calls)
    assert all(call.kwargs["allow_redirects"] is False for call in calls)
    assert json.loads(calls[0].kwargs["params"]["custom_field_query"]) == ["Source", "exact", "Bourse Direct"]
    assert calls[1].kwargs["params"]["page"] == 2
    assert calls[2].kwargs["params"] == {
        "original_filename__istartswith": "BourseDirect_", "page": 1,
    }
    assert calls[3].kwargs["params"] == {"original": "true"}


def test_paperless_filename_without_source_stops_before_pdf(settings, monkeypatch):
    labelled = Mock(status_code=200)
    labelled.json.return_value = {"count": 0, "next": None, "results": []}
    missing = Mock(status_code=200)
    missing.json.return_value = {
        "count": 1, "next": None,
        "results": [{"id": 99, "original_file_name": "BourseDirect_missing.pdf"}],
    }
    get = Mock(side_effect=[labelled, missing])
    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(RuntimeError, match="^source_field_missing$"):
        paperless.document_ids(settings)
    assert len(get.call_args_list) == 2


def test_real_import_posts_whitelisted_activity_and_confirms_exact_readback(settings, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    settings = config.load()
    activity = Activity("target", "EXAMPLE.PA", "2025-02-03T00:00:00+00:00", Decimal("4"), Decimal("25.50"), Decimal("1"), "BD#v3#TESTACCOUNT:BUY:proof")
    row = {"id": "created", "accountId": "target", "comment": activity.comment, "type": "BUY", "date": activity.date,
           "quantity": 4, "unitPrice": 25.5, "fee": 1, "currency": "EUR",
           "assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "currency": "EUR"}}
    response = Mock(status_code=201)
    read = Mock(status_code=200, content=json.dumps({"count": 1, "activities": [row]}).encode())
    monkeypatch.setattr(requests, "post", Mock(return_value=response))
    monkeypatch.setattr(requests, "get", Mock(return_value=read))
    monkeypatch.setattr(ghostfolio.time, "sleep", lambda _: None)
    ghostfolio.import_activities(settings, "offline", [activity])
    sent = json.loads(requests.post.call_args.kwargs["data"])["activities"]
    assert sent[0]["comment"] == activity.comment
    assert sent[0]["quantity"] == 4 and sent[0]["unitPrice"] == 25.50
    assert requests.post.call_args.kwargs["headers"]["Content-Type"] == "application/json"
    assert requests.get.call_args.args == ("http://ghostfolio.test/api/v1/activities",)


def test_real_import_refuses_missing_readback_without_resend(settings, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    settings = config.load()
    activity = Activity("target", "EXAMPLE.PA", "2025-02-03T00:00:00+00:00", Decimal("4"), Decimal("25.50"), Decimal("1"), "BD#v3#TESTACCOUNT:BUY:proof")
    monkeypatch.setattr(requests, "post", Mock(return_value=Mock(status_code=201)))
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=200, content=b'{"count":0,"activities":[]}')))
    monkeypatch.setattr(ghostfolio.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="^import_unconfirmed$"):
        ghostfolio.import_activities(settings, "offline", [activity])
    assert requests.post.call_count == 1


@pytest.mark.parametrize("outcome", ["timeout", "http_error", "duplicates", "changed", "failed_read"])
def test_import_confirmation_handles_uncertain_results(settings, monkeypatch, outcome):
    activity = Activity("target", "EXAMPLE.PA", "2025-02-03T00:00:00+00:00", Decimal("4"), Decimal("25.50"), Decimal("1"), "BD#v3#TESTACCOUNT:BUY:proof")
    row = {"id": "created", "accountId": "target", "comment": activity.comment, "type": "BUY", "date": activity.date,
           "quantity": 4, "unitPrice": 25.5, "fee": 1, "currency": "EUR",
           "assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "currency": "EUR"}}
    rows = [row, {**row, "id": "copy"}] if outcome == "duplicates" else [row]
    if outcome == "changed":
        row["quantity"] = 5
    post = Mock(side_effect=requests.Timeout()) if outcome == "timeout" else Mock(return_value=Mock(status_code=500 if outcome == "http_error" else 201))
    get = Mock(side_effect=requests.ConnectionError()) if outcome == "failed_read" else Mock(return_value=Mock(status_code=200, content=json.dumps({"count": len(rows), "activities": rows}).encode()))
    sleep = Mock()
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(ghostfolio.time, "sleep", sleep)
    if outcome in ("timeout", "http_error"):
        ghostfolio.import_activities(settings, "offline", [activity])
        sleep.assert_called_once_with(5)
    else:
        with pytest.raises(RuntimeError, match="^import_unconfirmed$"):
            ghostfolio.import_activities(settings, "offline", [activity])
    post.assert_called_once()
    get.assert_called_once()


@pytest.mark.parametrize("mode", ["success", "mixed", "unreadable", "unconfirmed"])
def test_real_notice_import_summary_and_exit(settings, monkeypatch, caplog, mode):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1, 2] if mode in ("mixed", "unreadable") else [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda _, doc: str(doc).encode())
    monkeypatch.setattr(notices, "extract_text", lambda pdf: (
        "invalid notice" if mode == "unreadable" and pdf == b"2" else
        FIXTURE.read_text().replace("FR0000120271", "FR0000000002") if pdf == b"2" else FIXTURE.read_text()))
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: None)
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000120271": "EXAMPLE.PA"})
    persisted = []

    def post(*args, **kwargs):
        for activity in json.loads(kwargs["data"])["activities"]:
            persisted.append({**activity, "id": "created", "assetProfile": {
                "symbol": activity["symbol"], "dataSource": "YAHOO", "currency": "EUR"}})
        return Mock(status_code=201)

    def get(*args, **kwargs):
        rows = [] if mode == "unconfirmed" else persisted
        return Mock(status_code=200, content=json.dumps({"count": len(rows), "activities": rows}).encode())

    monkeypatch.setattr(requests, "post", Mock(side_effect=post))
    monkeypatch.setattr(requests, "get", Mock(side_effect=get))
    with caplog.at_level(logging.INFO):
        assert app.main() == (0 if mode == "success" else 1)
    assert "[DRY RUN]" not in caplog.text
    assert "created=0" in caplog.text if mode in ("unconfirmed", "unreadable") else "created=1" in caplog.text
    assert sum("Summary:" in record.message for record in caplog.records) == 1
    if mode == "unreadable":
        requests.post.assert_not_called()
    else:
        requests.post.assert_called_once()


@pytest.mark.parametrize("other_account", [False, True])
def test_zero_brokerage_information_follows_account_filter(settings, monkeypatch, caplog, other_account):
    text = (FIXTURE.parent / "pdf_buy_no_brokerage.txt").read_text()
    if other_account:
        text = text.replace("TEST ACCOUNT", "OTHER ACCOUNT")
    monkeypatch.setattr(paperless, "document_ids", lambda _: [123])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"original")
    monkeypatch.setattr(notices, "extract_text", lambda _: text)
    monkeypatch.setattr(sync, "load_mapping", lambda _: {"FR0000000002": "EXAMPLE.PA"})
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected HTTP")))
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected write")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 0
    messages = [r.message for r in caplog.records if "brokerage_zero_inferred" in r.message]
    assert messages == ([] if other_account else ["brokerage_zero_inferred document=123 rows=1"])
    requests.post.assert_not_called()

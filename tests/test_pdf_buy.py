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
from ghostfolio_boursedirect_sync.models import ActivityIndex

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
    assert len(notice.buys) == 1
    buy = notice.buys[0]
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
    monkeypatch.setenv("APPRISE_URLS", "invalid-but-ignored-in-simulation")
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
    monkeypatch.setattr(requests, "post", Mock(side_effect=AssertionError("unexpected POST")))
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("unexpected GET")))
    assert app.main() == 1


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

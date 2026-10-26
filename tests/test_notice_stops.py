"""Stops use text extracted from the retained July 9 notice PDF.

Account, ISINs and security names are anonymized. The real coupon and division
have different ISINs. Same-ISIN and unknown-label cases are explicit alterations.
No test claims real Paperless/Ghostfolio acceptance.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from ghostfolio_boursedirect_sync import notices

FIXTURES = Path(__file__).parent / "fixtures"


def corporate_text():
    return (FIXTURES / "pdf_division_coupon.txt").read_text()


def test_real_division_rows_do_not_hide_the_independent_coupon():
    notice = notices.parse_text(corporate_text())
    coupon, = notice.trades
    assert coupon.type == "DIVIDEND"
    assert (coupon.quantity, coupon.unit_price, coupon.fee) == (Decimal(1), Decimal(10), Decimal(0))
    assert [(row.code, row.isin) for row in notice.stops] == [
        ("share_count_change", "FR0000000002"), ("share_count_change", "FR0000000002")]


def run_notices(monkeypatch, texts, done=(), *, dry_run=True):
    from ghostfolio_boursedirect_sync import app, config, ghostfolio, paperless
    from ghostfolio_boursedirect_sync.models import ActivityIndex, Settings

    settings = Settings("http://ghostfolio.test", "Example PEA", "TESTACCOUNT",
                        "http://paperless.test", "offline", "offline", None, "", "done & checked", dry_run)
    monkeypatch.setattr(config, "load", lambda: settings)
    monkeypatch.setattr(paperless, "document_ids", lambda _: list(texts))
    monkeypatch.setattr(paperless, "original_pdf", lambda _, doc: str(doc).encode())
    monkeypatch.setattr(notices, "extract_text", lambda pdf: texts[int(pdf)])
    monkeypatch.setattr(paperless, "done_document_ids", lambda _: set(done))
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    resolved, written = [], []

    def lookup(*args):
        resolved.append(args[-1])
        return "EXAMPLE.PA"

    monkeypatch.setattr(ghostfolio, "lookup_symbol", lookup)
    monkeypatch.setattr(ghostfolio, "import_activities", lambda _, token, rows: written.extend(rows))
    return app.main(), resolved, written


def test_same_isin_division_blocks_coupon_even_when_its_document_is_read_last(monkeypatch, caplog):
    import logging

    text = corporate_text().replace("FR0000000002", "FR0000000001")
    coupon, divisions = text.split("   09/07/2026           DIVISION", 1)
    divisions = "  COMPTE N° TEST ACCOUNTEUR PEA\n   09/07/2026           DIVISION" + divisions
    with caplog.at_level(logging.INFO):
        code, resolved, written = run_notices(monkeypatch, {1: coupon, 2: divisions})
    assert code == 1
    assert resolved == written == []
    assert "share_count_change document=2" in caplog.text
    assert "type=DIVIDEND" not in caplog.text


def test_done_tag_clears_only_its_documents_stops_and_keeps_coupon(monkeypatch, caplog):
    import logging

    text = corporate_text().replace("FR0000000002", "FR0000000001")
    with caplog.at_level(logging.INFO):
        code, resolved, written = run_notices(monkeypatch, {1: text}, done={1})
    assert code == 0
    assert resolved == ["FR0000000001"] and written == []
    assert "share_count_change" not in caplog.text
    assert "type=DIVIDEND" in caplog.text
    caplog.clear()
    with caplog.at_level(logging.INFO):
        code, resolved, written = run_notices(monkeypatch, {1: text, 2: text}, done={1})
    assert code == 1 and resolved == written == []
    assert "share_count_change document=2" in caplog.text
    assert "share_count_change document=1" not in caplog.text
    assert "type=DIVIDEND" not in caplog.text


def test_unknown_without_isin_reports_failure_and_keeps_independent_rows(monkeypatch, caplog):
    import logging

    text = corporate_text().replace("DIVISION", "PRIVATE UNKNOWN LABEL").replace("FR0000000002", "")
    with caplog.at_level(logging.INFO):
        code, resolved, written = run_notices(monkeypatch, {1: text}, dry_run=False)
    assert code == 1
    assert resolved == ["FR0000000001"]
    assert len(written) == 1 and written[0].type == "DIVIDEND"
    assert "unknown_operation document=1" in caplog.text
    assert "PRIVATE UNKNOWN LABEL" not in caplog.text
    assert "created=1" in caplog.text


def test_stop_in_other_account_cannot_block_selected_accounts_security(monkeypatch, caplog):
    import logging

    text = corporate_text().replace("FR0000000002", "FR0000000001")
    coupon, divisions = text.split("   09/07/2026           DIVISION", 1)
    divisions = "  COMPTE N° OTHER ACCOUNTEUR PEA\n   09/07/2026           DIVISION" + divisions
    with caplog.at_level(logging.INFO):
        code, resolved, _ = run_notices(monkeypatch, {1: coupon, 2: divisions})
    assert code == 0 and resolved == ["FR0000000001"]
    assert "share_count_change" not in caplog.text
    assert "other_account_notices=1" in caplog.text


def test_done_tag_does_not_clear_unknown_fields(monkeypatch, caplog):
    code, resolved, written = run_notices(monkeypatch, {
        1: corporate_text().replace("QUANTITE", "UNKNOWN FIELD")}, done={1}, dry_run=False)
    assert code == 1 and resolved == written == []
    assert "notice_unreadable" in caplog.text


@pytest.mark.parametrize("fixture,old,new,custody", [
    ("pdf_sell_custody.txt", "VENTE ETRANGER", "VENTE INCONNUE", 1),
    ("pdf_coupon.txt", "COUPONS", "COUPONS ETRANGER", 0),
])
def test_unrecognized_operation_is_a_stop_not_a_trade(fixture, old, new, custody):
    text = (FIXTURES / fixture).read_text().replace(old, new)
    notice = notices.parse_text(text)
    assert notice.trades == () and notice.custody_fees == custody
    assert [(s.code, s.isin) for s in notice.stops] == [("unknown_operation", "FR0000000002")]


def test_done_tag_query_uses_exact_configured_name_and_complete_pages(monkeypatch):
    import json
    from unittest.mock import Mock

    import requests

    from ghostfolio_boursedirect_sync import paperless
    from ghostfolio_boursedirect_sync.models import Settings

    settings = Settings("http://ghostfolio.test", "Example PEA", "TESTACCOUNT",
                        "http://paperless.test", "offline", "offline", None, "", "done & checked", True)
    get = Mock(side_effect=[Mock(status_code=200, json=lambda: {
        "count": 2, "next": None, "results": [{"id": 6, "name": "DONE & CHECKED"},
                                                  {"id": 7, "name": "done & checked"}]}),
        Mock(status_code=200, json=lambda: {
        "count": 2, "next": "http://untrusted.test/", "results": [{"id": 1}]}),
        Mock(status_code=200, json=lambda: {"count": 2, "next": None, "results": [{"id": 2}]})])
    monkeypatch.setattr(requests, "get", get)
    assert paperless.done_document_ids(settings) == {1, 2}
    assert get.call_args_list[0].args == ("http://paperless.test/api/tags/",)
    assert get.call_args_list[0].kwargs["params"] == {"name__iexact": "done & checked", "page": 1}
    for page, call in enumerate(get.call_args_list[1:], 1):
        assert call.args == ("http://paperless.test/api/documents/",)
        assert call.kwargs["params"] == {
            "custom_field_query": json.dumps(["Source", "exact", "Bourse Direct"]),
            "tags__id__all": "7", "page": page}
        assert call.kwargs["allow_redirects"] is False


def test_cleared_coupon_cannot_reimport_a_legacy_dividend_three_days_away():
    from ghostfolio_boursedirect_sync import ghostfolio, sync

    notice = notices.parse_text(corporate_text())
    coupon = sync.activity(notice.trades[0], {"FR0000000001": "EXAMPLE.PA"}, "target", "TESTACCOUNT",
                           sync.notice_namespace(notice), 0)
    ledger = ghostfolio.index_existing_activities({"count": 1, "activities": [{
        "id": "legacy", "accountId": "target", "date": "2026-07-12T00:00:00Z",
        "type": "DIVIDEND", "quantity": Decimal(2), "unitPrice": Decimal(5), "fee": 0,
        "currency": "EUR", "comment": "", "assetProfile": {
            "symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000001"}}]})
    selected = sync.select_account_activities([coupon], ledger)
    assert selected.activities == ()
    assert selected.duplicates == 1 and selected.errors == ()


def test_unknown_operation_with_isin_blocks_across_notices(monkeypatch, caplog):
    import logging

    text = corporate_text().replace("FR0000000002", "FR0000000001").replace("DIVISION", "UNSEEN OPERATION")
    coupon, unknown = text.split("   09/07/2026           UNSEEN OPERATION", 1)
    unknown = "  COMPTE N° TEST ACCOUNTEUR PEA\n   09/07/2026           UNSEEN OPERATION" + unknown
    for documents in ({1: coupon, 2: unknown}, {2: unknown, 1: coupon}):
        caplog.clear()
        with caplog.at_level(logging.INFO):
            code, resolved, written = run_notices(monkeypatch, documents, dry_run=False)
        assert code == 1 and resolved == written == []
        assert "unknown_operation document=2" in caplog.text
        assert "type=DIVIDEND" not in caplog.text


def test_untagged_real_notice_keeps_other_security_importable(monkeypatch, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        code, resolved, written = run_notices(monkeypatch, {1: corporate_text()}, dry_run=False)
    assert code == 1 and resolved == ["FR0000000001"]
    assert len(written) == 1 and written[0].type == "DIVIDEND"
    assert "share_count_change document=1" in caplog.text
    assert "created=1" in caplog.text


def test_done_unknown_rows_do_not_suppress_the_valid_coupon(monkeypatch, caplog):
    import logging

    text = corporate_text().replace("DIVISION", "UNSEEN OPERATION")
    with caplog.at_level(logging.INFO):
        code, resolved, _ = run_notices(monkeypatch, {1: text}, done={1})
    assert code == 0 and resolved == ["FR0000000001"]
    assert "unknown_operation" not in caplog.text
    assert "type=DIVIDEND" in caplog.text


def test_unavailable_done_tag_evidence_stops_before_target_access(monkeypatch, caplog):
    from unittest.mock import Mock

    from ghostfolio_boursedirect_sync import app, config, ghostfolio, paperless
    from ghostfolio_boursedirect_sync.models import Settings

    settings = Settings("http://ghostfolio.test", "Example PEA", "TESTACCOUNT",
                        "http://paperless.test", "offline", "offline", None, "", "done", False)
    monkeypatch.setattr(config, "load", lambda: settings)
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"offline PDF boundary")
    monkeypatch.setattr(notices, "extract_text", lambda _: corporate_text())
    monkeypatch.setattr(paperless, "done_document_ids", Mock(side_effect=RuntimeError("paperless_unreachable")))
    target = Mock(side_effect=AssertionError("target must not be accessed"))
    monkeypatch.setattr(ghostfolio, "exchange_token", target)
    assert app.main() == 1
    assert "paperless_unreachable" in caplog.text
    target.assert_not_called()


def test_real_attribution_is_an_unknown_operation_with_a_security():
    # June 8 retained PDF: identifiers and security name anonymized, label unchanged.
    text = (FIXTURES / "pdf_unknown_attribution.txt").read_text()
    notice = notices.parse_text(text)
    assert notice.trades == ()
    assert [(s.code, s.isin) for s in notice.stops] == [("unknown_operation", "FR0000000002")]


def test_single_space_before_division_isin_still_blocks_the_security(monkeypatch, caplog):
    text = corporate_text().replace("FR0000000002", "FR0000000001")
    text = text.replace("DIVISION                             FR", "DIVISION FR")
    notice = notices.parse_text(text)
    assert [(s.code, s.isin) for s in notice.stops] == [
        ("share_count_change", "FR0000000001"), ("share_count_change", "FR0000000001")]
    code, resolved, written = run_notices(monkeypatch, {1: text}, dry_run=False)
    assert code == 1 and resolved == written == []


def test_usd_dividend_is_not_an_exact_match_for_a_eur_coupon():
    from ghostfolio_boursedirect_sync import ghostfolio, sync

    notice = notices.parse_text(corporate_text())
    coupon = sync.activity(notice.trades[0], {"FR0000000001": "EXAMPLE.PA"}, "target", "TESTACCOUNT",
                           sync.notice_namespace(notice), 0)
    ledger = ghostfolio.index_existing_activities({"count": 1, "activities": [{
        "id": "usd", "accountId": "target", "date": coupon.date,
        "type": "DIVIDEND", "quantity": 1, "unitPrice": 10, "fee": 0,
        "currency": "USD", "comment": "", "assetProfile": {
            "symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000001"}}]})
    selected = sync.select_account_activities([coupon], ledger)
    assert selected.activities == ()
    assert selected.duplicates == 0 and selected.errors == ("possible_duplicate",)

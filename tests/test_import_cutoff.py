"""Creation boundary: real anonymized notice text and explicit derived cases."""

import logging
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_pdf_buy import settings as settings

from ghostfolio_boursedirect_sync import app, config, ghostfolio, notices, paperless

FIXTURES = Path(__file__).parent / "fixtures"


def run_cycle(settings, monkeypatch, documents, *, cutoff=date(2026, 10, 1), **options):
    configured = replace(settings, import_create_from=cutoff, **options)
    monkeypatch.setattr(config, "load", lambda: configured)
    monkeypatch.setattr(paperless, "document_ids", lambda _: list(documents))
    monkeypatch.setattr(paperless, "original_pdf", lambda _, doc: str(doc).encode())
    monkeypatch.setattr(notices, "extract_text", lambda pdf: documents[int(pdf)])
    monkeypatch.setattr(paperless, "done_document_ids", lambda _: set())
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities({"count": 0, "activities": []}))
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda _, __, isin: {"FR0010342592": "LQQ.PA", "FR0014010HV4": "LWLD.PA"}.get(isin, "EXAMPLE.PA"))
    post = Mock()
    put = Mock(side_effect=AssertionError("no correction authorized"))
    monkeypatch.setattr(ghostfolio, "import_activities", post)
    monkeypatch.setattr(ghostfolio, "update_reviewed_activity", put)
    return post, put


@pytest.mark.parametrize("value,expected", [(None, None), ("", None), ("2026-10-01", date(2026, 10, 1))])
def test_optional_creation_date(settings, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("IMPORT_CREATE_FROM", raising=False)
    else:
        monkeypatch.setenv("IMPORT_CREATE_FROM", value)
    assert config.load().import_create_from == expected


@pytest.mark.parametrize("value", ["2026-02-30", "20261001", "2026-W40-4", "2026-10-01T00:00:00Z", " 2026-10-01", "2026-1-1"])
def test_invalid_creation_date(settings, monkeypatch, value):
    monkeypatch.setenv("IMPORT_CREATE_FROM", value)
    with pytest.raises(RuntimeError, match="^invalid_configuration IMPORT_CREATE_FROM$"):
        config.load()


@pytest.mark.parametrize("dry_run", [True, False])
def test_real_recent_buys_remain_eligible_but_old_buy_is_never_created(settings, monkeypatch, caplog, dry_run):
    post, put = run_cycle(settings, monkeypatch, {
        1: (FIXTURES / "pdf_buy.txt").read_text(),
        2: (FIXTURES / "pdf_cutoff_buys.txt").read_text(),
    }, dry_run=dry_run)
    with caplog.at_level(logging.INFO):
        assert app.run_sync(set()) == 0
    assert "excluded_rows=1" in caplog.text
    assert "excluded_documents=1" in caplog.text
    if dry_run:
        assert "simulated=2" in caplog.text
        post.assert_not_called()
    else:
        rows = [call.args[2][0] for call in post.call_args_list]
        assert [(r.symbol, str(r.quantity), str(r.unit_price), str(r.fee)) for r in rows] == [
            ("LQQ.PA", "120", "8.035", "1.90"), ("LWLD.PA", "180", "5.144", "1.90")]
    put.assert_not_called()


@pytest.mark.parametrize("offset,simulated", [("30/09/2026", 0), ("01/10/2026", 1), ("02/10/2026", 1)])
def test_printed_row_date_controls_boundary_not_document_date(settings, monkeypatch, caplog, offset, simulated):
    source = (FIXTURES / "pdf_buy.txt").read_text().replace("03/02/2025", offset)
    run_cycle(settings, monkeypatch, {1: source})
    with caplog.at_level(logging.INFO):
        assert app.run_sync(set()) == 0
    assert f"simulated={simulated}" in caplog.text


def test_historical_division_does_not_block_recent_buy_but_coverage_keeps_it(settings, monkeypatch, caplog):
    old = (FIXTURES / "pdf_division_coupon.txt").read_text().replace("FR0000000002", "FR0010342592")
    docs = {1: old, 2: (FIXTURES / "pdf_cutoff_buys.txt").read_text()}
    run_cycle(settings, monkeypatch, docs)
    with caplog.at_level(logging.INFO):
        codes = set()
        assert app.run_sync(codes) == 0
    assert codes == set()
    assert "simulated=2" in caplog.text
    caplog.clear()
    run_cycle(settings, monkeypatch, docs, notice_coverage=True)
    with caplog.at_level(logging.INFO):
        app.run_sync(set())
    assert "unsupported=share_count_change" in caplog.text
    assert "absent supported" in caplog.text


@pytest.mark.parametrize("created,exit_code", [("2026-08-06", 0), ("2026-10-01", 1),
    ("2026-11-06", 1), (None, 1), ("bad", 1), ("2026-02-30", 1), ("20260806", 1)])
def test_real_unreadable_coupon_requires_proved_older_document_date(settings, monkeypatch, caplog, created, exit_code):
    import requests

    docs = {1: (FIXTURES / "pdf_cutoff_unreadable.txt").read_text(),
            2: (FIXTURES / "pdf_cutoff_buys.txt").read_text()}
    post, put = run_cycle(settings, monkeypatch, docs, dry_run=False)
    def get(url, **kwargs):
        assert url == "http://paperless.test/api/documents/1/"
        assert kwargs["allow_redirects"] is False
        return Mock(status_code=200, json=lambda: {"id": 1, "created": created, "added": "2025-01-01",
                                                    "original_file_name": "BourseDirect_PEA_2025-01-01.pdf"})
    monkeypatch.setattr(requests, "get", get)
    with caplog.at_level(logging.INFO):
        codes = set()
        assert app.run_sync(codes) == exit_code
    assert post.call_count == (2 if exit_code == 0 else 0)
    assert codes == (set() if exit_code == 0 else {"notice_unreadable"})
    if not exit_code:
        assert "Historical unreadable notice: document=1" in caplog.text
        assert "excluded_documents=1" in caplog.text
    put.assert_not_called()


@pytest.mark.parametrize("filename", ["pdf_cutoff_alias_coupon.txt", "pdf_cutoff_old_notice.txt"])
def test_real_historical_false_creation_is_excluded_even_without_a_match(settings, monkeypatch, caplog, filename):
    # Real historical notices from the false-creation investigation. An empty
    # ledger is an explicit derived case: exclusion must not depend on a match.
    run_cycle(settings, monkeypatch, {1: (FIXTURES / filename).read_text(),
                                    2: (FIXTURES / "pdf_cutoff_buys.txt").read_text()})
    with caplog.at_level(logging.INFO):
        codes = set()
        assert app.run_sync(codes) == 0
    assert codes == set()
    assert "simulated=2" in caplog.text
    assert "type=DIVIDEND" not in caplog.text


def test_historical_manual_fee_stays_in_review_without_becoming_a_creation(settings, monkeypatch, tmp_path):
    import yaml
    from test_activity_review import sample

    row, _, _ = sample()
    row.update(comment="manual", fee=9)
    path = tmp_path / "review.yaml"
    run_cycle(settings, monkeypatch, {1: (FIXTURES / "pdf_buy.txt").read_text()},
              activity_review_file=str(path))
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities({"count": 1, "activities": [row]}))
    codes = set()
    assert app.run_sync(codes) == 0
    data = yaml.safe_load(path.read_text())
    assert data["activity_corrections"]
    assert any(p["operation fields"] == ["fee"] for p in data["activity_corrections"].values())


@pytest.mark.parametrize("status", [403, 500])
def test_unreadable_metadata_acquisition_failure_stops_all_writes(settings, monkeypatch, status):
    import requests

    post, _ = run_cycle(settings, monkeypatch, {1: (FIXTURES / "pdf_cutoff_unreadable.txt").read_text(),
                                             2: (FIXTURES / "pdf_cutoff_buys.txt").read_text()}, dry_run=False)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Mock(status_code=status))
    assert app.run_sync(set()) == 1
    post.assert_not_called()


def test_historical_unreadable_notice_remains_in_coverage(settings, monkeypatch, caplog):
    import requests

    post, put = run_cycle(settings, monkeypatch, {1: (FIXTURES / "pdf_cutoff_unreadable.txt").read_text(),
        2: (FIXTURES / "pdf_cutoff_buys.txt").read_text()}, dry_run=False, notice_coverage=True)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: Mock(status_code=200, json=lambda: {"id": 1, "created": "2026-08-06"}))
    with caplog.at_level(logging.INFO):
        assert app.run_sync(set()) == 0
    assert "'unreadable': 1" in caplog.text
    assert "incomplete=True" in caplog.text
    post.assert_not_called()
    put.assert_not_called()

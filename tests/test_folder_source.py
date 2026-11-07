"""Folder scenarios use anonymized retained text and explicit derived files."""

import hashlib
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_pdf_buy import settings as settings

from ghostfolio_boursedirect_sync import (
    app,
    config,
    folder,
    ghostfolio,
    notices,
    paperless,
)


def select_folder(monkeypatch, path):
    monkeypatch.setenv("NOTICE_DIR", str(path))
    monkeypatch.delenv("PAPERLESS_URL", raising=False)
    monkeypatch.delenv("PAPERLESS_TOKEN", raising=False)


def test_folder_without_paperless(settings, monkeypatch, tmp_path):
    select_folder(monkeypatch, tmp_path)
    selected = config.load()
    assert selected.notice_dir == str(tmp_path)
    assert selected.paperless_url == selected.paperless_token == ""


@pytest.mark.parametrize("source", ["mixed", "absent", "relative"])
def test_conflicting_absent_or_relative_source(settings, monkeypatch, tmp_path, source):
    if source == "mixed":
        monkeypatch.setenv("NOTICE_DIR", str(tmp_path))
    else:
        select_folder(monkeypatch, Path("relative") if source == "relative" else "")
    with pytest.raises(RuntimeError, match="^invalid_configuration"):
        config.load()

FIXTURES = Path(__file__).parent / "fixtures"


def folder_cycle(settings, monkeypatch, tmp_path, **options):
    source = tmp_path / "notices"
    source.mkdir(exist_ok=True)
    select_folder(monkeypatch, source)
    for key, value in options.items():
        monkeypatch.setenv(key, str(value))
    # Extraction is a system boundary. Anonymized text replaces PDF extraction.
    monkeypatch.setattr(notices, "extract_text", lambda pdf: pdf.decode())
    monkeypatch.setattr(paperless, "document_ids", Mock(side_effect=AssertionError("no Paperless")))
    monkeypatch.setattr(paperless, "done_document_ids", Mock(side_effect=AssertionError("no Paperless")))
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities({"count": 0, "activities": []}))
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
    post, put = Mock(), Mock()
    monkeypatch.setattr(ghostfolio, "import_activities", post)
    monkeypatch.setattr(ghostfolio, "update_reviewed_activity", put)
    return source, post, put


def test_folder_buy_simulation(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    original = (FIXTURES / "pdf_buy.txt").read_bytes()
    (source / "notice.PDF").write_bytes(original)
    (source / "ignored.txt").write_text("ignored")
    (source / "nested").mkdir()
    with caplog.at_level("DEBUG"):
        assert app.run_sync(set()) == 0
    assert "simulated=1" in caplog.text
    assert "source_files=1 distinct_documents=1 ignored_entries=2" in caplog.text
    assert "quantity=4 unitPrice=25.50 fee=1.00" in caplog.text
    assert "document=sha256:" in caplog.text
    assert (source / "notice.PDF").read_bytes() == original
    post.assert_not_called()
    put.assert_not_called()


@pytest.mark.parametrize("unsafe", ["symlink", "fifo", "empty", "oversize", "unreadable"])
def test_unsafe_pdf_blocks_all_financial_writes(settings, monkeypatch, tmp_path, caplog, unsafe):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0, NOTICE_COVERAGE=1)
    (source / "buy.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    bad = source / "bad.pdf"
    if unsafe == "symlink":
        bad.symlink_to(source / "buy.pdf")
    elif unsafe == "fifo":
        os.mkfifo(bad)
    elif unsafe == "oversize":
        with bad.open("wb") as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
    else:
        bad.write_bytes(b"" if unsafe == "empty" else b"secret")
        if unsafe == "unreadable":
            bad.chmod(0)
    codes = set()
    with caplog.at_level("INFO"):
        assert app.run_sync(codes) == 1
    assert "notice_unreadable" in codes
    assert "incomplete=True" in caplog.text
    assert "absent supported" in caplog.text
    post.assert_not_called()
    put.assert_not_called()


def test_missing_and_linked_source_refuse_before_destination(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    token = Mock(side_effect=AssertionError("no destination access"))
    monkeypatch.setattr(ghostfolio, "exchange_token", token)
    for path, code in [(source / "missing", "notice_source_unavailable"), (tmp_path / "link", "notice_unreadable")]:
        if code == "notice_unreadable":
            path.symlink_to(source, target_is_directory=True)
        monkeypatch.setenv("NOTICE_DIR", str(path))
        errors = set()
        assert app.run_sync(errors) == 1
        assert code in errors
    token.assert_not_called()
    post.assert_not_called()
    put.assert_not_called()


def test_selected_input_changed_before_dispatch_blocks_writes(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0)
    path = source / "buy.pdf"
    path.write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    def lookup(*_):
        path.write_bytes(path.read_bytes() + b"\n")
        return "EXAMPLE.PA"
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lookup)
    errors = set()
    assert app.run_sync(errors) == 1
    assert errors == {"notice_source_unavailable"}
    post.assert_not_called()
    put.assert_not_called()


def test_copy_rename_and_relocation_keep_one_event(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0)
    data = (FIXTURES / "pdf_buy.txt").read_bytes()
    (source / "a.pdf").write_bytes(data)
    (source / "copy.pdf").write_bytes(data)
    with caplog.at_level("DEBUG"):
        assert app.run_sync(set()) == 0
    event = post.call_args.args[2][0]
    assert (event.quantity, event.unit_price, event.fee) == (Decimal(4), Decimal("25.50"), Decimal("1.00"))
    assert "source_files=2 distinct_documents=1" in caplog.text
    (source / "a.pdf").rename(source / "renamed.pdf")
    new = tmp_path / "moved"
    source.rename(new)
    monkeypatch.setenv("NOTICE_DIR", str(new))
    row = {"id": "confirmed", "accountId": "target", "comment": event.comment, "type": "BUY", "date": event.date,
           "quantity": 4, "unitPrice": Decimal("25.50"), "fee": 1, "currency": "EUR",
           "assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO"}}
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities({"count": 1, "activities": [row]}))
    post.reset_mock()
    assert app.run_sync(set()) == 0
    post.assert_not_called()
    put.assert_not_called()


def test_folder_printed_cutoff_and_unknown_date_hold(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0, IMPORT_CREATE_FROM="2025-02-03")
    data = (FIXTURES / "pdf_buy.txt").read_text()
    (source / "future-2030.pdf").write_text(data.replace("03/02/2025", "02/02/2025"))
    boundary = source / "old-1900.pdf"
    boundary.write_text(data)
    os.utime(boundary, (0, 0))
    with caplog.at_level("INFO"):
        assert app.run_sync(set()) == 0
    assert post.call_count == 1
    assert "excluded_rows=1 excluded_documents=1" in caplog.text
    (source / "old-unreadable.pdf").write_text(data.replace("03/02/2025", "unknown"))
    post.reset_mock()
    errors = set()
    assert app.run_sync(errors) == 1
    assert "notice_unreadable" in errors
    post.assert_not_called()
    put.assert_not_called()


@pytest.mark.parametrize("renamed", [False, True])
def test_digest_waiver_clears_only_document_stop(settings, monkeypatch, tmp_path, caplog, renamed):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    data = (FIXTURES / "pdf_division_coupon.txt").read_bytes()
    path = source / "division.pdf"
    path.write_bytes(data)
    errors = set()
    assert app.run_sync(errors) == 1
    assert "share_count_change" in errors
    waiver = tmp_path / "waivers.txt"
    waiver.write_text("sha256:" + hashlib.sha256(data).hexdigest() + " share_count_change\n")
    monkeypatch.setenv("NOTICE_WAIVER_FILE", str(waiver))
    if renamed:
        path = path.rename(source / "renamed.pdf")
    with caplog.at_level("INFO"):
        assert app.run_sync(set()) == 0
    assert "simulated=1" in caplog.text
    path.write_bytes(data + b"\n")
    errors = set()
    with caplog.at_level("INFO"):
        assert app.run_sync(errors) == 1
    assert "share_count_change" in errors
    assert "unknown_waiver_digests=1" in caplog.text
    assert waiver.read_text().endswith(" share_count_change\n")
    post.assert_not_called()
    put.assert_not_called()


@pytest.mark.parametrize("bad", ["malformed", "duplicate", "uppercase", "tab", "unknown_code", "oversize", "nonutf8", "missing", "link", "directory", "inside", "relative", "review_alias", "review_companion"])
def test_invalid_waivers_fail_before_service_access(settings, monkeypatch, tmp_path, bad):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    waiver = tmp_path / "waivers.txt"
    valid = "sha256:" + "a" * 64 + " unknown_operation\n"
    data = {"malformed": "bad", "duplicate": valid * 2, "uppercase": valid.replace("a", "A"),
            "tab": valid.replace(" ", "\t"), "unknown_code": valid.replace("unknown_operation", "notice_unreadable"),
            "oversize": "\n" * 65537}.get(bad, valid)
    if bad == "inside":
        waiver = source / "waivers.txt"
    if bad != "missing":
        waiver.write_bytes(b"\xff" if bad == "nonutf8" else data.encode())
    if bad == "link":
        link = tmp_path / "linked.txt"
        link.symlink_to(waiver)
        waiver = link
    if bad == "directory":
        waiver = source
    if bad == "relative":
        waiver = Path("relative")
    if bad == "review_companion":
        review = tmp_path / "review.yaml"
        monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(review))
        waiver = waiver.rename(Path(str(review) + ".normal.required-actions.yaml"))
    if bad == "review_alias":
        review = tmp_path / "review.yaml"
        os.link(waiver, review)
        monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(review))
    monkeypatch.setenv("NOTICE_WAIVER_FILE", str(waiver))
    token = Mock(side_effect=AssertionError("no destination access"))
    monkeypatch.setattr(ghostfolio, "exchange_token", token)
    with pytest.raises(RuntimeError, match="^invalid_configuration NOTICE_WAIVER_FILE$"):
        config.load()
    token.assert_not_called()
    post.assert_not_called()
    put.assert_not_called()


def test_waiver_is_invalid_in_paperless_mode(settings, monkeypatch):
    monkeypatch.setenv("NOTICE_WAIVER_FILE", "/waivers.txt")
    with pytest.raises(RuntimeError, match="^invalid_configuration NOTICE_WAIVER_FILE$"):
        config.load()


def test_waiver_size_boundary_and_read_permissions(settings, monkeypatch, tmp_path):
    source, _, _ = folder_cycle(settings, monkeypatch, tmp_path)
    waiver = tmp_path / "waivers.txt"
    waiver.write_bytes(b"\n" * 65536)
    monkeypatch.setenv("NOTICE_WAIVER_FILE", str(waiver))
    assert config.load().notice_waivers == ()
    waiver.chmod(0)
    with pytest.raises(RuntimeError, match="invalid_configuration NOTICE_WAIVER_FILE"):
        config.load()


def test_exact_pdf_size_boundary_and_no_recursive_read(tmp_path):
    path = tmp_path / "limit.pdf"
    with path.open("wb") as stream:
        stream.truncate(20 * 1024 * 1024)
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "ignored.pdf").symlink_to("/unreachable")
    source = folder.acquire(str(tmp_path))
    assert source.files == 1 and source.ignored == 1
    assert len(source.documents[0].pdf) == 20 * 1024 * 1024


@pytest.mark.parametrize("code,label", [("share_count_change", "DIVISION"), ("unknown_operation", "INDEMNISATION")])
def test_waiver_is_local_and_other_stop_still_holds(settings, monkeypatch, tmp_path, caplog, code, label):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    data = (FIXTURES / "pdf_division_coupon.txt").read_bytes().replace(b"DIVISION", label.encode())
    (source / "waived.pdf").write_bytes(data)
    waiver = tmp_path / "waivers.txt"
    waiver.write_text("sha256:" + hashlib.sha256(data).hexdigest() + " " + code + "\n")
    monkeypatch.setenv("NOTICE_WAIVER_FILE", str(waiver))
    assert app.run_sync(set()) == 0
    (source / "unwaived.pdf").write_bytes(data + b"\n")
    errors = set()
    assert app.run_sync(errors) == 1
    assert code in errors
    post.assert_not_called()
    put.assert_not_called()


def test_review_output_cannot_overlap_folder(settings, monkeypatch, tmp_path):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0)
    original = (FIXTURES / "pdf_buy.txt").read_bytes()
    (source / "buy.pdf").write_bytes(original)
    source.chmod(0o700)
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(source / "review.yaml"))
    errors = set()
    assert app.run_sync(errors) == 1
    assert errors == {"review_unavailable"}
    assert sorted(p.name for p in source.iterdir()) == ["buy.pdf"]
    assert (source / "buy.pdf").read_bytes() == original
    post.assert_not_called()
    put.assert_not_called()


def test_folder_review_evidence_survives_rename_but_not_changed_bytes(settings, monkeypatch, tmp_path):
    from test_activity_review import sample

    from ghostfolio_boursedirect_sync import activity_review as review

    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    path = source / "buy.pdf"
    data = (FIXTURES / "pdf_buy.txt").read_bytes()
    path.write_bytes(data)
    row, event, _ = sample()
    def evidence():
        document = folder.acquire(str(source)).documents[0]
        return review.source_events([event], "TESTACCOUNT", {event.comment: [
            {"id": document.reference, "sha256": document.reference.removeprefix("sha256:")} ]})
    first, _ = review.refresh_proposals({}, evidence(), [row], {"TESTACCOUNT": "target"})
    next(iter(first.values()))["approve"] = "yes"
    path = path.rename(source / "renamed.pdf")
    same, _ = review.refresh_proposals(first, evidence(), [row], {"TESTACCOUNT": "target"})
    assert next(iter(same.values()))["approve"] == "yes"
    path.write_bytes(data + b"\n")
    changed, _ = review.refresh_proposals(same, evidence(), [row], {"TESTACCOUNT": "target"})
    assert next(iter(changed.values()))["approve"] is None


def test_coverage_never_opens_review_or_settles_pending_work(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0, NOTICE_COVERAGE=1)
    (source / "buy.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    (source / "unreadable.pdf").write_bytes(b"unreadable")
    review = tmp_path / "review.yaml"
    pending = tmp_path / "review.yaml.journal.yaml"
    review.write_text("decision: yes\n")
    pending.write_text("pending: keep\n")
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(review))
    with caplog.at_level("INFO"):
        assert app.run_sync(set()) == 1
    assert review.read_text() == "decision: yes\n"
    assert pending.read_text() == "pending: keep\n"
    assert not (tmp_path / "review.yaml.lock").exists()
    assert "incomplete=True" in caplog.text
    post.assert_not_called()
    put.assert_not_called()


def test_unknown_date_before_readable_old_row_cannot_disappear(settings, monkeypatch, tmp_path):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0, IMPORT_CREATE_FROM="2026-01-01")
    data = (FIXTURES / "pdf_buy.txt").read_text()
    header, body = data.split("\n", 1)
    (source / "mixed.pdf").write_text(header + "\n" + body.replace("03/02/2025", "unknown") + "\n" + body)
    errors = set()
    assert app.run_sync(errors) == 1
    assert "notice_unreadable" in errors
    post.assert_not_called()
    put.assert_not_called()


def test_source_parity_and_historical_copy_counts(settings, monkeypatch, tmp_path, caplog):
    from dataclasses import replace
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, NOTICE_COVERAGE=1)
    data = (FIXTURES / "pdf_buy.txt").read_bytes()
    (source / "buy.pdf").write_bytes(data)
    (source / "copy.pdf").write_bytes(data)
    with caplog.at_level("INFO"):
        assert app.run_sync(set()) == 0
    folder_findings = [r.message.split(" event=", 1)[-1] for r in caplog.records if "absent supported document=" in r.message]
    caplog.clear()
    monkeypatch.setattr(config, "load", lambda: replace(settings, notice_coverage=True))
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: data)
    with caplog.at_level("INFO"):
        assert app.run_sync(set()) == 0
    paperless_findings = [r.message.split(" event=", 1)[-1] for r in caplog.records if "absent supported document=" in r.message]
    assert folder_findings == paperless_findings and len(folder_findings) == 1
    post.assert_not_called()
    put.assert_not_called()


def test_source_copies_keep_historical_exclusion_count(settings, monkeypatch, tmp_path, caplog):
    source, _, _ = folder_cycle(settings, monkeypatch, tmp_path, IMPORT_CREATE_FROM="2026-01-01")
    data = (FIXTURES / "pdf_buy.txt").read_bytes()
    for name in ("one.pdf", "two.pdf"):
        (source / name).write_bytes(data)
    with caplog.at_level("INFO"):
        assert app.run_sync(set()) == 0
    assert "excluded_rows=2 excluded_documents=2" in caplog.text


def test_identical_copies_preserve_repeated_rows_in_one_notice(settings, monkeypatch, tmp_path):
    source, post, _ = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0)
    data = (FIXTURES / "pdf_buy.txt").read_text()
    data += "\n" + data.split("\n", 1)[1]
    (source / "one.pdf").write_text(data)
    (source / "two.pdf").write_text(data)
    assert app.run_sync(set()) == 0
    events = [call.args[2][0] for call in post.call_args_list]
    assert len(events) == 2
    assert events[0].comment != events[1].comment


def test_waiver_alias_to_source_and_review_companion_is_rejected(settings, monkeypatch, tmp_path):
    source, _, _ = folder_cycle(settings, monkeypatch, tmp_path)
    original = source / "waiver.pdf"
    original.write_text("\n")
    waiver = tmp_path / "waivers.txt"
    os.link(original, waiver)
    monkeypatch.setenv("NOTICE_WAIVER_FILE", str(waiver))
    with pytest.raises(RuntimeError, match="invalid_configuration NOTICE_WAIVER_FILE"):
        config.load()


def test_unlistable_directory_and_file_change_during_acquisition(settings, monkeypatch, tmp_path):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0, NOTICE_COVERAGE=1)
    source.chmod(0)
    codes = set()
    assert app.run_sync(codes) == 1
    assert codes == {"notice_source_unavailable"}
    source.chmod(0o700)
    path = source / "changed.pdf"
    path.write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    original_stat = os.stat
    def changed(*args, **kwargs):
        result = original_stat(*args, **kwargs)
        if args[0] == "changed.pdf":
            path.write_bytes(path.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(os, "stat", changed)
    codes = set()
    assert app.run_sync(codes) == 1
    assert codes == {"notice_source_unavailable"}
    post.assert_not_called()
    put.assert_not_called()


def test_changed_folder_before_review_dispatch_blocks_put(settings, monkeypatch, tmp_path):
    from test_activity_review import sample
    from test_manual_history import approve

    source, post, put = folder_cycle(settings, monkeypatch, tmp_path)
    path = source / "buy.pdf"
    path.write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    row, _, _ = sample()
    row["fee"] = 2
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ghostfolio.index_existing_activities({"count": 1, "activities": [row]}))
    review = tmp_path / "review.yaml"
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(review))
    assert app.run_sync(set()) == 0
    approve(review)
    monkeypatch.setenv("DRY_RUN", "0")
    reads = 0
    def destination(*_):
        nonlocal reads
        reads += 1
        if reads == 4:
            path.write_bytes(path.read_bytes() + b"\n")
        return ghostfolio.index_existing_activities({"count": 1, "activities": [row]})
    monkeypatch.setattr(ghostfolio, "read_activities", destination)
    codes = set()
    assert app.run_sync(codes) == 1
    assert codes == {"notice_source_unavailable"}
    post.assert_not_called()
    put.assert_not_called()


@pytest.mark.parametrize("row", ["unknown TAXE TRANSACT FINANCIERES  2,86", "unknown DROITS DE GARDE  1,00", "unknown DIVISION  0,00"])
def test_undated_operation_without_isin_cannot_disappear(settings, monkeypatch, tmp_path, row):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0)
    data = (FIXTURES / "pdf_buy.txt").read_text()
    header, body = data.split("\n", 1)
    (source / "mixed.pdf").write_text(header + "\n" + row + "\n" + body)
    codes = set()
    assert app.run_sync(codes) == 1
    assert codes == {"notice_unreadable"}
    post.assert_not_called()
    put.assert_not_called()

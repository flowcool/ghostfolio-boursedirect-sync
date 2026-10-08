import copy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import socket

from bs4 import BeautifulSoup
import pytest

import boursedirect_to_ghostfolio as bd


FIXTURE = Path(__file__).parent / "fixtures" / "statement-synthetic.html"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not use network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def source():
    return bd.decode_document(FIXTURE.read_bytes())


def parse(html=None):
    return bd.parse_statement(source() if html is None else html, 32)


def mutate(change):
    soup = BeautifulSoup(source(), "html.parser")
    ledger = soup.find("table", id="synthetic-ledger")
    columns = bd.cells(bd.direct_rows(ledger)[1])
    vectors = [bd.direct_rows(c.find("table", recursive=False)) for c in columns]
    change(soup, ledger, vectors)
    return str(soup)


def replace_cell(vectors, column, slot, value, cell=0):
    bd.cells(vectors[column][slot])[cell].string = value


def test_four_parallel_vectors_keep_slots_and_controls():
    result = parse()
    assert result["slot_count"] == 13
    assert [e["slot"] for e in result["events"]] == [3, 4, 5]
    assert [e["kind"] for e in result["events"]] == ["SELL", "SELL", "BUY"]
    assert [c["slot"] for c in result["controls"]] == [1, 7, 10]
    assert result["controls"][1]["credit"] == Decimal("2100.00")
    assert result["events"][2]["quantity"] == Decimal("110")
    assert result["events"][2]["unit_price"] == Decimal("5.5")
    assert result["period"] == "2026-09"
    assert bd.inspection_summary(result)["import_ready"] is False


@pytest.mark.parametrize("value,expected", [
    ("+1 234,567", "1234.567"), ("-90", "-90"),
    ("1\u00a0234,50", "1234.50"), ("1\u202f234,50", "1234.50"), ("0,00", "0.00")
])
def test_decimal_grouping_and_sign(value, expected):
    assert bd.parse_decimal(value) == Decimal(expected)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1.25", "1e3", "1 23", "1,2,3", "1 €", ""])
def test_invalid_decimal(value):
    with pytest.raises(RuntimeError, match="^INVALID_DECIMAL$"):
        bd.parse_decimal(value)


def test_exact_cash_precision_beyond_default_decimal_context():
    amount = "123456789012345678901234567890,12"
    assert bd.parse_decimal(amount, cash=True) == Decimal(amount.replace(",", "."))
    with pytest.raises(RuntimeError, match="INVALID_CASH_PRECISION"):
        bd.parse_decimal(amount + "3", cash=True)


@pytest.mark.parametrize("column,slot,value,cell,error", [
    (0, 3, "31/02/2026", 0, "INVALID_DATE"),
    (1, 3, "Qté : 100", 1, "SELL_DIRECTION_CONFLICT"),
    (1, 5, "Qté : -110", 1, "BUY_DIRECTION_CONFLICT"),
    (1, 5, "Cours : 0", 2, "INVALID_TRADE_PRICE"),
    (1, 5, "Cours : 5.5", 2, "INVALID_DECIMAL"),
    (2, 5, "-605,00", 0, "NEGATIVE_CASH_COLUMN"),
    (2, 5, "605,001", 0, "INVALID_CASH_PRECISION"),
    (3, 10, "1 496,00", 0, "BALANCE_MISMATCH"),
    (3, 7, "1 900,00", 0, "CUMULATIVE_MISMATCH"),
    (0, 1, "01/09/2026", 0, "CONTROL_ALIGNMENT_ERROR"),
    (0, 8, "01/09/2026", 0, "ORPHAN_LEDGER_SLOT"),
    (2, 3, "10,00", 0, "AMBIGUOUS_OPERATION_DIRECTION"),
    (1, 1, "Solde au : 30/08/2026", 0, "INVALID_STATEMENT_PERIOD"),
    (1, 10, "Solde au : 29/09/2026", 0, "INVALID_STATEMENT_PERIOD"),
    (1, 7, "Cumul mouvements inconnus :", 0, "ORPHAN_LEDGER_SLOT"),
])
def test_inconsistent_source_fails_closed(column, slot, value, cell, error):
    html = mutate(lambda s, l, v: replace_cell(v, column, slot, value, cell))
    with pytest.raises(RuntimeError, match=f"^{error}$"):
        parse(html)


def test_missing_column_slot():
    with pytest.raises(RuntimeError, match="UNEQUAL_COLUMN_LENGTHS"):
        parse(mutate(lambda s, l, v: v[2][3].decompose()))


def test_ambiguous_ledger():
    with pytest.raises(RuntimeError, match="LEDGER_MISSING_OR_AMBIGUOUS"):
        parse(mutate(lambda s, l, v: l.insert_after(copy.deepcopy(l))))


def test_nested_slot_table():
    def change(soup, ledger, vectors):
        bd.cells(vectors[1][3])[0].append(soup.new_tag("table"))
    with pytest.raises(RuntimeError, match="NESTED_SLOT_TABLE"):
        parse(mutate(change))


def test_unaligned_direct_text_is_rejected():
    def change(soup, ledger, vectors):
        bd.cells(bd.direct_rows(ledger)[1])[0].append("23/09/2026")
    with pytest.raises(RuntimeError, match="UNSUPPORTED_COLUMN_STRUCTURE"):
        parse(mutate(change))


def test_transparent_font_tags_and_tbody_variant():
    # Fixture already wraps scalar values in transparent fonts.
    html = source().replace("<table class=\"column\">", '<table class="column"><tbody>')
    html = html.replace("</table></td>", "</tbody></table></td>")
    assert len(parse(html)["events"]) == 3


def test_identical_trades_remain_two_occurrences():
    def change(soup, ledger, vectors):
        for index in range(4):
            vectors[index][4].replace_with(copy.deepcopy(vectors[index][3]))
        vectors = [bd.direct_rows(c.find("table", recursive=False))
                   for c in bd.cells(bd.direct_rows(ledger)[1])]
        replace_cell(vectors, 3, 7, "2200,00")
        replace_cell(vectors, 3, 10, "1595,00")
    result = parse(mutate(change))
    assert len(result["events"]) == 3
    first, second = result["events"][:2]
    assert first["slot"] != second["slot"]
    assert {k: v for k, v in first.items() if k != "slot"} == {k: v for k, v in second.items() if k != "slot"}


def test_missing_account_header_and_changed_header():
    with pytest.raises(RuntimeError, match="ACCOUNT_HEADER_MISSING_OR_AMBIGUOUS"):
        parse(source().replace("COMPTE N&deg;", "WRONG HEADER"))
    with pytest.raises(RuntimeError, match="LEDGER_MISSING_OR_AMBIGUOUS"):
        parse(source().replace("D&eacute;bit (&euro;)", "Debit (USD)"))


def test_unknown_operations_preserved_and_blocking():
    html = mutate(lambda s, l, v: replace_cell(v, 1, 3, "UNSUPPORTED CORPORATE ACTION"))
    result = parse(html)
    assert result["events"][0]["kind"] == "UNKNOWN"
    assert "UNKNOWN_OPERATIONS" in result["blockers"]
    assert len(result["events"]) == 3


def test_operation_month_boundary_is_blocking_not_guessed():
    html = mutate(lambda s, l, v: replace_cell(v, 0, 3, "31/08/2026"))
    assert "OPERATION_OUTSIDE_STATEMENT_MONTH" in parse(html)["blockers"]


def test_negative_balances_reconcile():
    def change(soup, ledger, vectors):
        for column, slot, value in [(3, 1, ""), (2, 1, "200,00"),
                                    (2, 7, "805,00"), (3, 7, "1900,00"),
                                    (3, 10, "1095,00")]:
            replace_cell(vectors, column, slot, value)
    result = parse(mutate(change))
    assert result["controls"][0]["debit"] == Decimal("200")


def test_money_reconciliation_does_not_depend_on_process_precision():
    result = parse()
    with localcontext() as context:
        context.prec = 2
        bd.validate_ledger(result["controls"], result["events"])
        result["controls"][2]["credit"] = Decimal("1495.01")
        with pytest.raises(RuntimeError, match="BALANCE_MISMATCH"):
            bd.validate_ledger(result["controls"], result["events"])


def test_utf8_saved_variant():
    html = source().replace("windows-1252", "utf-8")
    assert len(parse(bd.decode_document(html.encode("utf-8")))["events"]) == 3


@pytest.mark.parametrize("raw,error", [
    (b'<meta charset="utf-8">\xff', "INVALID_DOCUMENT_ENCODING"),
    (b'<meta charset="windows-1252">\x81', "INVALID_DOCUMENT_ENCODING"),
    (b'<meta charset="latin1">', "UNSUPPORTED_OR_AMBIGUOUS_ENCODING"),
    (b'<meta charset="utf-8"><meta charset="windows-1252">', "UNSUPPORTED_OR_AMBIGUOUS_ENCODING"),
    (b'<html></html>', "UNSUPPORTED_OR_AMBIGUOUS_ENCODING"),
    (b'\xef\xbb\xbf<meta charset="windows-1252">', "ENCODING_BOM_CONFLICT"),
    (b'<meta charset="utf-8">\x00', "INVALID_DOCUMENT_BYTES"),
    ('<meta charset="utf-8">\ufffd'.encode(), "REPLACEMENT_CHARACTER"),
])
def test_encoding_policy(raw, error):
    with pytest.raises(RuntimeError, match=f"^{error}$"):
        bd.decode_document(raw)


def test_file_boundary_and_limit(tmp_path):
    root = tmp_path / "inputs"
    root.mkdir()
    document = root / "statement.html"
    document.write_bytes(FIXTURE.read_bytes())
    html, digest = bd.read_document(document, root, 100000)
    assert html == source()
    assert len(digest) == 64
    with pytest.raises(RuntimeError, match="INPUT_TOO_LARGE"):
        bd.read_document(document, root, 10)
    link = root / "link.html"
    link.symlink_to(document)
    with pytest.raises(RuntimeError, match="SYMLINK_INPUT"):
        bd.read_document(link, root, 100000)
    with pytest.raises(RuntimeError, match="INPUT_OUTSIDE_ROOT"):
        bd.read_document(FIXTURE, root, 100000)
    with pytest.raises(RuntimeError, match="INPUT_NOT_REGULAR"):
        bd.read_document(root, root, 100000)


def test_depth_limit():
    with pytest.raises(RuntimeError, match="INPUT_TOO_DEEP"):
        bd.parse_statement(source(), 3)


def test_cli_safe_summary_and_blocked_exit(capsys):
    status = bd.main(["inspect", str(FIXTURE), "--input-root", str(FIXTURE.parent),
                      "--max-bytes", "100000", "--max-depth", "32"])
    captured = capsys.readouterr()
    assert status == 2
    summary = json.loads(captured.out)
    assert summary["operation_counts"] == {"BUY": 1, "SELL": 2, "UNKNOWN": 0}
    for private_value in ["SYNTHETIC_ACCOUNT", "SYNTHETIC ALPHA", "1495", str(FIXTURE)]:
        assert private_value not in captured.out + captured.err


def test_cli_errors_do_not_echo_private_filename(tmp_path, caplog):
    status = bd.main(["inspect", str(tmp_path / "private-account-name.html"),
                      "--input-root", str(tmp_path), "--max-bytes", "1000", "--max-depth", "32"])
    assert status == 1
    assert "LOCAL_INPUT_ERROR" in caplog.text
    assert "private-account-name" not in caplog.text

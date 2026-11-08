"""Cash behavior from anonymized retained statements and notices; HTTP is mocked."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from test_folder_source import folder_cycle
from test_pdf_buy import settings as settings

from ghostfolio_boursedirect_sync import (
    app,
    cash,
    config,
    ghostfolio,
    notices,
    statements,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("value, expected", [(None, False), ("0", False), ("1", True)])
def test_cash_setting(settings, monkeypatch, value, expected):
    monkeypatch.delenv("CASH_BALANCE", raising=False)
    if value is not None:
        monkeypatch.setenv("CASH_BALANCE", value)
    assert config.load().cash_balance is expected


@pytest.mark.parametrize("value", ["", "yes", "true", " 1", "01", "2"])
def test_invalid_cash_setting_before_services(settings, monkeypatch, caplog, value):
    monkeypatch.setenv("CASH_BALANCE", value)
    acquire = Mock(side_effect=AssertionError("service access"))
    monkeypatch.setattr(app.notice_source, "acquire", acquire)
    assert app.main() == 1
    assert "invalid_configuration CASH_BALANCE" in caplog.text
    acquire.assert_not_called()


def test_cash_uses_checked_net_including_coupon_and_ttf():
    statement = statements.parse_text((FIXTURES / "pdf_statement.txt").read_text())
    buy = notices.parse_text((FIXTURES / "pdf_buy.txt").read_text() +
        "\n03/02/2025 TAXE TRANSACT FINANCIERES FR0000120271  0.30\n")
    coupon = notices.parse_text((FIXTURES / "pdf_coupon.txt").read_text())
    result = cash.calculate([statement], [buy, coupon, buy], "TESTACCOUNT")
    # 925.00 - 103.00 - .30 + 4.86; coupon gross is 5.72, not net.
    assert result.amount == Decimal("826.56")
    assert result.closing_date == date(2025, 1, 31)
    assert result.notices == 2


def account_response(balance="0.00", **changes):
    body = {"id": "target", "currency": "EUR", "name": "Example PEA", "platformId": None,
            "balance": Decimal(balance), "comment": "private", "tags": [{"id": "tag"}], **changes}
    return Mock(status_code=200, content=ghostfolio.decimal_json(body).encode())


@pytest.mark.parametrize("dry, stored, result, writes", [
    (True, "0", "simulated", 0), (False, "228.66", "unchanged", 0), (False, "0", "updated", 1)])
def test_cash_http_exact_dto_and_readback(settings, monkeypatch, dry, stored, result, writes):
    get = Mock(side_effect=[account_response(stored), account_response("228.66")])
    put = Mock(return_value=Mock(status_code=200))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    assert ghostfolio.update_cash_balance(replace(settings, dry_run=dry), "token", "target", Decimal("228.66")) == result
    assert put.call_count == writes
    assert get.call_count == 1 + writes
    if writes:
        assert json.loads(put.call_args.kwargs["data"], parse_float=Decimal) == {
            "balance": Decimal("228.66"), "currency": "EUR", "id": "target",
            "name": "Example PEA", "platformId": None}
        assert put.call_args.kwargs["allow_redirects"] is False
        assert put.call_args.args[0] == "http://ghostfolio.test/api/v1/account/target"


@pytest.mark.parametrize("dry", ["0", "1"])
@pytest.mark.parametrize("broken", [False, True])
def test_cash_runs_after_imports_and_does_not_block_them(settings, monkeypatch, tmp_path, caplog, dry, broken):
    source, post, _ = folder_cycle(settings, monkeypatch, tmp_path, CASH_BALANCE=1, DRY_RUN=dry)
    (source / "buy.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    text = (FIXTURES / "pdf_statement.txt").read_text()
    (source / "statement.pdf").write_text(text.replace("925,00", "925,01") if broken else text)
    def update(*args):
        assert post.call_count == (1 if dry == "0" else 0)
        assert args[-1] == Decimal("822.00")
        return "simulated" if dry == "1" else "updated"
    cash_update = Mock(side_effect=update)
    monkeypatch.setattr(ghostfolio, "update_cash_balance", cash_update)
    with caplog.at_level("INFO"):
        assert app.main() == 0
    assert post.call_count == (1 if dry == "0" else 0)
    assert cash_update.call_count == (0 if broken else 1)
    assert f"cash={'unavailable' if broken else 'simulated' if dry == '1' else 'updated'}" in caplog.text
    if broken:
        assert "Cycle result: success with user action required" in caplog.text
        assert "Action required: cash_unavailable" not in caplog.text  # notifications disabled
        assert "cash_unavailable:" in caplog.text
    else:
        assert "Cash: statement=2025-01-31 later_notices=1 proposed=822.00 EUR" in caplog.text
    assert "EXAMPLE HOLDER" not in caplog.text
    assert "Solde au" not in caplog.text


@pytest.mark.parametrize("change", [
    {"currency": "USD"}, {"balance": None}, {"balance": True}, {"balance": "0"},
    {"name": None}, {"platformId": 4}, {"id": "other"}])
def test_invalid_account_blocks_cash_only(settings, monkeypatch, change):
    body = json.loads(account_response().content, parse_float=Decimal)
    body.update(change)
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(status_code=200,
        content=ghostfolio.decimal_json(body).encode())))
    put = Mock()
    monkeypatch.setattr(requests, "put", put)
    with pytest.raises(RuntimeError, match="^cash_unavailable$"):
        ghostfolio.update_cash_balance(replace(settings, dry_run=False), "token", "target", Decimal("228.66"))
    put.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "redirect", "http", "readback", "read_timeout", "bad_json"])
def test_cash_uncertainty_never_resends(settings, monkeypatch, failure):
    before = account_response()
    after = account_response("228.67") if failure == "readback" else account_response("228.66")
    if failure == "bad_json":
        after = Mock(status_code=200, content=b"private invalid response")
    get = Mock(side_effect=[before, requests.Timeout("private") if failure == "read_timeout" else after])
    put = Mock(side_effect=requests.Timeout("private") if failure == "timeout" else None,
               return_value=Mock(status_code=302 if failure == "redirect" else 500 if failure == "http" else 200))
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "put", put)
    with pytest.raises(RuntimeError, match="^cash_unavailable$"):
        ghostfolio.update_cash_balance(replace(settings, dry_run=False), "token", "target", Decimal("228.66"))
    assert put.call_count == 1
    assert get.call_count == (1 if failure in ("timeout", "redirect", "http") else 2)


@pytest.mark.parametrize("case", ["missing", "broken_chain", "other", "only", "failed_write"])
def test_statement_selection_and_cash_failure_are_independent(settings, monkeypatch, tmp_path, caplog, case):
    source, post, _ = folder_cycle(settings, monkeypatch, tmp_path, CASH_BALANCE=1, DRY_RUN=0)
    if case != "only":
        (source / "buy.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    text = (FIXTURES / "pdf_statement.txt").read_text()
    if case != "missing":
        (source / "statement.pdf").write_text(text)
    if case == "broken_chain":
        # Individually reconciled, but opening 1000 != previous closing 925.
        (source / "second.pdf").write_text(text.replace("31/01/2025", "28/02/2025")
            .replace("31/12/2024", "31/01/2025").replace("03/01/2025", "03/02/2025")
            .replace("06/01/2025", "06/02/2025"))
    if case == "other":
        # The other account is ignored before its inconsistent amounts are read.
        (source / "other.pdf").write_text(text.replace("TEST ACCOUNT", "OTHER ACCOUNT").replace("925,00", "bad"))
    update = Mock(return_value="updated", side_effect=RuntimeError("cash_unavailable") if case == "failed_write" else None)
    monkeypatch.setattr(ghostfolio, "update_cash_balance", update)
    errors = set()
    with caplog.at_level("INFO"):
        assert app.run_sync(errors) == 0
    assert post.call_count == (0 if case == "only" else 1)
    assert update.call_count == int(case in ("other", "only", "failed_write"))
    assert errors == ({"cash_unavailable"} if case in ("missing", "broken_chain", "failed_write") else set())
    if case == "other":
        assert "other_account_statements=1" in caplog.text
    if case == "only":
        assert update.call_args.args[-1] == Decimal("925.00")


def test_latest_statement_boundary_account_and_decimal_precision():
    from decimal import localcontext
    statement = statements.parse_text((FIXTURES / "pdf_statement.txt").read_text())
    buy = notices.parse_text((FIXTURES / "pdf_buy.txt").read_text())
    ignored = replace(buy, account_ref="OTHER")
    boundary = replace(buy, trades=(replace(buy.trades[0], date=statement.closing_date),))
    with localcontext() as context:
        context.prec = 2
        result = cash.calculate([statement, statement, replace(statement, account_ref="OTHER")],
                                [buy, ignored, boundary], "TESTACCOUNT")
    assert result.amount == Decimal("822.00")
    assert result.notices == 1


def test_cash_failure_notification_is_user_action():
    from ghostfolio_boursedirect_sync import outcome
    assert "cash_unavailable" not in outcome.FAILURE_CODES
    assert outcome.notification_summary({"cash_unavailable"}).startswith("Action required: cash_unavailable.")


def test_sell_cash_and_latest_statement():
    first = statements.parse_text((FIXTURES / "pdf_statement.txt").read_text())
    second = replace(first, opening_date=first.closing_date, closing_date=date(2025, 2, 28),
                     opening_balance=first.closing_balance, closing_balance=Decimal("850.00"))
    buy = notices.parse_text((FIXTURES / "pdf_buy.txt").read_text())
    sale = notices.parse_text((FIXTURES / "pdf_sell_custody.txt").read_text())
    # BUY is inside the latest period. SELL net is 1123.30, custody fee excluded.
    result = cash.calculate([second, first], [buy, sale], "TESTACCOUNT")
    assert result.amount == Decimal("1973.30")
    assert result.notices == 1


def test_uncertain_activity_stops_before_cash(settings, monkeypatch, tmp_path):
    source, post, _ = folder_cycle(settings, monkeypatch, tmp_path, CASH_BALANCE=1, DRY_RUN=0)
    (source / "buy.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    (source / "statement.pdf").write_bytes((FIXTURES / "pdf_statement.txt").read_bytes())
    post.side_effect = RuntimeError("import_unconfirmed")
    update = Mock()
    monkeypatch.setattr(ghostfolio, "update_cash_balance", update)
    errors = set()
    assert app.run_sync(errors) == 1
    assert "import_unconfirmed" in errors
    update.assert_not_called()


def test_cash_ignores_creation_cutoff_and_duplicates(settings, monkeypatch, tmp_path):
    source, post, _ = folder_cycle(settings, monkeypatch, tmp_path, CASH_BALANCE=1,
                                   IMPORT_CREATE_FROM="2025-02-04", DRY_RUN=0)
    (source / "buy.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    (source / "statement.pdf").write_bytes((FIXTURES / "pdf_statement.txt").read_bytes())
    update = Mock(return_value="unchanged")
    monkeypatch.setattr(ghostfolio, "update_cash_balance", update)
    assert app.run_sync(set()) == 0
    post.assert_not_called()
    assert update.call_args.args[-1] == Decimal("822.00")

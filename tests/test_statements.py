"""Statement text keeps the retained pdftotext column layout, with changed data."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from test_folder_source import folder_cycle
from test_pdf_buy import settings as settings

from ghostfolio_boursedirect_sync import app, paperless, statements

FIXTURES = Path(__file__).parent / "fixtures"


def test_statement_recognized_by_content():
    text = (FIXTURES / "pdf_statement.txt").read_text()
    assert statements.is_statement(text)
    assert not statements.is_statement(text.replace("RELEVE DE COMPTE", "RELEVE DE TITRES"))
    assert not statements.is_statement(text.replace("Solde au : 31/01/2025", "Balance"))
    assert not statements.is_statement((FIXTURES / "pdf_buy.txt").read_text())


@pytest.mark.parametrize('dry_run', ['0', '1'])
@pytest.mark.parametrize('source_mode', ['folder', 'paperless'])
def test_statements_next_to_notices(settings, monkeypatch, tmp_path, caplog, dry_run, source_mode):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=dry_run)
    (source / "notice.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    # Recognition must not parse amounts while cash management is absent.
    text = (FIXTURES / "pdf_statement.txt").read_text().replace("925,00", "invalid")
    (source / "statement.pdf").write_text(text)
    if source_mode == 'paperless':
        monkeypatch.delenv('NOTICE_DIR')
        monkeypatch.setenv('PAPERLESS_URL', settings.paperless_url)
        monkeypatch.setenv('PAPERLESS_TOKEN', settings.paperless_token)
        monkeypatch.setattr(paperless, 'document_ids', lambda _: [1, 2])
        monkeypatch.setattr(paperless, 'original_pdf', lambda _, doc:
                            (FIXTURES / 'pdf_buy.txt').read_bytes() if doc == 1 else text.encode())
    errors = set()
    with caplog.at_level("DEBUG"):
        assert app.run_sync(errors) == 0
    assert not errors
    assert "Account statements: recognized=1" in caplog.text
    assert ('simulated=1' if dry_run == '1' else 'created=1') in caplog.text
    assert "unreadable_notices=0" in caplog.text
    assert "notice_unreadable" not in caplog.text
    assert "EXAMPLE HOLDER" not in caplog.text
    assert "EXAMPLE STREET" not in caplog.text
    assert 'Solde au' not in caplog.text
    assert post.call_count == (0 if dry_run == '1' else 1)
    put.assert_not_called()


def test_unknown_pdf_still_blocks_notices(settings, monkeypatch, tmp_path, caplog):
    source, post, put = folder_cycle(settings, monkeypatch, tmp_path, DRY_RUN=0)
    (source / "notice.pdf").write_bytes((FIXTURES / "pdf_buy.txt").read_bytes())
    (source / "unknown.pdf").write_text("EXAMPLE HOLDER\nUnknown PDF")
    errors = set()
    with caplog.at_level("INFO"):
        assert app.run_sync(errors) == 1
    assert errors == {"notice_unreadable"}
    assert "Account statements: recognized=0" in caplog.text
    assert "unreadable_notices=1" in caplog.text
    assert "EXAMPLE HOLDER" not in caplog.text
    post.assert_not_called()
    put.assert_not_called()


def test_parse_reconciled_statement():
    statement = statements.parse_text((FIXTURES / "pdf_statement.txt").read_text())
    assert statement.account_ref == "TESTACCOUNT"
    assert (statement.opening_date, statement.closing_date) == (date(2024, 12, 31), date(2025, 1, 31))
    assert (statement.opening_balance, statement.closing_balance) == (Decimal("1000.00"), Decimal("925.00"))
    assert [(m.date, m.amount) for m in statement.movements] == [
        (date(2025, 1, 3), Decimal("-100.00")), (date(2025, 1, 6), Decimal("25.00"))]
    with pytest.raises(FrozenInstanceError):
        statement.closing_balance = Decimal(0)


def test_statement_mismatch_is_fixed_redacted_error():
    text = (FIXTURES / "pdf_statement.txt").read_text().replace("925,00", "925,01")
    with pytest.raises(RuntimeError, match="^statement_unreadable$"):
        statements.parse_text(text)


def test_movement_without_cash_does_not_use_price():
    text = (FIXTURES / "pdf_statement.txt").read_text()
    # Observed zero-cash share movements retain a nonzero Cours field.
    row = '10/01/2025     DIVISION EXAMPLE SECURITY'.ljust(84) + 'Qté : 2 800'.ljust(18) + 'Cours : 0,002'
    text = text.replace('               Cumul mouvements :', row + '\n\n               Cumul mouvements :')
    statement = statements.parse_text(text)
    assert statement.movements[-1].amount == Decimal(0)
    assert statement.closing_balance == Decimal('925.00')


def test_wrapped_movement_keeps_one_amount():
    text = (FIXTURES / "pdf_statement.txt").read_text()
    line = next(line for line in text.splitlines() if line.startswith('03/01/2025'))
    # Keep the quantity, price and cash columns on the continuation line.
    text = text.replace(line, line[:84].rstrip() + '\n' + ' ' * 84 + line[84:])
    statement = statements.parse_text(text)
    assert [m.amount for m in statement.movements] == [Decimal('-100.00'), Decimal('25.00')]


def test_sign_comes_from_column_not_movement_label():
    text = (FIXTURES / "pdf_statement.txt").read_text()
    # A label can be misleading. Keep the original columns and exact totals.
    text = text.replace('ACH CPT EXAMPLE SECURITY', 'VTE CPT EXAMPLE SECURITY')
    text = text.replace('COUPONS EXAMPLE SECURITY', 'ACH CPT EXAMPLE SECURITY')
    assert [m.amount for m in statements.parse_text(text).movements] == [Decimal('-100.00'), Decimal('25.00')]


@pytest.mark.parametrize('broken', [False, True])
def test_consecutive_statement_chain(broken):
    first = statements.parse_text((FIXTURES / 'pdf_statement.txt').read_text())
    second = replace(first, opening_date=date(2025, 1, 31), closing_date=date(2025, 2, 28),
                     opening_balance=Decimal('925.01') if broken else Decimal('925.00'),
                     closing_balance=Decimal('850.01') if broken else Decimal('850.00'))
    if broken:
        with pytest.raises(RuntimeError, match='^statement_unreadable$'):
            statements.validate_chain([second, first])
    else:
        statements.validate_chain([second, first])


@pytest.mark.parametrize('change', ['bad_account', 'currency', 'bad_date', 'bad_amount', 'duplicate_cash'])
def test_unreadable_statement_rejects_without_private_text(change):
    text = (FIXTURES / 'pdf_statement.txt').read_text()
    if change == 'bad_account':
        text += '\nCOMPTE N° OTHER EUR PEA\n'
    elif change == 'currency':
        text = text.replace('EUR PEA', 'USD PEA')
    elif change == 'bad_date':
        text = text.replace('03/01/2025', '32/01/2025')
    elif change == 'bad_amount':
        text = text.replace('100,00', '100,0X')
    else:
        row = next(line for line in text.splitlines() if line.startswith('03/01/2025'))
        text = text.replace(row, row + '\n' + ' ' * 132 + '100,00')
    with pytest.raises(RuntimeError, match='^statement_unreadable$'):
        statements.parse_text(text)


def test_statement_does_not_round_with_ambient_decimal_context():
    from decimal import localcontext

    text = (FIXTURES / 'pdf_statement.txt').read_text()
    text = text.replace('100,00', '123,45').replace('925,00', '901,55')
    with localcontext() as context:
        context.prec = 2
        statement = statements.parse_text(text)
    assert statement.movements[0].amount == Decimal('-123.45')


def test_debit_balances_are_negative():
    text = (FIXTURES / 'pdf_statement.txt').read_text()
    for line in text.splitlines():
        if 'Solde au' in line:
            label = line[:36].rstrip()
            amount = '1 000,00' if '31/12/2024' in line else '1 075,00'
            text = text.replace(line, label.ljust(140 - len(amount)) + amount)
    statement = statements.parse_text(text)
    assert (statement.opening_balance, statement.closing_balance) == (Decimal('-1000.00'), Decimal('-1075.00'))


@pytest.mark.parametrize('change', ['account', 'period'])
def test_statement_chain_rejects_other_account_or_nonconsecutive_period(change):
    first = statements.parse_text((FIXTURES / 'pdf_statement.txt').read_text())
    second = replace(first, opening_date=date(2025, 1, 31), closing_date=date(2025, 2, 28),
                     opening_balance=Decimal('925.00'), closing_balance=Decimal('850.00'))
    second = replace(second, **({'account_ref': 'OTHER'} if change == 'account' else
                                {'opening_date': date(2025, 2, 1)}))
    with pytest.raises(RuntimeError, match='^statement_unreadable$'):
        statements.validate_chain([first, second])

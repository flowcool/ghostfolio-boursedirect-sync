import copy
from decimal import Decimal, localcontext
import json
from pathlib import Path
import socket

from bs4 import BeautifulSoup
import pytest

import boursedirect_to_ghostfolio as bd

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def note_source(multiple=False):
    name = 'note-multi-sell-synthetic.html' if multiple else 'note-buy-synthetic.html'
    return bd.decode_document((FIXTURES / name).read_bytes())


def document(multiple=False):
    return bd.parse_contract_note(note_source(multiple), 32)


def vectors(soup):
    ledger = soup.find('table', id='synthetic-note')
    return [bd.direct_rows(c.find('table', recursive=False)) for c in bd.cells(bd.direct_rows(ledger)[1])]


def field(soup, slot, cell=0):
    column = vectors(soup)[1]
    nested = bd.cells(column[slot])[0].find('table', recursive=False)
    return bd.cells(bd.direct_rows(nested)[0])[cell]


def change_field(slot, cell, value):
    soup = BeautifulSoup(note_source(), 'html.parser')
    field(soup, slot, cell).string = value
    return str(soup)


def statement_from_notes(docs):
    return {'account_ref': docs[0]['account_ref'], 'events': [copy.deepcopy(n) for d in docs for n in d['notes']]}


def test_explicit_fields_and_two_daily_sales_keep_separate_groups():
    buy = document()
    sell = document(True)
    assert buy['slot_count'] == 9 and sell['slot_count'] == 18
    assert [n['slot'] for n in sell['notes']] == [1, 10]
    assert [n['kind'] for n in sell['notes']] == ['SELL', 'SELL']
    assert buy['notes'][0]['brokerage'] == Decimal('0.45')
    assert buy['notes'][0]['price_currency'] is None
    assert buy['notes'][0]['net_currency'] == 'EUR'
    assert buy['notes'][0]['execution_time'] == '10:00:00'


@pytest.mark.parametrize('slot,cell,value,error', [
    (1, 0, 'VENTE ETRANGER', 'UNSUPPORTED_NOTE_OPERATION'),
    (1, 1, 'FR0000000000', 'INVALID_NOTE_SECURITY'),
    (3, 0, 'QUANTITE : -3', 'NOTE_DIRECTION_CONFLICT'),
    (3, 1, 'TAXE : 1,00', 'UNSUPPORTED_NOTE_EXTRA_FIELD'),
    (4, 0, 'COURS : 0', 'INVALID_NOTE_PRICE_OR_GROSS'),
    (4, 1, 'BRUT : +31,00', 'NOTE_GROSS_MISMATCH'),
    (4, 1, 'BRUT : +30,001', 'INVALID_CASH_PRECISION'),
    (5, 0, 'COURTAGE : +0,50', 'NOTE_NET_MISMATCH'),
    (5, 0, 'COURTAGE : -0,45', 'NEGATIVE_NOTE_AMOUNT'),
    (5, 1, 'TVA : +0,01', 'NOTE_NET_MISMATCH'),
    (7, 0, 'Heure Execution: 25:00:00', 'INVALID_NOTE_EXECUTION_TIME'),
    (7, 1, 'Lieu:', 'UNSUPPORTED_NOTE_EXECUTION_FIELDS'),
])
def test_unseen_fields_invalid_security_and_money_fail(slot, cell, value, error):
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        bd.parse_contract_note(change_field(slot, cell, value), 32)


def test_valid_nonzero_vat_is_separate_and_reconciles():
    soup = BeautifulSoup(note_source(), 'html.parser')
    field(soup, 5, 1).string = 'TVA : +0,09'
    bd.cells(vectors(soup)[2][1])[0].string = '30,54'
    result = bd.parse_contract_note(str(soup), 32)
    assert result['notes'][0]['vat'] == Decimal('0.09')
    assert result['notes'][0]['brokerage'] == Decimal('0.45')


@pytest.mark.parametrize('mutation,error', [
    ('shift', 'UNEQUAL_COLUMN_LENGTHS'),
    ('blank', 'NOTE_BLANK_SLOT_CONFLICT'),
    ('money', 'NOTE_FIELD_ALIGNMENT_ERROR'),
    ('extra_row', 'UNSUPPORTED_NOTE_GROUP_LENGTH'),
    ('nested', 'UNSUPPORTED_NOTE_SLOT'),
])
def test_alignment_and_unknown_structure_fail(mutation, error):
    soup = BeautifulSoup(note_source(), 'html.parser')
    cols = vectors(soup)
    if mutation == 'shift':
        cols[0][0].decompose()
    elif mutation == 'blank':
        bd.cells(cols[0][2])[0].string = '17/09/2026'
    elif mutation == 'money':
        bd.cells(cols[2][3])[0].string = '30,45'
    elif mutation == 'extra_row':
        for column in cols:
            column[0].parent.append(copy.copy(column[0]))
    elif mutation == 'nested':
        bd.cells(cols[0][1])[0].append(soup.new_tag('table'))
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        bd.parse_contract_note(str(soup), 32)


def test_changed_date_in_multi_operation_note_fails():
    soup = BeautifulSoup(note_source(True), 'html.parser')
    bd.cells(vectors(soup)[0][10])[0].string = '18/09/2026'
    with pytest.raises(RuntimeError, match='NOTE_MULTIPLE_DATES'):
        bd.parse_contract_note(str(soup), 32)


def test_large_decimal_product_and_cost_do_not_round_under_default_context():
    soup = BeautifulSoup(note_source(), 'html.parser')
    value = '123456789012345678901234567890'
    field(soup, 3).string = 'QUANTITE : +' + value
    field(soup, 4).string = 'COURS : +1'
    field(soup, 4, 1).string = 'BRUT : +' + value
    with localcontext() as context:
        context.prec = 80
        net = Decimal(value) + Decimal('0.45')
    bd.cells(vectors(soup)[2][1])[0].string = str(net).replace('.', ',')
    assert bd.parse_contract_note(str(soup), 32)['notes'][0]['debit'] == net


def test_account_mismatch_blocks_before_matching():
    doc = document()
    statement = statement_from_notes([doc])
    statement['account_ref'] = 'ANOTHER_SYNTHETIC_ACCOUNT'
    with pytest.raises(RuntimeError, match='NOTE_ACCOUNT_MISMATCH'):
        bd.match_trade_notes(statement, [doc])


def test_unique_exact_matches_do_not_infer_currency_or_names():
    docs = [document(), document(True)]
    statement = statement_from_notes(docs)
    for event in statement['events']:
        event['name'] = 'DIFFERENT NAME'
    result = bd.match_trade_notes(statement, docs)
    assert len(result['matches']) == 3
    assert result['blockers'] == ['EXPLICIT_PRICE_CURRENCY_REQUIRED']


@pytest.mark.parametrize('key,value', [('date', bd.parse_date('18/09/2026')), ('quantity', Decimal('4')),
                                     ('unit_price', Decimal('11')), ('debit', Decimal('30.46')), ('kind', 'SELL')])
def test_no_tolerance_or_name_fallback_for_changed_trade(key, value):
    doc = document()
    statement = statement_from_notes([doc])
    statement['events'][0][key] = value
    result = bd.match_trade_notes(statement, [doc])
    assert not result['matches']
    assert result['missing_trades'] == 1 and result['unmatched_notes'] == 1
    assert 'TRADE_NOTE_MISSING' in result['blockers']


def test_duplicate_files_and_identical_trades_preserve_multiplicity_and_block():
    doc = document()
    statement = statement_from_notes([doc, doc])
    result = bd.match_trade_notes(statement, [doc, copy.deepcopy(doc)])
    assert result['note_count'] == 2 and result['ambiguous_trades'] == 2
    assert not result['matches'] and 'TRADE_NOTE_AMBIGUOUS' in result['blockers']
    one = bd.match_trade_notes(statement, [doc])
    assert one['ambiguous_trades'] == 2 and not one['matches']


def paired_statement():
    soup = BeautifulSoup(bd.decode_document((FIXTURES / 'statement-synthetic.html').read_bytes()), 'html.parser')
    ledger = soup.find('table', id='synthetic-ledger')
    columns = [bd.direct_rows(c.find('table', recursive=False)) for c in bd.cells(bd.direct_rows(ledger)[1])]
    def set_cell(column, slot, value, cell=0):
        bd.cells(columns[column][slot])[cell].string = value
    for slot in (3, 4, 5):
        set_cell(0, slot, '17/09/2026')
    for slot, quantity, price in [(3, '-2', '12'), (4, '-5', '7'), (5, '3', '10')]:
        set_cell(1, slot, 'Qté : ' + quantity, 1)
        set_cell(1, slot, 'Cours : ' + price, 2)
    for column, slot, amount in [(3, 3, '23,80'), (3, 4, '34,65'), (2, 5, '30,45'),
                                  (2, 7, '30,45'), (3, 7, '258,45'), (3, 10, '228,00')]:
        set_cell(column, slot, amount)
    return str(soup)


def test_cli_matching_is_bounded_offline_and_logs_counts_only(tmp_path, capsys):
    statement = tmp_path / 'private-sensitive-path.html'
    buy = tmp_path / 'private-buy.html'
    sell = tmp_path / 'private-sell.html'
    statement.write_text(paired_statement().replace('windows-1252', 'utf-8'))
    buy.write_text(note_source())
    sell.write_text(note_source(True))
    status = bd.main(['inspect', str(statement), '--input-root', str(tmp_path), '--max-bytes', '100000',
                      '--max-depth', '32', '--notes', str(buy), str(sell)])
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert status == 2 and report['import_ready'] is False
    assert report['note_matching'] == {'note_count': 3, 'matched_trades': 3, 'missing_trades': 0,
                                       'ambiguous_trades': 0, 'unmatched_notes': 0}
    assert report['blockers'] == ['EXPLICIT_PRICE_CURRENCY_REQUIRED', 'REAL_SOURCE_ACCEPTANCE_PENDING']
    assert 'SYNTHETIC_ACCOUNT' not in captured.out and 'FR000' not in captured.out
    assert 'private' not in captured.out and '30.45' not in captured.out


def test_note_paths_obey_same_input_root(tmp_path, caplog):
    statement = tmp_path / 'statement.html'
    statement.write_text(paired_statement().replace('windows-1252', 'utf-8'))
    status = bd.main(['inspect', str(statement), '--input-root', str(tmp_path), '--max-bytes', '100000',
                      '--max-depth', '32', '--notes', str(FIXTURES / 'note-buy-synthetic.html')])
    assert status == 1
    assert 'INPUT_OUTSIDE_ROOT' in caplog.text and 'note-buy-synthetic' not in caplog.text


def test_note_depth_and_multiple_ledger_are_rejected():
    with pytest.raises(RuntimeError, match='INPUT_TOO_DEEP'):
        bd.parse_contract_note(note_source(), 3)
    soup = BeautifulSoup(note_source(), 'html.parser')
    soup.body.append(copy.copy(soup.find('table', id='synthetic-note')))
    with pytest.raises(RuntimeError, match='LEDGER_MISSING_OR_AMBIGUOUS'):
        bd.parse_contract_note(str(soup), 32)


def test_note_sign_and_extra_cash_direction_rejected():
    soup = BeautifulSoup(note_source(), 'html.parser')
    bd.cells(vectors(soup)[3][1])[0].string = '0,01'
    with pytest.raises(RuntimeError, match='NOTE_DIRECTION_CONFLICT'):
        bd.parse_contract_note(str(soup), 32)


def test_invalid_note_cli_diagnostics_do_not_expose_raw_fields(tmp_path, caplog):
    statement = tmp_path / 'private-statement.html'
    note = tmp_path / 'private-sensitive-note.html'
    statement.write_text(paired_statement().replace('windows-1252', 'utf-8'))
    note.write_text(change_field(5, 0, 'COURTAGE : SECRET-SYNTHETIC-CONTENT'))
    status = bd.main(['inspect', str(statement), '--input-root', str(tmp_path), '--max-bytes', '100000',
                      '--max-depth', '32', '--notes', str(note)])
    assert status == 1 and 'INVALID_DECIMAL' in caplog.text
    assert 'SECRET-SYNTHETIC-CONTENT' not in caplog.text
    assert 'private-sensitive-note' not in caplog.text

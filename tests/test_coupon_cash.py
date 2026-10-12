import copy
from datetime import date
from decimal import Decimal, localcontext
import json
import os
import socket

import pytest

import boursedirect_to_ghostfolio as bd
from test_contract_notes import coupon_source


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline coupon review must not connect')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def statement_html():
    columns = [
        ['', '17/09/2026', '', ''],
        ['Solde au : 31/08/2026', 'COUPONS SYNTHETIC GAMMA', 'Cumul mouvements :', 'Solde au : 30/09/2026'],
        ['', '', '', ''], ['', '1,90', '1,90', '1,90']]
    vectors = ''.join('<td><table>' + ''.join('<tr><td>' + x + '</td></tr>' for x in c) + '</table></td>' for c in columns)
    headers = ''.join('<td>' + h + '</td>' for h in bd.HEADERS)
    return ('<html><head><meta charset="utf-8"></head><body><strong>RELEVE DE COMPTE</strong><table><tr><td>COMPTE N°</td>'
            '<td>SYNTHETIC_ACCOUNT</td></tr></table><table><tr>' + headers + '</tr><tr>' + vectors + '</tr></table></body></html>')


def inputs():
    statement = bd.parse_statement(statement_html(), 32)
    doc = bd.parse_contract_note(coupon_source(), 32, include_coupons=True)
    statement['account_ref'] = doc['account_ref']
    statement['events'][0]['label'] = 'COUPONS ' + doc['notes'][0]['name']
    return statement, [doc]


def test_net_credit_booking_day_and_original_evidence_are_exact_without_inferred_tax():
    values = inputs()
    original = copy.deepcopy(values)
    result = bd.review_coupon_cash(*values)
    coupon = next(iter(result['coupons'].values()))
    assert coupon['kind'] == 'DIVIDEND' and coupon['amount'] == '1.9'
    assert coupon['operation_date'] == '2026-09-17' and coupon['date_basis'] == 'broker_booking_day'
    assert coupon['amount_basis'] == 'net_received' and coupon['currency'] == 'EUR'
    assert coupon['source_fields'] == {'quantity': '-3', 'unit_gross': '0.8', 'gross': '2.4', 'commission': '0.1'}
    assert coupon['withholding'] is None and coupon['tax_credit'] is None
    assert coupon['gross_semantics_verified'] is False and coupon['import_ready'] is False
    assert result['import_ready'] is False and values == original
    assert 'activities' not in result and 'quantity' not in coupon and 'unit_price' not in coupon


@pytest.mark.parametrize('mutation', ['duplicate-note', 'duplicate-event', 'missing-note', 'name', 'date', 'credit', 'account'])
def test_matching_requires_exact_source_name_date_cash_and_global_one_to_one(mutation):
    statement, docs = inputs()
    if mutation == 'duplicate-note': docs.append(copy.deepcopy(docs[0]))
    elif mutation == 'duplicate-event':
        statement['events'].append(copy.deepcopy(statement['events'][0]))
        statement['events'][-1]['slot'] = 2
        for c in statement['controls'][1:]: c['credit'] *= 2
    elif mutation == 'missing-note': docs[0]['notes'] = []
    elif mutation == 'name': docs[0]['notes'][0]['name'] = 'OTHER'
    elif mutation == 'date': docs[0]['notes'][0]['date'] = date(2026, 9, 16)
    elif mutation == 'credit': docs[0]['notes'][0]['credit'] += Decimal('0.01')
    else: docs[0]['account_ref'] = 'OTHER'
    with pytest.raises(RuntimeError): bd.review_coupon_cash(statement, docs)


@pytest.mark.parametrize('field,value', [
    ('quantity', Decimal(3)), ('credit', Decimal(0)), ('gross', Decimal('2.401')),
    ('commission', Decimal('-0.01')), ('unit_gross', Decimal('NaN')),
    ('net_currency', 'USD'), ('isin', 'FR0000000000'),
    ('tax_credit', Decimal('0.001')), ('tax_credit', Decimal('-0.01'))])
def test_changed_or_unsupported_financial_fields_refuse(field, value):
    statement, docs = inputs()
    docs[0]['notes'][0][field] = value
    with pytest.raises(RuntimeError): bd.review_coupon_cash(statement, docs)


def test_explicit_zero_tax_credit_is_preserved_not_withholding():
    statement, docs = inputs()
    docs[0]['notes'][0]['tax_credit'] = Decimal(0)
    coupon = next(iter(bd.review_coupon_cash(statement, docs)['coupons'].values()))
    assert coupon['tax_credit'] == '0' and coupon['withholding'] is None


def test_unknown_statement_or_note_keeps_entire_period_blocked():
    statement, docs = inputs()
    statement['events'].append({'date': date(2026, 9, 17), 'kind': 'UNKNOWN', 'label': 'DIVISION',
                                'slot': 5, 'debit': Decimal(0), 'credit': Decimal(0)})
    result = bd.review_coupon_cash(statement, docs)
    assert result['unsupported_statement_operations'] == 1
    assert 'UNSUPPORTED_OPERATION_PERIOD' in result['blockers'] and result['import_ready'] is False
    statement['events'].pop()
    docs[0]['notes'].append({'kind': 'UNKNOWN', 'date': date(2026, 9, 17)})
    assert 'UNSUPPORTED_OPERATION_PERIOD' in bd.review_coupon_cash(statement, docs)['blockers']


def test_changed_controls_or_outside_month_cannot_be_ignored():
    statement, docs = inputs()
    statement['controls'][-1]['credit'] += Decimal(1)
    with pytest.raises(RuntimeError, match='BALANCE_MISMATCH'): bd.review_coupon_cash(statement, docs)
    statement, docs = inputs()
    docs[0]['notes'][0]['date'] = date(2026, 10, 17)
    with pytest.raises(RuntimeError, match='OPERATION_OUTSIDE_STATEMENT_MONTH'): bd.review_coupon_cash(statement, docs)


def test_decimal_precision_does_not_round_large_source_cash():
    statement, docs = inputs()
    amount = Decimal('123456789012345678901234567890.19')
    docs[0]['notes'][0].update(credit=amount, gross=amount)
    statement['events'][0]['credit'] = amount
    for c in statement['controls'][1:]: c['credit'] = amount
    with localcontext() as ctx:
        ctx.prec = 6
        result = bd.review_coupon_cash(statement, docs)
    assert next(iter(result['coupons'].values()))['amount'] == str(amount)


def test_cli_private_report_safe_counts_repeat_and_collision_preservation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'inputs'
    source.mkdir()
    statement, docs = inputs()
    raw = statement_html().replace('SYNTHETIC_ACCOUNT', statement['account_ref']).replace('SYNTHETIC GAMMA', docs[0]['notes'][0]['name'])
    (source / 'statement.html').write_text(raw)
    (source / 'coupon.html').write_text(coupon_source())
    args = ['review-coupons', str(source / 'statement.html'), '--notes', str(source / 'coupon.html'),
            '--input-root', str(source), '--output', 'outputs/coupons.yaml', '--max-bytes', '100000', '--max-depth', '32']
    assert bd.main(args) == 2
    output = capsys.readouterr().out
    assert json.loads(output)['coupons'] == 1
    assert '1.9' not in output and statement['account_ref'] not in output and docs[0]['notes'][0]['isin'] not in output
    report = (tmp_path / 'outputs/coupons.yaml').read_bytes()
    assert os.stat(tmp_path / 'outputs/coupons.yaml').st_mode & 0o777 == 0o600
    assert bd.main(args) == 2 and (tmp_path / 'outputs/coupons.yaml').read_bytes() == report
    capsys.readouterr()
    # Hard-link collision inside outputs must preserve both source and previous report.
    os.link(source / 'coupon.html', tmp_path / 'outputs/collision.yaml')
    args[args.index('outputs/coupons.yaml')] = 'outputs/collision.yaml'
    before = (source / 'coupon.html').read_bytes()
    assert bd.main(args) == 1
    assert (source / 'coupon.html').read_bytes() == before and (tmp_path / 'outputs/coupons.yaml').read_bytes() == report


def test_source_cash_artifact_cannot_enter_existing_trade_import_path():
    result = bd.review_coupon_cash(*inputs())
    with pytest.raises(RuntimeError): bd.validated_prepared_review(bd.yaml.safe_dump(result).encode())
    with pytest.raises(RuntimeError): bd.build_wire_payload(result['coupons'])

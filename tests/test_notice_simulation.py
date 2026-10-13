"""Task 3.2: observed financial forms with all personal fields removed."""
import copy
import json
from datetime import date
from decimal import localcontext
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

import boursedirect_to_ghostfolio as connector
from test_buy_simulation import ACCOUNT, MAPPING, real_buy


def notice(name, transform=lambda html: html):
    raw = (Path(__file__).parent / 'fixtures' / name).read_text()
    raw = connector.decode_document(transform(raw).encode())
    return connector.parse_contract_note(raw, 16, include_coupons=True,
        skip_missing_isin=True, notice_sync=True)


@pytest.mark.parametrize('name,expected', [
    ('note-sell-anonymized-real.html', [
        ('SELL', '2026-09-23', '90', '11.6', '2.9'),
        ('SELL', '2026-09-23', '100', '17.65', '2.9')]),
    ('note-foreign-sell-anonymized-real.html', [
        ('SELL', '2026-07-01', '47', '24.02', '5.64')]),
    ('note-coupon-anonymized-real.html', [
        ('DIVIDEND', '2026-07-02', '1', '4.86', '0'),
        ('DIVIDEND', '2026-07-02', '1', '12', '0'),
        ('BUY', '2026-07-02', '1', '1988.4', '2.9'),
        ('BUY', '2026-07-02', '180', '5.309', '1.9')]),
    ('note-corporate-anonymized-real.html', [
        ('DIVIDEND', '2026-07-09', '1', '10', '0')])])
def test_observed_forms_keep_exact_amounts_row_dates_and_net_coupon(name, expected):
    document = notice(name)
    original = copy.deepcopy(document)
    failures, skipped = [], []
    with localcontext() as context:
        context.prec = 4
        proposals = connector.simulate_buy_notice(document, ACCOUNT, MAPPING,
            failures=failures, skipped=skipped)
    assert proposals == [dict(type=kind, date=day + 'T00:00:00.000Z',
        isin='FR0000000002', symbol='VERIFIED.PA', currency='EUR',
        quantity=quantity, unitPrice=price, fee=fee)
        for kind, day, quantity, price, fee in expected]
    assert failures == []
    assert document == original


@pytest.mark.parametrize('operation', ['DROITS DE GARDE', 'TAXE TRANSACT FINANCIERES',
    'DIVISION', 'DET DROIT DE SOUSCRIPTION', 'RETRAIT TITRES FISCALISE',
    'TRANSFERT VALEUR', 'INVESTISSEMENT ESPECES'])
@pytest.mark.parametrize('missing_isin', [False, True])
def test_known_exclusions_log_one_error_and_succeed(operation, missing_isin, capsys):
    document = notice('note-corporate-anonymized-real.html')
    row = document['notes'][1]
    row['source_kind'] = operation
    if missing_isin:
        row['isin'] = None
    document['notes'] = [row]
    failures, skipped = [], []
    assert connector.simulate_buy_notice(document, ACCOUNT, {},
        resolver=lambda isin: pytest.fail('excluded row must not resolve'),
        failures=failures, skipped=skipped) == []
    assert failures == [] and skipped == ['NOTICE_OUT_OF_SCOPE']
    assert json.loads(capsys.readouterr().out)['run_failed'] is False


def test_missing_isin_trade_and_coupon_are_skipped_without_lookup(capsys):
    document = notice('note-coupon-anonymized-real.html',
        lambda html: html.replace('FR0000000002', ''))
    failures, skipped = [], []
    assert connector.simulate_buy_notice(document, ACCOUNT, {},
        resolver=lambda isin: pytest.fail('no-ISIN row must not resolve'),
        failures=failures, skipped=skipped) == []
    assert not failures and skipped == ['NOTICE_NO_ISIN'] * 4
    assert len(capsys.readouterr().out.splitlines()) == 4


@pytest.mark.parametrize('missing_isin', [False, True])
@pytest.mark.parametrize('fault,code', [('unknown', 'NOTICE_UNKNOWN_OPERATION'),
    ('currency', 'NOTICE_CURRENCY_UNPROVED'), ('vat', 'NOTICE_NONZERO_TVA')])
def test_financial_errors_precede_no_isin_and_continue_valid_rows(fault, code, missing_isin, capsys):
    document = real_buy()
    row = copy.deepcopy(document['notes'][0])
    if missing_isin:
        row['isin'] = None
    if fault == 'unknown':
        row.update(kind='UNKNOWN', source_kind='UNSEEN OPERATION')
    elif fault == 'currency':
        row['net_currency'] = None
    else:
        row['vat'] = connector.Decimal('0.01')
    document['notes'].insert(0, row)
    failures, skipped = [], []
    assert len(connector.simulate_buy_notice(document, ACCOUNT, MAPPING,
        failures=failures, skipped=skipped)) == 1
    assert failures == skipped == [code]
    log = json.loads(capsys.readouterr().out)
    assert log['code'] == code and log['run_failed'] is True


@pytest.mark.parametrize('currency', ['USD', '', 'EUR'])
def test_headers_without_observed_euro_symbol_do_not_prove_currency(currency):
    transform = lambda html: html.replace('Débit (€)', 'Débit' + (f' ({currency})' if currency else ''))
    document = notice('note-sell-anonymized-real.html', transform)
    failures = []
    assert connector.simulate_buy_notice(document, ACCOUNT, MAPPING, failures=failures) == []
    assert failures == ['NOTICE_CURRENCY_UNPROVED'] * 2


def test_unknown_without_isin_is_not_hidden_by_parser():
    document = notice('note-corporate-anonymized-real.html', lambda html:
        html.replace('DIVISION', 'UNSEEN OPERATION').replace('FR0000000002', ''))
    failures = []
    connector.simulate_buy_notice(document, ACCOUNT, MAPPING, failures=failures)
    assert failures == ['NOTICE_UNKNOWN_OPERATION'] * 2


@pytest.mark.parametrize('vat,credits', [('+0,01', {'1041,10': '1041,09', '1762,10': '1762,09'}),
    ('-0,01', {'1041,10': '1041,11', '1762,10': '1762,11'})])
def test_nonzero_vat_without_isin_is_retained_by_parser(vat, credits):
    def transform(html):
        soup = BeautifulSoup(html.replace('FR0000000002', ''), 'html.parser')
        for node in soup.find_all('font'):
            if connector.text(node).startswith('TVA :'):
                node.string = 'TVA : ' + vat
            elif connector.text(node).replace(' ', '') in ('1041,10', '1762,10'):
                node.string = credits[connector.text(node).replace(' ', '')]
        return str(soup)
    document = notice('note-sell-anonymized-real.html', transform)
    failures = []
    connector.simulate_buy_notice(document, ACCOUNT, MAPPING, failures=failures)
    assert failures == ['NOTICE_NONZERO_TVA'] * 2


def test_generic_out_of_scope_vat_still_fails():
    document = notice('note-corporate-anonymized-real.html')
    document['notes'] = document['notes'][1:]
    for row in document['notes']:
        row['source_fields'].append(['TVA : +0,01', '', ''])
    failures = []
    connector.simulate_buy_notice(document, ACCOUNT, MAPPING, failures=failures)
    assert failures == ['NOTICE_NONZERO_TVA'] * 2


def test_sync_uses_each_row_date_even_with_different_notice_header_or_other_rows():
    def transform(html):
        soup = BeautifulSoup(html, 'html.parser')
        ledger = connector.contract_note_ledger(soup)
        column = connector.cells(connector.direct_rows(ledger)[1])[0].find('table', recursive=False)
        second = connector.cells(connector.direct_rows(column)[10])[0]
        second.string = '24/09/2026'
        return str(soup).replace("<body>", '<body><p>Notice date: 25/09/2026</p>')
    document = notice('note-sell-anonymized-real.html', transform)
    rows = connector.simulate_buy_notice(document, ACCOUNT, MAPPING)
    assert [row['date'] for row in rows] == ['2026-09-23T00:00:00.000Z', '2026-09-24T00:00:00.000Z']
    assert document['notes'][1]['date'] == date(2026, 9, 24)

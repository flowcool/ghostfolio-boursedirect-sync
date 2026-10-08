import copy
from datetime import date
from decimal import Decimal
from pathlib import Path
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_contract_notes import document, paired_statement


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def inputs():
    statement = bd.parse_statement(paired_statement(), 32)
    docs = [document(), document(True)]
    account = {'source_account_ref': statement['account_ref'], 'account_key': 'synthetic-owned-account',
               'target_account_id': 'synthetic-ghostfolio-account'}
    mappings = {n['isin']: {'symbol': symbol, 'data_source': 'YAHOO', 'execution_price_currency': 'EUR',
                           'target_currency': 'EUR', 'currency_evidence': 'synthetic operator confirmation',
                           'target_security_evidence': 'synthetic verified target profile'}
                for n, symbol in zip([d['notes'][0] for d in docs] + [docs[1]['notes'][1]],
                                     ['SYNTHG.PA', 'SYNTHA.BR', 'SYNTHB.PA'])}
    return statement, docs, account, mappings


def test_strict_trades_have_positive_quantity_exact_costs_and_private_internal_dates():
    records = bd.convert_matched_trades(*inputs())
    assert [r['kind'] for r in records] == ['SELL', 'SELL', 'BUY']
    assert [r['quantity'] for r in records] == [Decimal('2'), Decimal('5'), Decimal('3')]
    assert [r['fee'] for r in records] == [Decimal('0.20'), Decimal('0.35'), Decimal('0.45')]
    assert all(r['operation_date'] == date(2026, 9, 17) for r in records)
    assert all(r['price_currency'] == 'EUR' and r['net_currency'] == 'EUR' for r in records)
    assert all(r['target_account_id'] == 'synthetic-ghostfolio-account' for r in records)
    assert all(r['import_ready'] is False and 'id' not in r and 'date' not in r for r in records)
    assert records[0]['execution_time'] == '10:00:00'
    assert records[1]['gross'] == Decimal('35') and records[1]['net'] == Decimal('34.65')
    assert all(isinstance(r['unit_price'], Decimal) for r in records)


def test_no_inputs_are_mutated_and_no_output_is_printed(capsys):
    values = inputs()
    before = copy.deepcopy(values)
    bd.convert_matched_trades(*values)
    assert before == values
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('key,value,error', [
    ('symbol', '', 'SECURITY_MAPPING_UNVERIFIED'),
    ('symbol', 'RAW PRIVATE NAME WITH SPACES', 'INVALID_TARGET_SYMBOL'),
    ('currency_evidence', None, 'SECURITY_MAPPING_UNVERIFIED'),
    ('target_security_evidence', '', 'SECURITY_MAPPING_UNVERIFIED'),
    ('data_source', 'MANUAL', 'UNSUPPORTED_TARGET_DATA_SOURCE'),
    ('execution_price_currency', None, 'SECURITY_CURRENCY_CONFLICT'),
    ('target_currency', 'USD', 'SECURITY_CURRENCY_CONFLICT'),
])
def test_mapping_and_currency_evidence_required_for_every_isin(key, value, error):
    statement, docs, account, mappings = inputs()
    mappings[docs[0]['notes'][0]['isin']][key] = value
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_missing_mapping_blocks_entire_period_not_partial_success():
    statement, docs, account, mappings = inputs()
    del mappings[docs[0]['notes'][0]['isin']]
    with pytest.raises(RuntimeError, match='SECURITY_MAPPING_MISSING'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_foreign_currency_not_synthesized_from_matching_numbers():
    statement, docs, account, mappings = inputs()
    for mapping in mappings.values():
        mapping.update(execution_price_currency='USD', target_currency='USD')
    with pytest.raises(RuntimeError, match='UNVERIFIED_FX_SEMANTICS'):
        bd.convert_matched_trades(statement, docs, account, mappings)


@pytest.mark.parametrize('key', ['source_account_ref', 'account_key', 'target_account_id'])
def test_explicit_account_configuration_required(key):
    statement, docs, account, mappings = inputs()
    del account[key]
    with pytest.raises(RuntimeError, match='ACCOUNT_CONFIGURATION_MISSING'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_source_account_cannot_be_routed_by_filename_or_note():
    statement, docs, account, mappings = inputs()
    account['source_account_ref'] = 'UNEXPECTED_ACCOUNT'
    with pytest.raises(RuntimeError, match='SOURCE_ACCOUNT_MISMATCH'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_unsupported_operation_blocks_period_even_if_trades_match():
    statement, docs, account, mappings = inputs()
    statement['events'].append({'kind': 'UNKNOWN', 'label': 'COUPONS', 'debit': Decimal(0), 'credit': Decimal(0)})
    with pytest.raises(RuntimeError, match='UNSUPPORTED_OPERATION_PERIOD'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_missing_or_duplicate_notes_do_not_create_partial_activities():
    statement, docs, account, mappings = inputs()
    for invalid in [docs[:1], docs + [copy.deepcopy(docs[0])]]:
        with pytest.raises(RuntimeError, match='NOTE_MATCHING_NOT_COMPLETE'):
            bd.convert_matched_trades(statement, invalid, account, mappings)


@pytest.mark.parametrize('mutation,error', [('vat','UNVERIFIED_VAT_TREATMENT'),
                                           ('gross','NOTE_GROSS_MISMATCH'),
                                           ('brokerage','NOTE_NET_MISMATCH'),
                                           ('price_currency','SOURCE_PRICE_CURRENCY_CONFLICT')])
def test_conversion_rechecks_internal_note_financial_evidence(mutation, error):
    statement, docs, account, mappings = inputs()
    note = docs[0]['notes'][0]
    note[mutation] = 'USD' if mutation == 'price_currency' else note[mutation] + Decimal('0.01')
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_bad_buy_sign_is_not_repaired_by_absolute_value():
    statement, docs, account, mappings = inputs()
    statement['events'][-1]['quantity'] = Decimal('-3')
    with pytest.raises(RuntimeError, match='TRADE_DIRECTION_CONFLICT'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_cash_controls_are_revalidated_before_activity_conversion():
    statement, docs, account, mappings = inputs()
    statement['controls'][-1]['credit'] += Decimal('1')
    with pytest.raises(RuntimeError, match='BALANCE_MISMATCH'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_internal_note_sign_conflict_not_hidden_by_absolute_matching():
    statement, docs, account, mappings = inputs()
    docs[0]['notes'][0]['quantity'] = Decimal('-3')
    with pytest.raises(RuntimeError, match='NOTE_QUANTITY_SIGN_CONFLICT'):
        bd.convert_matched_trades(statement, docs, account, mappings)


def test_outside_period_dates_block_even_with_matching_notes():
    statement, docs, account, mappings = inputs()
    statement['events'][-1]['date'] = date(2026, 10, 1)
    docs[0]['notes'][0]['date'] = date(2026, 10, 1)
    with pytest.raises(RuntimeError, match='OPERATION_OUTSIDE_STATEMENT_MONTH'):
        bd.convert_matched_trades(statement, docs, account, mappings)

import copy
from decimal import Decimal
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_contract_notes import paired_statement

ACCOUNT = '3a5d9909-b311-4412-96b4-a0df15861530'
OTHER = 'a2c45ef7-0a84-481d-9f4e-0862e44ea26f'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def statement():
    return bd.parse_statement(paired_statement(), 32)


def empty():
    return {'schema_version': 1, 'accounts': {}}


def test_original_facts_own_stable_account_namespaced_ids():
    original = statement()
    before = copy.deepcopy(original)
    result = bd.ledger_identity(original, ACCOUNT)
    assert len(result['events']) == 3
    assert len({e['id'] for e in result['events']}) == 3
    assert all(e['id'].startswith('BD#v1#' + ACCOUNT + '#') for e in result['events'])
    assert all(len(e['id']) == 107 for e in result['events'])
    assert result == bd.ledger_identity(original, ACCOUNT)
    assert before == original
    other = bd.ledger_identity(original, OTHER)
    assert set(e['id'] for e in other['events']).isdisjoint(e['id'] for e in result['events'])


def test_row_order_blank_slots_decimal_format_and_enrichment_do_not_change_identity():
    original = statement()
    altered = copy.deepcopy(original)
    altered['events'].reverse()
    for i, event in enumerate(altered['events']):
        event['slot'] = 4 + i
        event.update(symbol='CHANGED.PA', isin='IGNORED', execution_time='23:00:00', filename='other.html')
        for key in ['quantity', 'unit_price', 'debit', 'credit']:
            event[key] = Decimal(str(event[key]) + ('00' if '.' in str(event[key]) else '.000'))
    a = bd.ledger_identity(original, ACCOUNT)
    b = bd.ledger_identity(altered, ACCOUNT)
    assert a['fingerprint'] == b['fingerprint']
    assert sorted(e['id'] for e in a['events']) == sorted(e['id'] for e in b['events'])


def update_controls(source):
    opening, cumulative, closing = source['controls']
    debits = sum((e['debit'] for e in source['events']), Decimal(0))
    credits = sum((e['credit'] for e in source['events']), Decimal(0))
    cumulative.update(debit=opening['debit'] + debits, credit=opening['credit'] + credits)
    net = opening['credit'] - opening['debit'] + credits - debits
    closing.update(debit=-net if net < 0 else Decimal(0), credit=net if net > 0 else Decimal(0))


def test_identical_trades_keep_distinct_occurrences_and_multiplicity_revision_blocks():
    original = statement()
    altered = copy.deepcopy(original)
    altered['events'].insert(1, copy.deepcopy(altered['events'][0]))
    altered['events'][1]['slot'] = 3
    update_controls(altered)
    a = bd.ledger_identity(original, ACCOUNT)
    b = bd.ledger_identity(altered, ACCOUNT)
    assert len(b['events']) == 4 and len({e['id'] for e in b['events']}) == 4
    assert [e['occurrence'] for e in b['events'][:2]] == [1, 2]
    journal = bd.register_statement_snapshot(empty(), a)
    with pytest.raises(RuntimeError, match='STATEMENT_REVISION_CONFLICT'):
        bd.register_statement_snapshot(journal, b)
    assert len(journal['accounts'][ACCOUNT]) == 1


@pytest.mark.parametrize('key,value', [('unit_price', Decimal('13')), ('quantity', Decimal('-3')),
                                     ('credit', Decimal('23.81')), ('label', 'VTE CPT CORRECTED')])
def test_changed_financial_fact_is_revision_not_new_automatic_import(key, value):
    original = statement()
    altered = copy.deepcopy(original)
    altered['events'][0][key] = value
    update_controls(altered)
    a = bd.ledger_identity(original, ACCOUNT)
    b = bd.ledger_identity(altered, ACCOUNT)
    assert a['fingerprint'] != b['fingerprint']
    journal = bd.register_statement_snapshot(empty(), a)
    with pytest.raises(RuntimeError, match='STATEMENT_REVISION_CONFLICT'):
        bd.register_statement_snapshot(journal, b)


def test_equivalent_reimport_returns_equal_journal_without_mutation():
    snapshot = bd.ledger_identity(statement(), ACCOUNT)
    journal = bd.register_statement_snapshot(empty(), snapshot)
    before = copy.deepcopy(journal)
    assert bd.register_statement_snapshot(journal, snapshot) == journal
    assert before == journal
    second = bd.register_statement_snapshot(journal, bd.ledger_identity(statement(), OTHER))
    assert len(second['accounts']) == 2 and len(journal['accounts']) == 1


@pytest.mark.parametrize('key', ['', 'ACTUAL_ACCOUNT_NUMBER', ACCOUNT.upper(), '00000000-0000-0000-0000-000000000000', None])
def test_account_namespace_cannot_be_private_account_ref_or_noncanonical_uuid(key):
    with pytest.raises(RuntimeError, match='INVALID_IMMUTABLE_ACCOUNT_KEY'):
        bd.ledger_identity(statement(), key)


@pytest.mark.parametrize('value', [Decimal('NaN'), Decimal('Infinity'), '1.00'])
def test_nonfinite_or_non_decimal_facts_rejected(value):
    with pytest.raises(RuntimeError, match='INVALID_IDENTITY_DECIMAL'):
        bd.canonical_decimal(value)


@pytest.mark.parametrize('value,expected', [(Decimal('-0.00'), '0'), (Decimal('1000.00'), '1000'),
                                          (Decimal('0.00100'), '0.001'), (Decimal('1E+5'), '100000')])
def test_decimal_normalization_never_rounds_or_changes_integer_zeros(value, expected):
    assert bd.canonical_decimal(value) == expected


def test_unknown_and_boundary_mismatches_are_not_silently_owned():
    source = statement()
    source['events'][0]['kind'] = 'UNKNOWN'
    with pytest.raises(RuntimeError, match='UNSUPPORTED_OPERATION_PERIOD'):
        bd.ledger_identity(source, ACCOUNT)
    source = statement()
    source['period'] = '2026-10'
    with pytest.raises(RuntimeError, match='OPERATION_OUTSIDE_STATEMENT_MONTH'):
        bd.ledger_identity(source, ACCOUNT)


def test_normalization_version_change_blocks_existing_period():
    snapshot = bd.ledger_identity(statement(), ACCOUNT)
    journal = bd.register_statement_snapshot(empty(), snapshot)
    journal['accounts'][ACCOUNT][snapshot['period']]['normalization_version'] = 0
    with pytest.raises(RuntimeError, match='STATEMENT_REVISION_CONFLICT'):
        bd.register_statement_snapshot(journal, snapshot)
    snapshot['normalization_version'] = 2
    with pytest.raises(RuntimeError, match='IDENTITY_VERSION_CONFLICT'):
        bd.register_statement_snapshot(empty(), snapshot)

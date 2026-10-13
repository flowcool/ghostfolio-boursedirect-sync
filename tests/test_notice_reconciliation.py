"""Exact reconciliation from anonymized real financial notice fields, offline."""
import copy
import json
from decimal import Decimal, localcontext

import pytest

import boursedirect_to_ghostfolio as b
from test_buy_simulation import real_buy, MAPPING


ACCOUNT = {'source_account_ref': 'SYNTHETIC001 PEA', 'target_account_id': 'synthetic-destination'}


def proposals(document=None):
    return b.simulate_buy_notice(document or real_buy(), ACCOUNT, MAPPING, occurrences={})


def remote(proposal, marker=True, **changes):
    row = {'id': 'synthetic-activity', 'accountId': proposal['accountId'],
        'account': {'id': proposal['accountId'], 'tags': []}, 'tags': [],
        'type': proposal['type'], 'date': proposal['date'], 'currency': 'EUR',
        'comment': proposal['comment'] if marker else None,
        'quantity': Decimal(proposal['quantity']), 'unitPrice': Decimal(proposal['unitPrice']),
        'fee': Decimal(proposal['fee']), 'assetProfile': {'symbol': proposal['symbol'],
            'currency': 'EUR', 'dataSource': 'YAHOO'}}
    row.update(changes)
    # Numeric strings are never substituted for Ghostfolio's numeric JSON fields.
    raw = json.dumps({'count': 1, 'activities': [row]}, default=lambda n: 'DECIMAL:' + str(n))
    import re
    raw = re.sub(r'"DECIMAL:([-0-9.]+)"', r'\1', raw)
    return b.parse_remote_activity_snapshot(raw.encode())[0]


def test_owned_exact_repeat_proposes_nothing_and_has_no_side_effect():
    pending = proposals()
    original = copy.deepcopy(pending)
    assert b.reconcile_notice_duplicates(pending, [remote(pending[0])]) == ([], 1)
    assert pending == original


@pytest.mark.parametrize('field,value', [('quantity', 13), ('unitPrice', 9), ('fee', 2),
    ('date', '2019-02-07T00:00:00.000Z'), ('currency', 'USD'), ('isDraft', True)])
def test_changed_owned_identity_fails(field, value):
    pending = proposals()
    with pytest.raises(RuntimeError, match='NOTICE_OWNED_ACTIVITY_CONFLICT'):
        b.reconcile_notice_duplicates(pending, [remote(pending[0], **{field: value})])


def test_owned_wrong_account_or_duplicate_identity_fails():
    pending = proposals()
    row = remote(pending[0])
    other = dict(row, target_account_id='other')
    for rows in ([other], [row, dict(row, remote_id='second')]):
        with pytest.raises(RuntimeError, match='NOTICE_IDENTITY_OWNERSHIP_CONFLICT'):
            b.reconcile_notice_duplicates(pending, rows)


def test_identity_ignores_mapping_capture_location_and_preserves_occurrences():
    document = real_buy()
    first = proposals(document)[0]
    document['notes'][0].update(name='another label', venue='another venue', slot=999)
    assert proposals(document)[0]['comment'] == first['comment']
    different = b.simulate_buy_notice(document, ACCOUNT,
        {'FR0000000002': {'symbol': 'OTHER.PA', 'currency': 'EUR'}}, occurrences={})[0]
    assert different['comment'] == first['comment']
    document['notes'].append(copy.deepcopy(document['notes'][0]))
    both = proposals(document)
    assert len({p['comment'] for p in both}) == 2
    assert b.reconcile_notice_duplicates(both, [remote(both[0])]) == ([both[1]], 1)
    assert b.reconcile_notice_duplicates(both, [remote(both[0]), remote(both[1], id='second')]) == ([], 2)
    different_account = b.simulate_buy_notice(document, dict(ACCOUNT, target_account_id='other'), MAPPING, occurrences={})
    assert {p['comment'] for p in both}.isdisjoint(p['comment'] for p in different_account)


def test_pending_duplicate_identity_is_never_silently_collapsed():
    pending = proposals()
    with pytest.raises(RuntimeError, match='NOTICE_PENDING_IDENTITY_CONFLICT'):
        b.reconcile_notice_duplicates(pending * 2, [])


def test_manual_exact_match_consumes_once_and_never_changes_comment():
    pending = proposals()
    row = remote(pending[0], marker=False)
    assert b.reconcile_notice_duplicates(pending, [row]) == ([], 1)
    assert row['comment'] is None


@pytest.mark.parametrize('field,value', [('quantity', 13), ('unitPrice', 9), ('fee', 2),
    ('date', '2019-02-05T23:00:00.000Z'), ('isDraft', True)])
def test_manual_nearby_difference_is_ambiguous(field, value):
    pending = proposals()
    with pytest.raises(RuntimeError, match='NOTICE_MANUAL_OVERLAP_AMBIGUOUS'):
        b.reconcile_notice_duplicates(pending, [remote(pending[0], marker=False, **{field: value})])


def test_manual_multiplicity_requires_exact_group_count():
    document = real_buy()
    document['notes'] *= 2
    pending = proposals(document)
    row = remote(pending[0], marker=False)
    with pytest.raises(RuntimeError, match='NOTICE_MANUAL_OVERLAP_AMBIGUOUS'):
        b.reconcile_notice_duplicates(pending, [row])
    assert b.reconcile_notice_duplicates(pending, [row, dict(row, remote_id='second')]) == ([], 2)
    with pytest.raises(RuntimeError, match='NOTICE_MANUAL_OVERLAP_AMBIGUOUS'):
        b.reconcile_notice_duplicates(pending[:1], [row, dict(row, remote_id='second')])


def test_other_account_same_financial_fields_does_not_deduplicate_or_fund_sell():
    pending = proposals()
    row = dict(remote(pending[0], marker=False), target_account_id='other')
    assert b.reconcile_notice_duplicates(pending, [row]) == (pending, 0)
    sell = dict(pending[0], type='SELL', quantity='1')
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([sell], [row])


def test_insufficient_50_with_10_stops_all_proposals_and_logs_both_quantities(capsys):
    buy = proposals()[0]
    sell = dict(buy, type='SELL', quantity='50')
    baseline = remote(buy, marker=False, quantity=10, date='2018-01-01T00:00:00.000Z')
    later_buy = dict(buy, quantity='100', execution_time='23:59:59')
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([later_buy, sell], [baseline])
    log = json.loads(capsys.readouterr().out)
    assert (log['available'], log['sale'], log['financial_writes'], log['imported']) == ('10', '50', 0, 0)


def test_only_preceding_buys_fund_projection_and_submitted_buys_never_fund_dispatch():
    buy = dict(proposals()[0], quantity='50', execution_time='09:00:00')
    sell = dict(buy, type='SELL', execution_time='10:00:00', comment=buy['comment'] + 'sell')
    assert b.reconcile_notice_holdings([sell, buy], []) == [buy, sell]
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([buy, sell], [], project_buys=False)
    # The readback-confirmed BUY is then available from the baseline itself.
    confirmed = remote(buy)
    assert b.reconcile_notice_holdings([sell], [confirmed], project_buys=False) == [sell]
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([dict(buy, execution_time='11:00:00'), sell], [])


def test_duplicate_and_skipped_buys_cannot_double_fund_sales():
    buy = dict(proposals()[0], quantity='10')
    sell = dict(buy, type='SELL', quantity='15', comment=buy['comment'] + 'sell')
    row = remote(buy)
    pending, duplicates = b.reconcile_notice_duplicates([buy, sell], [row])
    assert duplicates == 1 and pending == [sell]
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings(pending, [row])
    document = real_buy()
    document['notes'][0]['vat'] = Decimal('.01')
    assert proposals(document) == []
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([sell], [row])


def test_baseline_uses_net_active_trades_only_and_exact_decimals():
    buy = dict(proposals()[0], quantity='1000000000000000000000000000.0001')
    baseline = remote(buy)
    sale = dict(baseline, remote_id='sale', kind='SELL', quantity=Decimal('1000000000000000000000000000'))
    excluded = dict(baseline, remote_id='draft', active=False)
    dividend = dict(baseline, remote_id='coupon', kind='DIVIDEND')
    sell = dict(buy, type='SELL', quantity='.0001')
    with localcontext() as context:
        context.prec = 4
        assert b.reconcile_notice_holdings([sell], [baseline, sale, excluded, dividend]) == [sell]


@pytest.mark.parametrize('change', [{'financial_context_verified': False}, {'price_currency': 'USD'},
    {'data_source': 'MANUAL'}])
def test_unsupported_target_holdings_refuse(change):
    buy = proposals()[0]
    with pytest.raises(RuntimeError, match='NOTICE_HOLDINGS_CONTEXT_UNVERIFIED'):
        b.reconcile_notice_holdings([buy], [dict(remote(buy), **change)])


@pytest.mark.parametrize('change', [{'data_source': 'MANUAL'}, {'price_currency': 'USD'},
    {'financial_context_verified': False}])
def test_unrelated_holdings_context_does_not_block_a_proposal(change):
    buy = proposals()[0]
    unrelated = dict(remote(buy), symbol='00000000-0000-4000-8000-000000000002', **change)
    assert b.reconcile_notice_holdings([buy], [unrelated]) == [buy]


def test_multiple_isins_cannot_share_one_holdings_symbol():
    buy = proposals()[0]
    with pytest.raises(RuntimeError, match='NOTICE_SYMBOL_ISIN_CONFLICT'):
        b.reconcile_notice_holdings([buy, dict(buy, isin='FR0000000010')], [])


@pytest.mark.parametrize('raw,code', [(b'{"count":1,"activities":[]}', 'REMOTE_ACTIVITY_COUNT_MISMATCH'),
    (b'{"activities":[]}', 'REMOTE_ACTIVITY_COUNT_MISMATCH')])
def test_incomplete_destination_read_refuses(raw, code):
    with pytest.raises(RuntimeError, match=code):
        b.parse_remote_activity_snapshot(raw)


def test_redacted_numeric_destination_refuses():
    with pytest.raises(RuntimeError, match='REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED'):
        remote(proposals()[0], quantity=None)

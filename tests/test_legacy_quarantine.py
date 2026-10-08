import copy
from datetime import timedelta
from decimal import Decimal
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_adoption import prepared, row, snapshot, resolution


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def case():
    marker, activity = next(iter(prepared().items()))
    remote = row(activity)
    remote['fee'] += 1
    return {marker: activity}, remote


@pytest.mark.parametrize('days', [-2, -1, 0, 1, 2])
@pytest.mark.parametrize('serialized', [False, True])
def test_inclusive_calendar_bounds_and_prepared_value_forms(days, serialized):
    plan, remote = case()
    activity = next(iter(plan.values()))
    remote['date'] = (activity['operation_date'] + timedelta(days=days)).isoformat() + 'T13:14:15.123Z'
    if serialized:
        activity['operation_date'] = activity['operation_date'].isoformat()
        for key in ('quantity', 'unit_price'):
            value = str(activity[key])
            activity[key] = value + ('00' if '.' in value else '.00')
    # Equivalent Decimal scales must not conceal an existing candidate.
    if abs(days) <= 1:
        with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
            bd.reconcile_existing_activities(plan, snapshot([remote]), {})
    else:
        assert bd.reconcile_existing_activities(plan, snapshot([remote]), {})['new'] == list(plan)


@pytest.mark.parametrize('offset,clock', [('+02:00', '00:30:00'), ('-02:00', '23:30:00')])
def test_offset_timestamp_crossing_utc_midnight_blocks(offset, clock):
    plan, remote = case()
    remote['date'] = next(iter(plan.values()))['operation_date'].isoformat() + 'T' + clock + offset
    with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
        bd.reconcile_existing_activities(plan, snapshot([remote]), {})


@pytest.mark.parametrize('context', ['currency', 'fx', 'draft', 'excluded', 'foreign_owner'])
def test_eligibility_and_currency_cannot_erase_duplicate_evidence(context):
    plan, remote = case()
    if context == 'currency':
        remote['currency'] = remote['assetProfile']['currency'] = 'USD'
    elif context == 'fx':
        remote['currency'] = 'USD'
    elif context == 'draft':
        remote['isDraft'] = True
    elif context == 'excluded':
        remote['account']['isExcluded'] = True
    else:
        remote['comment'] = 'BD#foreign-owner'
    with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
        bd.reconcile_existing_activities(plan, snapshot([remote]), {})


@pytest.mark.parametrize('field', ['account', 'symbol', 'source', 'type', 'quantity', 'price'])
def test_unrelated_identity_or_financial_values_remain_outside_guard(field):
    plan, remote = case()
    if field == 'account':
        remote['accountId'] = remote['account']['id'] = 'another-account'
    elif field == 'symbol':
        remote['assetProfile']['symbol'] = 'ANOTHER'
    elif field == 'source':
        remote['assetProfile']['dataSource'] = 'OTHER'
    elif field == 'type':
        remote['type'] = 'SELL' if remote['type'] == 'BUY' else 'BUY'
    elif field == 'quantity':
        remote['quantity'] += 1
    else:
        remote['unitPrice'] += 1
    assert bd.reconcile_existing_activities(plan, snapshot([remote]), {})['new'] == list(plan)


@pytest.mark.parametrize('reverse', [False, True])
def test_claimed_candidate_cannot_hide_second_changed_fee_source(reverse):
    marker, first = next(iter(prepared().items()))
    second = copy.deepcopy(first)
    second['id'] = 'another-source-occurrence'
    second['fee'] += Decimal('1')
    items = [(marker, first), (second['id'], second)]
    if reverse:
        items.reverse()
    with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
        bd.reconcile_existing_activities(dict(items), snapshot([row(first)]), {marker: resolution(first)})


def test_nonmidnight_exact_fee_preserves_existing_context_rejection():
    marker, first = next(iter(prepared().items()))
    remote = row(first)
    remote['date'] = first['operation_date'].isoformat() + 'T13:14:15.123Z'
    with pytest.raises(RuntimeError, match='^REMOTE_CANDIDATE_CONTEXT_UNVERIFIED$'):
        bd.reconcile_existing_activities({marker: first}, snapshot([remote]), {})

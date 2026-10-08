import copy
from datetime import date
from decimal import Decimal
import hashlib
import json
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_adoption import prepared, row, resolution


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def acquired(plan, day='2026-09-01'):
    rows = []
    for i, a in enumerate(plan.values()):
        if a['kind'] == 'SELL':
            buy = row(a, 'prior-buy-' + str(i))
            buy['type'], buy['date'] = 'BUY', day + 'T00:00:00.000Z'
            rows.append(buy)
    return rows


def check(plan, rows, resolutions=None, evidence=None):
    raw = json.dumps({'count': len(rows), 'activities': rows})
    if evidence is None:
        evidence = {'kind': 'complete_acquisition_history', 'snapshot_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                    'target_account_id': next(iter(plan.values()))['target_account_id'],
                    'confirmed_by': 'synthetic-operator', 'reference': 'synthetic-history-proof'}
    return bd.verify_chronological_holdings(plan, raw, resolutions or {}, evidence)


def test_prior_acquisitions_cover_sales_exactly_without_granting_readiness():
    plan = prepared()
    before = copy.deepcopy(plan)
    result = check(plan, acquired(plan))
    assert result['coverage_verified'] and not result['shortages'] and result['import_ready'] is False
    for a in plan.values():
        assert Decimal(result['ending_quantities'][a['symbol']]) == (Decimal(0) if a['kind'] == 'SELL' else a['quantity'])
    assert plan == before


@pytest.mark.parametrize('day', ['2026-09-17', '2026-09-18'])
def test_same_day_or_future_buys_cannot_cover_earlier_sales(day):
    plan = prepared()
    result = check(plan, acquired(plan, day))
    assert not result['coverage_verified'] and len(result['shortages']) == 2
    assert 'CHRONOLOGICAL_HOLDINGS_SHORTFALL' in result['blockers']


def test_missing_acquisitions_do_not_invent_opening_buy():
    result = check(prepared(), [])
    assert len(result['shortages']) == 2
    assert all(s['available_before_day'] == '0' for s in result['shortages'])


@pytest.mark.parametrize('owned', [True, False])
def test_existing_owned_or_explicitly_adopted_trades_count_once(owned):
    plan = prepared()
    rows = acquired(plan)
    resolutions = {}
    for i, (marker, a) in enumerate(plan.items()):
        remote_id = 'existing-' + str(i)
        rows.append(row(a, remote_id, owned=owned))
        if not owned:
            resolutions[marker] = resolution(a, remote_id)
    result = check(plan, rows, resolutions)
    assert result['coverage_verified']
    assert sum(Decimal(v) for v in result['ending_quantities'].values()) == 3


def test_unresolved_similar_existing_trades_cannot_be_counted_twice():
    plan = prepared()
    rows = acquired(plan) + [row(next(iter(plan.values())))]
    with pytest.raises(RuntimeError, match='HOLDINGS_ADOPTION_UNRESOLVED'):
        check(plan, rows)


@pytest.mark.parametrize('change', ['other-account', 'draft', 'excluded', 'future'])
def test_ineligible_acquisitions_cannot_cover_sales(change):
    plan = prepared()
    rows = acquired(plan)
    for r in rows:
        if change == 'other-account':
            r['accountId'] = r['account']['id'] = 'other'
        elif change == 'draft':
            r['isDraft'] = True
        elif change == 'excluded':
            r['account']['isExcluded'] = True
        else:
            r['date'] = '2999-01-01T00:00:00.000Z'
    assert not check(plan, rows)['coverage_verified']


@pytest.mark.parametrize('key,value', [('kind', 'partial_history'), ('snapshot_sha256', 'stale'), ('target_account_id', 'other'), ('confirmed_by', ''), ('reference', None)])
def test_history_proof_is_explicit_account_and_snapshot_bound(key, value):
    plan = prepared()
    raw = json.dumps({'count': 0, 'activities': []})
    evidence = {'kind': 'complete_acquisition_history', 'snapshot_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                'target_account_id': next(iter(plan.values()))['target_account_id'],
                'confirmed_by': 'synthetic', 'reference': 'synthetic'}
    evidence[key] = value
    with pytest.raises(RuntimeError, match='COMPLETE_ACQUISITION_HISTORY_EVIDENCE_REQUIRED'):
        check(plan, [], evidence=evidence)


@pytest.mark.parametrize('change', ['date', 'currency', 'source', 'unknown-type'])
def test_unverified_quantity_context_blocks(change):
    plan = prepared()
    rows = acquired(plan)
    r = rows[0]
    if change == 'date':
        r['date'] = r['date'].replace('T00:', 'T12:')
    elif change == 'currency':
        r['currency'] = r['assetProfile']['currency'] = 'USD'
    elif change == 'source':
        r['assetProfile']['dataSource'] = 'MANUAL'
    else:
        r['type'] = 'LIABILITY'
    with pytest.raises(RuntimeError, match='HOLDINGS'):
        check(plan, rows)


def test_dividend_fee_interest_do_not_change_security_quantity():
    plan = prepared()
    rows = acquired(plan)
    for i, kind in enumerate(('DIVIDEND', 'FEE', 'INTEREST')):
        extra = copy.deepcopy(rows[0])
        extra['id'], extra['type'] = 'nontrade-' + str(i), kind
        rows.append(extra)
    assert check(plan, rows)['coverage_verified']


def test_precision_of_fractional_position_is_exact():
    plan = prepared()
    first_id, sale = next(iter(plan.items()))
    sale['quantity'] = Decimal('0.12345678901234568')
    rows = acquired(plan)
    result = check(plan, rows)
    assert result['coverage_verified'] and result['ending_quantities'][sale['symbol']] == '0'


def test_future_new_source_activity_blocks():
    plan = prepared()
    next(iter(plan.values()))['operation_date'] = date(2999, 1, 1)
    with pytest.raises(RuntimeError, match='FUTURE_HOLDINGS_ACTIVITY'):
        check(plan, acquired(plan))

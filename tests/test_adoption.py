import copy
from decimal import Decimal
import json
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_conversion import inputs
from test_identity import ACCOUNT


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def prepared():
    statement, docs, account, mappings = inputs()
    account['account_key'] = ACCOUNT
    activities = bd.convert_matched_trades(statement, docs, account, mappings)
    ids = {e['source_slot']: e['id'] for e in bd.ledger_identity(statement, ACCOUNT)['events']}
    return {ids[a['source_slot']]: {**a, 'id': ids[a['source_slot']]} for a in activities}


def row(activity, remote_id='synthetic-remote-1', owned=False):
    return {'id': remote_id, 'accountId': activity['target_account_id'], 'type': activity['kind'],
            'currency': activity['price_currency'], 'date': activity['operation_date'].isoformat() + 'T00:00:00.000Z',
            'quantity': float(activity['quantity']), 'unitPrice': float(activity['unit_price']), 'fee': float(activity['fee']),
            'comment': activity['id'] if owned else None, 'tags': [],
            'account': {'id': activity['target_account_id'], 'tags': []},
            'assetProfile': {'symbol': activity['symbol'], 'dataSource': 'YAHOO', 'currency': 'EUR'}}


def snapshot(rows):
    return bd.parse_remote_activity_snapshot(json.dumps({'count': len(rows), 'activities': rows}))


def resolution(activity, remote_id='synthetic-remote-1'):
    return {'remote_id': remote_id, 'financial_fingerprint': bd.activity_financial_fingerprint(activity)}


def test_complete_json_float_values_are_decimal_without_python_float_roundtrip():
    plan = prepared()
    item = next(iter(plan.values()))
    raw = row(item)
    remote = snapshot([raw])
    assert isinstance(remote[0]['fee'], Decimal)
    assert remote[0]['fee'] == Decimal('0.2')
    assert remote[0]['active'] is True and remote[0]['date_context_verified'] is True
    assert bd.activity_financial_fingerprint(remote[0]) == bd.activity_financial_fingerprint(item)


@pytest.mark.parametrize('data,error', [
    ({'count': 2, 'activities': []}, 'REMOTE_ACTIVITY_COUNT_MISMATCH'),
    ({'count': True, 'activities': []}, 'REMOTE_ACTIVITY_COUNT_MISMATCH'),
    ({'count': 0, 'activities': {}}, 'INVALID_REMOTE_ACTIVITY_SNAPSHOT'),
])
def test_partial_or_invalid_list_not_accepted(data, error):
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        bd.parse_remote_activity_snapshot(json.dumps(data))


def test_duplicate_json_fields_and_remote_ids_block():
    with pytest.raises(RuntimeError, match='JSON_DUPLICATE_KEY'):
        bd.parse_remote_activity_snapshot('{"count":0,"count":0,"activities":[]}')
    item = row(next(iter(prepared().values())))
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVITY_ID_DUPLICATE'):
        snapshot([item, item])


@pytest.mark.parametrize('key', ['quantity', 'unitPrice', 'fee'])
def test_redaction_blocks_complete_snapshot(key):
    item = row(next(iter(prepared().values())))
    item[key] = None
    with pytest.raises(RuntimeError, match='REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED'):
        snapshot([item])


def test_current_profile_takes_precedence_even_if_legacy_looks_valid():
    item = row(next(iter(prepared().values())))
    item['SymbolProfile'] = item['assetProfile']
    item['assetProfile'] = None
    with pytest.raises(RuntimeError, match='REMOTE_ASSET_PROFILE_INVALID'):
        snapshot([item])
    del item['assetProfile']
    assert snapshot([item])[0]['symbol'] == item['SymbolProfile']['symbol']


def test_owned_marker_requires_financial_and_account_equality():
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    remote = snapshot([row(item, owned=True)])
    result = bd.reconcile_existing_activities(plan, remote, {})
    assert result['owned'] == [first_id] and len(result['new']) == 2
    assert result['import_ready'] is False
    for key, value in [('fee', Decimal('0.21')), ('target_account_id', 'different-target'), ('symbol', 'CHANGED')]:
        altered = copy.deepcopy(remote)
        altered[0][key] = value
        with pytest.raises(RuntimeError, match='REMOTE_OWNED_ACTIVITY_CONFLICT'):
            bd.reconcile_existing_activities(plan, altered, {})


def test_duplicate_owned_markers_block_even_if_financial_values_agree():
    plan = prepared()
    item = next(iter(plan.values()))
    remote = snapshot([row(item, owned=True), row(item, 'synthetic-remote-2', owned=True)])
    with pytest.raises(RuntimeError, match='REMOTE_OWNED_MARKER_DUPLICATE'):
        bd.reconcile_existing_activities(plan, remote, {})


def test_manual_financial_similarity_is_candidate_not_automatic_skip():
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    remote = snapshot([row(item)])
    result = bd.reconcile_existing_activities(plan, remote, {})
    assert not result['owned'] and not result['adopted']
    assert result['candidates'] == {first_id: ['synthetic-remote-1']}
    assert 'MANUAL_ACTIVITY_ADOPTION_REQUIRED' in result['blockers']
    assert first_id not in result['new']


def test_explicit_fingerprint_resolution_adopts_without_modifying_any_source():
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    remote = snapshot([row(item)])
    before = copy.deepcopy((plan, remote))
    resolutions = {first_id: resolution(item)}
    result = bd.reconcile_existing_activities(plan, remote, resolutions)
    assert result['adopted'] == resolutions and result['candidates'] == {}
    assert 'MANUAL_ACTIVITY_ADOPTION_REQUIRED' not in result['blockers']
    assert result['import_ready'] is False and before == (plan, remote)


@pytest.mark.parametrize('key,value', [('remote_id', 'another-remote'), ('financial_fingerprint', 'changed')])
def test_stale_or_invalid_adoption_resolution_blocks(key, value):
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    resolved = resolution(item)
    resolved[key] = value
    with pytest.raises(RuntimeError, match='STALE_ADOPTION_RESOLUTION'):
        bd.reconcile_existing_activities(plan, snapshot([row(item)]), {first_id: resolved})


def test_changed_remote_financial_values_invalidate_prior_adoption():
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    remote = snapshot([row(item)])
    remote[0]['quantity'] += Decimal('1')
    with pytest.raises(RuntimeError, match='STALE_ADOPTION_RESOLUTION'):
        bd.reconcile_existing_activities(plan, remote, {first_id: resolution(item)})


def test_same_manual_remote_cannot_cover_two_identical_source_occurrences():
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    identical_id = first_id[:-1] + ('a' if first_id[-1] != 'a' else 'b')
    duplicate = {**copy.deepcopy(item), 'id': identical_id}
    pair = {first_id: item, identical_id: duplicate}
    resolved = {first_id: resolution(item), identical_id: resolution(duplicate)}
    with pytest.raises(RuntimeError, match='ADOPTION_MULTIPLICITY_CONFLICT'):
        bd.reconcile_existing_activities(pair, snapshot([row(item)]), resolved)
    remote = snapshot([row(item), row(item, 'synthetic-remote-2')])
    resolved[identical_id]['remote_id'] = 'synthetic-remote-2'
    result = bd.reconcile_existing_activities(pair, remote, resolved)
    assert len(result['adopted']) == 2


@pytest.mark.parametrize('context', ['tag', 'draft', 'excluded', 'clock'])
def test_inactive_or_unverified_date_context_cannot_authorize_duplication(context):
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    raw = row(item)
    if context == 'tag':
        raw['tags'] = [{'id': '0c077abd-eca2-4cbb-818c-6cefbf2d169a'}]
    elif context == 'draft':
        raw['isDraft'] = True
    elif context == 'excluded':
        raw['account']['isExcluded'] = True
    else:
        raw['date'] = raw['date'].replace('T00:00:00', 'T12:00:00')
    with pytest.raises(RuntimeError, match='REMOTE_CANDIDATE_CONTEXT_UNVERIFIED'):
        bd.reconcile_existing_activities(plan, snapshot([raw]), {})


def test_foreign_stable_ownership_marker_cannot_be_implicitly_reassigned():
    plan = prepared()
    first_id, item = next(iter(plan.items()))
    raw = row(item)
    raw['comment'] = 'BD#v1#another-owner#another-event'
    with pytest.raises(RuntimeError, match='FOREIGN_BD_OWNERSHIP_CONFLICT'):
        bd.reconcile_existing_activities(plan, snapshot([raw]), {first_id: resolution(item)})


def test_matching_other_account_never_becomes_manual_adoption_candidate():
    plan = prepared()
    raw = row(next(iter(plan.values())))
    raw['accountId'] = 'other-account'
    raw['account']['id'] = 'other-account'
    result = bd.reconcile_existing_activities(plan, snapshot([raw]), {})
    assert len(result['new']) == 3 and not result['candidates']


def test_incomplete_eligibility_context_and_timezone_fail():
    item = row(next(iter(prepared().values())))
    item['account']['tags'] = None
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVE_TAGS_MISSING_OR_INVALID'):
        snapshot([item])
    item = row(next(iter(prepared().values())))
    item['date'] = item['date'].replace('.000Z', '')
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVITY_TIMEZONE_MISSING'):
        snapshot([item])


def test_remote_quote_currency_conflict_not_interpreted_as_conversion():
    item = row(next(iter(prepared().values())))
    item['assetProfile']['currency'] = 'USD'
    parsed = snapshot([item])
    assert parsed[0]['price_currency'] == 'EUR'
    assert parsed[0]['financial_context_verified'] is False
    with pytest.raises(RuntimeError, match='REMOTE_CANDIDATE_CONTEXT_UNVERIFIED'):
        bd.reconcile_existing_activities(prepared(), parsed, {})


def test_explicit_null_currency_uses_proven_profile_default():
    plan = prepared()
    item = row(next(iter(plan.values())), owned=True)
    item['currency'] = None
    parsed = snapshot([item])
    assert parsed[0]['price_currency'] == 'EUR'
    assert parsed[0]['currency_origin'] == 'asset_profile_default'
    assert parsed[0]['financial_context_verified'] is True
    assert len(bd.reconcile_existing_activities(plan, parsed, {})['owned']) == 1


def test_absent_currency_does_not_get_null_inheritance():
    item = row(next(iter(prepared().values())))
    del item['currency']
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVITY_CONTEXT_MISSING'):
        snapshot([item])


@pytest.mark.parametrize('profile', [None, {}, {'currency': None}])
def test_null_currency_requires_actual_profile_currency(profile):
    item = row(next(iter(prepared().values())))
    item['currency'], item['assetProfile'] = None, profile
    with pytest.raises(RuntimeError):
        snapshot([item])


def test_unassigned_account_pair_preserved_but_never_owned_or_holdings_active():
    plan = prepared()
    item = row(next(iter(plan.values())))
    item['accountId'], item['account'] = None, None
    parsed = snapshot([item])
    assert parsed[0]['target_account_id'] is None and parsed[0]['active'] is False
    assert len(bd.reconcile_existing_activities(plan, parsed, {})['new']) == 3
    item['comment'] = next(iter(plan))
    with pytest.raises(RuntimeError, match='REMOTE_OWNED_ACTIVITY_CONFLICT'):
        bd.reconcile_existing_activities(plan, snapshot([item]), {})


@pytest.mark.parametrize('change', ['missing-account', 'missing-id', 'null-id-object', 'id-null-account'])
def test_unassigned_account_cannot_excuse_missing_or_conflicting_context(change):
    item = row(next(iter(prepared().values())))
    if change == 'missing-account':
        item['accountId'] = None
        del item['account']
    elif change == 'missing-id':
        del item['accountId']
        item['account'] = None
    elif change == 'null-id-object':
        item['accountId'] = None
    else:
        item['account'] = None
    with pytest.raises(RuntimeError):
        snapshot([item])


def test_zero_price_history_is_preserved_but_not_financially_verified():
    item = row(next(iter(prepared().values())))
    item['unitPrice'] = 0
    parsed = snapshot([item])
    assert parsed[0]['unit_price'] == 0 and parsed[0]['financial_context_verified'] is False

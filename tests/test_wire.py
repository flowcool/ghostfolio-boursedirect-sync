import copy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_adoption import prepared, row


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def response(plan):
    return {'activities': [row(a, 'remote-' + str(i), owned=True) for i, a in enumerate(plan.values())]}


def test_review_is_allowlisted_exact_numeric_utc_and_deterministic():
    plan = prepared()
    before = copy.deepcopy(plan)
    review = bd.build_wire_payload(plan)
    assert review == bd.build_wire_payload(dict(reversed(list(plan.items()))))
    assert review['sha256'] == hashlib.sha256(review['body']).hexdigest()
    assert review['import_ready'] is False and plan == before
    values = json.loads(review['body'], parse_float=Decimal)['activities']
    assert len(values) == 3
    assert [r['date'] for r in values] == sorted(r['date'] for r in values)
    for item in values:
        source = plan[item['comment']]
        assert item['date'] == source['operation_date'].isoformat() + 'T00:00:00.000Z'
        assert set(item) == {'accountId', 'comment', 'currency', 'dataSource', 'date', 'fee', 'quantity', 'symbol', 'type', 'unitPrice'}
        assert Decimal(item['quantity']) == source['quantity']
        assert Decimal(item['unitPrice']) == source['unit_price']
        assert Decimal(item['fee']) == source['fee']
    assert len(bd.reviewed_wire_rows(review)) == 3


@pytest.mark.parametrize('value', ['0', '0.10', '5.537', '0.12345678901234568', '9007199254740992', '1E-100', '1E100'])
def test_supported_tokens_preserve_decimal_value(value):
    source = Decimal(value)
    assert Decimal(json.dumps(bd.wire_number(source))) == source


@pytest.mark.parametrize('value', ['0.123456789012345678', '9007199254740993', '1E400', '1E-400'])
def test_excess_precision_overflow_and_underflow_rejected(value):
    with pytest.raises(RuntimeError, match='WIRE_NUMERIC_PRECISION_LOSS'):
        bd.wire_number(Decimal(value))


@pytest.mark.parametrize('value', [True, None, 1, 0.1, 'NaN', 'Infinity', '1e3', Decimal('NaN'), Decimal('Infinity')])
def test_unreviewed_number_types_and_nonfinite_rejected(value):
    with pytest.raises(RuntimeError, match='INVALID_WIRE_DECIMAL'):
        bd.wire_number(value)


@pytest.mark.parametrize('key,value', [
    ('kind', 'DIVIDEND'), ('data_source', 'MANUAL'), ('price_currency', 'USD'),
    ('quantity', Decimal(0)), ('quantity', Decimal(-1)), ('unit_price', Decimal(0)),
    ('fee', Decimal('-0.01')), ('symbol', 'BAD SYMBOL'), ('operation_date', '2026-02-30'),
    ('operation_date', datetime(2026, 9, 1)), ('target_account_id', ' target '),
    ('account_key', 'not-uuid'), ('id', 'other'),
])
def test_invalid_source_never_yields_partial_payload(key, value):
    plan = prepared()
    next(iter(plan.values()))[key] = value
    with pytest.raises(RuntimeError):
        bd.build_wire_payload(plan)


def test_private_yaml_string_values_equal_internal_decimals():
    plan = prepared()
    strings = copy.deepcopy(plan)
    for activity in strings.values():
        for key in ('quantity', 'unit_price', 'fee'):
            activity[key] = bd.canonical_decimal(activity[key])
        activity['operation_date'] = activity['operation_date'].isoformat()
    assert bd.build_wire_payload(strings) == bd.build_wire_payload(plan)


def test_mixed_target_or_namespace_and_empty_payload_fail():
    plan = prepared()
    next(iter(plan.values()))['target_account_id'] = 'other-target'
    with pytest.raises(RuntimeError, match='WIRE_ACCOUNT_BINDING_CONFLICT'):
        bd.build_wire_payload(plan)
    for invalid in ({}, [], {1: {}}):
        with pytest.raises(RuntimeError):
            bd.build_wire_payload(invalid)


def test_response_complete_skipped_partial_are_distinct_and_never_ready():
    plan = prepared()
    review = bd.build_wire_payload(plan)
    data = response(plan)
    for rows, status, accepted in [(data['activities'], 'complete', 3), ([], 'skipped', 0), (data['activities'][:1], 'partial', 1)]:
        result = bd.compare_import_response(review, json.dumps({'activities': rows}))
        assert result['status'] == status
        assert len(result['accepted']) == accepted and len(result['missing']) == 3 - accepted
        assert result['import_ready'] is False
        assert result['blockers'] == ['COMPLETE_READBACK_REQUIRED', 'UNCERTAIN_WRITE_RECOVERY_UNVERIFIED']


@pytest.mark.parametrize('key,value', [
    ('accountId', 'different'), ('type', 'DIVIDEND'), ('currency', 'USD'), ('comment', 'foreign-marker'),
    ('id', None), ('quantity', True), ('unitPrice', None), ('fee', '0.2'),
    ('quantity', 999), ('unitPrice', 999), ('fee', 999),
    ('date', '2026-09-01'), ('date', 'not-date'), ('date', 123),
])
def test_response_changed_ownership_financial_or_date_fields_conflict(key, value):
    plan = prepared()
    data = response(plan)
    data['activities'][0][key] = value
    result = bd.compare_import_response(bd.build_wire_payload(plan), json.dumps(data))
    assert result['status'] == 'conflicting' and 'conflict_code' in result
    assert result['import_ready'] is False


def test_response_same_calendar_but_shifted_instant_conflicts():
    plan = prepared()
    data = response(plan)
    item = data['activities'][0]
    item['date'] = item['date'].replace('T00:00:00.000Z', 'T12:00:00.000Z')
    assert bd.compare_import_response(bd.build_wire_payload(plan), json.dumps(data))['conflict_code'] == 'IMPORT_RESPONSE_DATE_CONFLICT'


def test_response_equal_instant_offset_and_decimal_spelling_accepted():
    plan = prepared()
    data = response(plan)
    for item in data['activities']:
        item['date'] = item['date'].replace('T00:00:00.000Z', 'T02:00:00+02:00')
    raw = json.dumps(data).replace('0.2', '2e-1')
    assert bd.compare_import_response(bd.build_wire_payload(plan), raw)['status'] == 'complete'


@pytest.mark.parametrize('key,value', [('symbol', 'OTHER'), ('dataSource', 'MANUAL'), ('currency', 'USD')])
def test_response_profile_fields_must_match_sent_values(key, value):
    plan = prepared()
    data = response(plan)
    data['activities'][0]['assetProfile'][key] = value
    assert bd.compare_import_response(bd.build_wire_payload(plan), json.dumps(data))['conflict_code'] == 'IMPORT_RESPONSE_PROFILE_CONFLICT'


def test_current_response_profile_invalid_cannot_fall_back_to_legacy():
    plan = prepared()
    data = response(plan)
    first = data['activities'][0]
    first['SymbolProfile'] = first['assetProfile']
    first['assetProfile'] = None
    review = bd.build_wire_payload(plan)
    assert bd.compare_import_response(review, json.dumps(data))['status'] == 'conflicting'
    del first['assetProfile']
    assert bd.compare_import_response(review, json.dumps(data))['status'] == 'complete'


@pytest.mark.parametrize('duplicate', ['marker', 'id'])
def test_response_duplicate_ownership_or_remote_id_conflicts(duplicate):
    plan = prepared()
    data = response(plan)
    key = 'comment' if duplicate == 'marker' else 'id'
    data['activities'][1][key] = data['activities'][0][key]
    result = bd.compare_import_response(bd.build_wire_payload(plan), json.dumps(data))
    assert result['status'] == 'conflicting'
    assert len(result['accepted']) == 1  # Positive evidence retained, no success or replay permission.


@pytest.mark.parametrize('raw', ['{"activities":[],"activities":[]}', '{', '{}', '[]', '{"activities":[null]}'])
def test_malformed_response_is_conflict_never_empty_success(raw):
    result = bd.compare_import_response(bd.build_wire_payload(prepared()), raw)
    assert result['status'] == 'conflicting' and len(result['missing']) == 3


def test_response_long_decimal_token_cannot_hide_behind_binary_rounding():
    plan = prepared()
    data = response(plan)
    raw = json.dumps(data).replace('0.2', '0.20000000000000000001')
    result = bd.compare_import_response(bd.build_wire_payload(plan), raw)
    assert result['status'] == 'conflicting'


@pytest.mark.parametrize('tamper', ['body', 'digest', 'ready', 'extra', 'spacing'])
def test_review_tampering_and_unreviewed_payload_shape_fail_before_response(tamper):
    review = bd.build_wire_payload(prepared())
    if tamper == 'body':
        review['body'] += b' '
    elif tamper == 'digest':
        review['sha256'] = '0' * 64
    elif tamper == 'ready':
        review['import_ready'] = True
    else:
        data = json.loads(review['body'])
        if tamper == 'extra':
            data['activities'][0]['unreviewed'] = True
        review['body'] = json.dumps(data).encode()
        review['sha256'] = hashlib.sha256(review['body']).hexdigest()
    with pytest.raises(RuntimeError):
        bd.compare_import_response(review, '{"activities":[]}')

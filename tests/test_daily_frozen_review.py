import copy
from datetime import date
import hashlib
import json

import pytest

import boursedirect_to_ghostfolio as bd
from test_mixed_preparation import sources
from test_holdings import acquired, no_network
from test_adoption import row


def window_sources():
    raw, documents = sources()
    config = bd.parse_keyed_yaml(raw)
    old = copy.deepcopy(config['documents']['september'])
    old['statement'] = 'june-statement.html'
    old['notes'] = ['june-'+name for name in old['notes']]
    config['documents']['june'] = old
    documents['june'] = {
        'statement': documents['september']['statement'].replace(b'/09/2026', b'/06/2026').replace(b'31/08/2026', b'31/05/2026'),
        'notes': [raw.replace(b'/09/2026', b'/06/2026') for raw in documents['september']['notes']]}
    return bd.yaml.safe_dump(config).encode(), documents


def bundle(as_of='2026-10-12'):
    raw, documents = window_sources()
    prepared = bd.compute_prepared_sources(raw, documents, 1000000, 32)['artifact']
    current = {k:{**v, 'operation_date':date.fromisoformat(v['operation_date'])}
               for k,v in prepared['activities'].items() if v['operation_date']=='2026-09-17'}
    rows = acquired(current)
    snapshot = json.dumps({'count':len(rows), 'activities':rows}).encode()
    history = {'kind':'complete_acquisition_history', 'target_account_id':prepared['target_account_id'],
               'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
               'confirmed_by':'synthetic-operator', 'reference':'synthetic-window-history'}
    captures = {'prepared':bd.yaml.safe_dump(prepared).encode(), 'snapshot':snapshot,
                'resolutions':b'{}\n', 'history_evidence':bd.yaml.safe_dump(history).encode()}
    config = {'schema_version':3, 'adoption_mode':'certain_unique', 'as_of':as_of,
              **{k:k+'.yaml' for k in captures}}
    return bd.yaml.safe_dump(config).encode(), captures


def compute(config, captures):
    return bd.compute_offline_review(config, captures, 1000000)


def test_frozen_window_uses_full_source_review_and_only_selected_new_holdings_and_wire():
    config, captures = bundle()
    report = compute(config, captures)
    assert len(report['adoption']['new']) == 8
    assert len(report['holdings']['selected_new']) == report['wire']['activity_count'] == 4
    assert report['holdings']['booking_window'] == {'first_day':'2026-07-15', 'last_day':'2026-10-12', 'days':90}
    assert report['holdings']['coverage_verified'] is True
    rows = json.loads(report['wire']['body_utf8'])['activities']
    assert all(r['date']=='2026-09-17T00:00:00.000Z' for r in rows)
    assert next(r for r in rows if r['type']=='DIVIDEND')['unitPrice'] == 1.9
    assert bd.frozen_review_summary(report)['new_activities'] == 4
    assert report['import_ready'] is False
    raw = bd.yaml.safe_dump(report).encode()
    assert bd.validate_frozen_review(raw, hashlib.sha256(raw).hexdigest(), config, captures, 1000000) == report
    assert compute(config, captures) == report


@pytest.mark.parametrize('day,count', [('2026-12-15',4), ('2026-12-16',0)])
def test_frozen_window_inclusive_start_and_all_old_rows_have_no_wire(day, count):
    config, captures = bundle(day)
    report = compute(config, captures)
    assert len(report['holdings']['selected_new']) == count
    assert bd.frozen_review_summary(report)['new_activities'] == count
    assert (report['wire'] is None) is (count==0)
    assert len(report['adoption']['new']) == 8


def test_old_unimported_buys_cannot_cover_selected_sales():
    config, captures = bundle()
    prepared = bd.parse_keyed_yaml(captures['prepared'])
    plan = {k:v for k,v in prepared['activities'].items() if v['operation_date']=='2026-09-17'}
    for i, activity in enumerate(list(plan.values())):
        if activity['kind']=='SELL':
            old = copy.deepcopy(activity)
            old.update(id='BD#v1#'+prepared['account_key']+'#'+str(i)*64,
                       operation_date='2026-06-17', kind='BUY')
            plan[old['id']] = old
    prepared['activities'] = plan
    captures['prepared'] = bd.yaml.safe_dump(prepared).encode()
    captures['snapshot'] = b'{"count":0,"activities":[]}'
    history = bd.parse_keyed_yaml(captures['history_evidence'])
    history['snapshot_sha256'] = hashlib.sha256(captures['snapshot']).hexdigest()
    captures['history_evidence'] = bd.yaml.safe_dump(history).encode()
    report = compute(config, captures)
    assert report['holdings']['coverage_verified'] is False
    assert len(report['holdings']['shortages']) == 2
    assert all(s['available_before_day']=='0' for s in report['holdings']['shortages'])
    options = bd.parse_keyed_yaml(config)
    options.update(schema_version=2)
    options.pop('as_of')
    full = compute(bd.yaml.safe_dump(options).encode(), captures)
    assert full['holdings']['coverage_verified'] is True


def test_window_filter_cannot_hide_legacy_timestamp_uncertainty_in_old_sources():
    config, captures = bundle('2026-12-16')
    prepared = bd.parse_keyed_yaml(captures['prepared'])
    activity = next(a for a in prepared['activities'].values() if a['operation_date']=='2026-06-17')
    remote = row({**activity, 'operation_date':date.fromisoformat(activity['operation_date'])})
    remote['date'] = activity['operation_date']+'T13:00:00.000Z'
    rows = json.loads(captures['snapshot'])['activities']+[remote]
    captures['snapshot'] = json.dumps({'count':len(rows),'activities':rows}).encode()
    history = bd.parse_keyed_yaml(captures['history_evidence'])
    history['snapshot_sha256'] = hashlib.sha256(captures['snapshot']).hexdigest()
    captures['history_evidence'] = bd.yaml.safe_dump(history).encode()
    with pytest.raises(RuntimeError, match='^REMOTE_CANDIDATE_CONTEXT_UNVERIFIED$'):
        compute(config, captures)


def test_window_filter_cannot_hide_old_source_multiplicity():
    config, captures = bundle('2026-12-16')
    prepared = bd.parse_keyed_yaml(captures['prepared'])
    original = next(a for a in prepared['activities'].values() if a['operation_date']=='2026-06-17')
    duplicate = copy.deepcopy(original)
    duplicate['id'] = 'BD#v1#'+prepared['account_key']+'#'+'0'*64
    prepared['activities'][duplicate['id']] = duplicate
    captures['prepared'] = bd.yaml.safe_dump(prepared).encode()
    remote = row({**original, 'operation_date':date.fromisoformat(original['operation_date'])})
    rows = json.loads(captures['snapshot'])['activities']+[remote]
    captures['snapshot'] = json.dumps({'count':len(rows),'activities':rows}).encode()
    history = bd.parse_keyed_yaml(captures['history_evidence'])
    history['snapshot_sha256'] = hashlib.sha256(captures['snapshot']).hexdigest()
    captures['history_evidence'] = bd.yaml.safe_dump(history).encode()
    with pytest.raises(RuntimeError, match='^HOLDINGS_ADOPTION_UNRESOLVED$'):
        compute(config, captures)


@pytest.mark.parametrize('field,value', [('as_of','2026-02-30'), ('as_of',True),
                                         ('adoption_mode','guess'), ('window_days',30)])
def test_frozen_daily_clock_and_policy_are_exact_explicit_inputs(field, value):
    config, captures = bundle()
    options = bd.parse_keyed_yaml(config)
    options[field] = value
    with pytest.raises(RuntimeError, match='^(INVALID_REVIEW_CONFIGURATION|INVALID_DAILY_PREVIEW_DAY)$'):
        compute(bd.yaml.safe_dump(options).encode(), captures)


def test_pinned_review_cannot_change_window_even_with_same_selected_wire():
    config, captures = bundle()
    report = compute(config, captures)
    raw = bd.yaml.safe_dump(report).encode()
    options = bd.parse_keyed_yaml(config)
    options['as_of'] = '2026-10-13'
    changed = bd.yaml.safe_dump(options).encode()
    assert compute(changed, captures)['wire'] == report['wire']
    with pytest.raises(RuntimeError, match='^FROZEN_REVIEW_CONTENT_CONFLICT$'):
        bd.validate_frozen_review(raw, hashlib.sha256(raw).hexdigest(), changed, captures, 1000000)

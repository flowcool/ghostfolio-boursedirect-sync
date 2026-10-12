import copy
from datetime import date
import json
from pathlib import Path

import pytest

import boursedirect_to_ghostfolio as bd
from test_daily_preview import isolated, setup, run, paths
from test_mixed_preparation import sources, internal_plan
from test_adoption import row


def report(config):
    return bd.parse_keyed_yaml(paths(config)[1].read_bytes())


def test_window_selection_uses_original_source_day_and_no_activity_before_inclusive_start():
    config = setup()
    run('2026-12-15')
    before = report(config)['candidate_export']
    assert before['activity_count'] == 3 and before['excluded_outside_window'] == 0
    run('2026-12-16')
    boundary = report(config)
    assert boundary['window']['first_day'] == '2026-09-18'
    export = boundary['candidate_export']
    assert export['activity_count'] == 0 and export['wire'] is None
    assert export['excluded_outside_window'] == 3
    assert boundary['import_ready'] is export['import_ready'] is False
    assert boundary['window_source_events']['2026-09'] == []


def test_owned_activities_and_certain_unique_adoption_are_excluded_from_daily_wire():
    config = setup()
    captures, _ = bd.capture_preparation_sources(
        bd.yaml.safe_dump({k:v for k,v in config.items() if k!='snapshot'}).encode(),'inputs',1000000,32)
    prepared = bd.compute_prepared_sources(bd.yaml.safe_dump({k:v for k,v in config.items() if k!='snapshot'}).encode(),captures,1000000,32)['artifact']['activities']
    rows = []
    for i,a in enumerate(prepared.values()):
        a = {**a, 'operation_date':date.fromisoformat(a['operation_date'])}
        rows.append(row(a, 'existing-'+str(i), owned=(i==0)))
    Path('inputs/snapshot.json').write_text(json.dumps({'count':3,'activities':rows}))
    run()
    export = report(config)['candidate_export']
    assert export['owned_count'] == 1 and export['adopted_count'] == 2
    assert export['activity_count'] == 0 and export['wire'] is None
    assert export['reconciliation_code'] is None


def test_daily_wire_has_exact_digest_and_repeat_is_identical_but_never_authorizes_writes():
    config = setup()
    run()
    saved = report(config)
    export = saved['candidate_export']
    wire = {'body':export['wire']['body_utf8'].encode(),'sha256':export['wire']['sha256'],'import_ready':False}
    assert len(bd.reviewed_wire_rows(wire)) == 3
    assert export['artifact_kind'] == 'daily_candidate_wire_not_apply_authorization'
    assert 'CURRENT_PERIOD_CUTOFF_UNVERIFIED' in saved['blockers']
    before = paths(config)[1].read_bytes()
    run()
    assert paths(config)[1].read_bytes() == before


def mixed_setup():
    Path('inputs').mkdir()
    raw, captures = sources()
    config = bd.parse_keyed_yaml(raw)
    entry = config['documents']['september']
    Path('inputs',entry['statement']).write_bytes(captures['september']['statement'])
    for filename,body in zip(entry['notes'],captures['september']['notes']):
        Path('inputs',filename).write_bytes(body)
    config['snapshot']='snapshot.json'
    Path('inputs/config.yaml').write_text(bd.yaml.safe_dump(config))
    Path('inputs/snapshot.json').write_text('{"count":0,"activities":[]}')
    return config


def test_complete_mixed_daily_export_includes_net_dividend_and_legacy_mismatch_suppresses_wire():
    config = mixed_setup()
    run()
    export = report(config)['candidate_export']
    assert export['activity_count'] == 4
    rows = json.loads(export['wire']['body_utf8'])['activities']
    dividend = next(r for r in rows if r['type']=='DIVIDEND')
    assert dividend['quantity']==1 and dividend['unitPrice']==1.9 and dividend['fee']==0
    p=internal_plan()
    existing = row(next(a for a in p.values() if a['kind']=='DIVIDEND'))
    existing.update(date='2026-09-13T22:00:00.000Z',quantity=3,unitPrice=0.8)
    Path('inputs/snapshot.json').write_text(json.dumps({'count':1,'activities':[existing]}))
    run()
    export = report(config)['candidate_export']
    assert export['wire'] is None and export['activity_count']==0
    assert export['reconciliation_code']=='REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED'


def test_duplicate_remote_candidates_refuse_export_even_when_other_rows_are_unowned():
    config = setup()
    raw=bd.yaml.safe_dump({k:v for k,v in config.items() if k!='snapshot'}).encode()
    captures,_=bd.capture_preparation_sources(raw,'inputs',1000000,32)
    prepared=bd.compute_prepared_sources(raw,captures,1000000,32)['artifact']['activities']
    a=next(iter(prepared.values()));a={**a,'operation_date':date.fromisoformat(a['operation_date'])}
    rows=[row(a,'one'),row(a,'two')]
    Path('inputs/snapshot.json').write_text(json.dumps({'count':2,'activities':rows}))
    run()
    export=report(config)['candidate_export']
    assert export['reconciliation_code']=='AUTOMATIC_ACTIVITY_ADOPTION_UNCERTAIN'
    assert export['wire'] is None and export['activity_count']==0


def test_old_source_refusal_is_retained_before_window_selection():
    config=setup()
    note=Path('inputs/buy.html')
    note.write_text(note.read_text().replace('QUANTITE : +3','QUANTITE : -3'))
    run('2026-12-16')
    saved=report(config)
    export=saved['candidate_export']
    assert saved['window_source_events']['2026-09']==[]
    assert export['blocked_source_periods']==['2026-09']
    assert export['source_complete_periods']==[] and export['wire'] is None
    assert saved['exceptions']['2026-09:source']['status']=='unresolved'


def test_source_subset_wire_remains_blocked_by_unqualified_period_and_current_cutoff():
    config=setup()
    entry=copy.deepcopy(next(iter(config['documents'].values())))
    Path('inputs/august.html').write_text(Path('inputs/statement.html').read_text().replace('17/09/2026','17/08/2026').replace('31/08/2026','31/07/2026').replace('30/09/2026','31/08/2026'))
    entry['statement']='august.html'
    # September note bytes are intentionally not August evidence.
    config['documents']['august']=entry
    Path('inputs/config.yaml').write_text(bd.yaml.safe_dump(config))
    run()
    saved=report(config)
    export=saved['candidate_export']
    assert export['activity_count']==3 and export['source_complete_periods']==['2026-09']
    assert export['blocked_source_periods']==['2026-08']
    assert export['import_ready'] is saved['import_ready'] is False
    assert saved['exceptions']['2026-08:source']['status']=='unresolved'
    assert 'ACQUISITION_COVERAGE_GAP' in saved['blockers']

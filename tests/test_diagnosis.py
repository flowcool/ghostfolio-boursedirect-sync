import copy
from datetime import timedelta
import fcntl
import hashlib
import json
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_adoption import prepared, row
from test_prepare import setup as prepare_inputs, run as prepare_run, artifact as prepared_path
from test_identity import ACCOUNT


@pytest.fixture(autouse=True)
def isolated_and_no_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    for name in ('reconcile_existing_activities', 'verify_chronological_holdings',
                 'persist_write_transition', 'acquire_readonly_snapshot'):
        monkeypatch.setattr(bd, name, forbidden)


def setup(rows=None):
    prepare_inputs()
    prepare_run()
    Path('inputs/prepared.yaml').write_bytes(prepared_path().read_bytes())
    write_snapshot(rows or [])
    config = {'schema_version': 1, 'prepared': 'prepared.yaml', 'snapshot': 'snapshot.json'}
    Path('inputs/diagnosis.yaml').write_text(yaml.safe_dump(config))
    return config


def write_snapshot(rows):
    Path('inputs/snapshot.json').write_text(json.dumps({'count': len(rows), 'activities': rows}))


def run(maximum=100000):
    return bd.diagnose_local_snapshot('inputs/diagnosis.yaml', 'inputs', maximum)


def output():
    return Path('outputs/diagnosis-' + ACCOUNT + '.yaml')


def artifact():
    return yaml.safe_load(output().read_text())


def private_files():
    return {str(p): p.read_bytes() for folder in ('inputs', 'state', 'outputs')
            for p in Path(folder).rglob('*') if p.is_file()}


def test_diagnostic_cli_provenance_safe_counts_and_no_import_paths(capsys):
    plan = prepared()
    first, second, third = list(plan.values())
    exact = row(first)
    exact['date'] = first['operation_date'].isoformat() + 'T13:14:15.123Z'
    near = row(second, 'near-candidate')
    near['fee'] += 1
    near['currency'] = 'USD'
    near['account']['isExcluded'] = True
    near['comment'] = 'Private free-text comment must never be copied'
    setup([exact, near])
    before = private_files()
    assert bd.main(['diagnose', '--config', 'inputs/diagnosis.yaml', '--input-root', 'inputs',
                    '--max-bytes', '100000']) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary['source_activities'] == 3 and summary['sources_with_candidates'] == 2
    assert summary['remote_candidates'] == 2 and summary['import_ready'] is False
    assert first['target_account_id'] not in json.dumps(summary)
    a = artifact()
    for name in ('wire', 'adoption', 'holdings', 'new', 'body', 'coverage_verified'):
        assert name not in a
    assert a['import_ready'] is False
    assert a['activities'][first['id']]['codes'] == ['CANDIDATE_CONTEXT_UNVERIFIED', 'EXACT_FINANCIAL_MATCH_OBSERVED']
    assert 'fee' in a['activities'][second['id']]['candidates']['near-candidate']['different_fields']
    assert a['activities'][third['id']]['codes'] == ['NO_CANDIDATE_IN_BOUNDED_CHECK']
    assert a['remote_evidence'][exact['id']]['original_timestamp'] == exact['date']
    assert a['remote_evidence'][exact['id']]['fee'] == '0.2'
    assert near['comment'] not in output().read_text()
    assert a['evaluation_started_at_utc'].endswith('+00:00')
    for key, filename in [('config', 'diagnosis.yaml'), ('prepared', 'prepared.yaml'), ('snapshot', 'snapshot.json')]:
        assert a['input_sha256'][key] == hashlib.sha256(Path('inputs', filename).read_bytes()).hexdigest()
    assert a['source_digests'] == yaml.safe_load(Path('inputs/prepared.yaml').read_text())['source_digests']
    assert output().stat().st_mode & 0o777 == 0o600
    assert Path('outputs').stat().st_mode & 0o777 == 0o700
    assert all(Path(path).read_bytes() == raw for path, raw in before.items())
    assert not list(Path('state').glob('writes-*.yaml'))


@pytest.mark.parametrize('days', [-2, -1, 0, 1, 2])
def test_calendar_bounds_are_observations_not_new_classification(days):
    a = next(iter(prepared().values()))
    r = row(a)
    r['date'] = (a['operation_date'] + timedelta(days=days)).isoformat() + 'T13:14:15Z'
    r['fee'] += 1
    r['comment'] = 'BD#foreign-owner'
    setup([r])
    run()
    candidates = artifact()['activities'][a['id']]['candidates']
    assert bool(candidates) is (abs(days) <= 1)
    if candidates:
        assert candidates[r['id']]['ownership'] == 'FOREIGN_BD_MARKER'
    else:
        assert artifact()['activities'][a['id']]['codes'] == ['NO_CANDIDATE_IN_BOUNDED_CHECK']


def test_owned_markers_visible_outside_numeric_and_account_predicate():
    a = next(iter(prepared().values()))
    first = row(a, owned=True)
    first['accountId'] = first['account']['id'] = 'different-account'
    first['type'] = 'DIVIDEND'
    first['quantity'] = 0
    second = copy.deepcopy(first)
    second['id'] = 'duplicate-marker'
    setup([first, second])
    run()
    entry = artifact()['activities'][a['id']]
    assert set(entry['candidates']) == {first['id'], second['id']}
    assert 'OWNED_MARKER_DUPLICATE' in entry['codes']
    assert 'OWNED_MARKER_FINANCIAL_CONFLICT' in entry['codes']
    assert all(c['ownership'] == 'SELF_MARKER' for c in entry['candidates'].values())


def test_shared_candidates_not_consumed_and_source_order_not_resolution():
    a = next(iter(prepared().values()))
    setup([row(a)])
    path = Path('inputs/prepared.yaml')
    p = yaml.safe_load(path.read_text())
    repeated = copy.deepcopy(p['activities'][a['id']])
    repeated['id'] = 'BD#v1#' + ACCOUNT + '#' + 'f' * 64
    repeated['fee'] = '1.2'
    p['activities'][repeated['id']] = repeated
    path.write_text(yaml.safe_dump(p))
    run()
    first = artifact()
    p['activities'] = dict(reversed(list(p['activities'].items())))
    path.write_text(yaml.safe_dump(p, sort_keys=False))
    run()
    second = artifact()
    assert first['activities'] == second['activities']
    assert len(first['remote_evidence']) == 1
    for marker in (a['id'], repeated['id']):
        assert 'SHARED_CANDIDATE_REVIEW_REQUIRED' in first['activities'][marker]['codes']


@pytest.mark.parametrize('tamper', ['partial', 'redacted', 'binding', 'ready', 'extra', 'symlink'])
def test_invalid_inputs_preserve_previous_report_and_all_captured_files(tamper):
    setup()
    run()
    if tamper in ('partial', 'redacted'):
        data = json.loads(Path('inputs/snapshot.json').read_text())
        if tamper == 'partial':
            data['count'] = 1
        else:
            r = row(next(iter(prepared().values())))
            r['fee'] = None
            data = {'count': 1, 'activities': [r]}
        Path('inputs/snapshot.json').write_text(json.dumps(data))
    elif tamper in ('binding', 'ready'):
        path = Path('inputs/prepared.yaml')
        p = yaml.safe_load(path.read_text())
        p['target_account_id' if tamper == 'binding' else 'import_ready'] = 'changed' if tamper == 'binding' else True
        path.write_text(yaml.safe_dump(p))
    elif tamper == 'extra':
        path = Path('inputs/diagnosis.yaml')
        config = yaml.safe_load(path.read_text())
        config['apply'] = True
        path.write_text(yaml.safe_dump(config))
    else:
        path = Path('inputs/snapshot.json')
        raw = path.read_bytes()
        path.unlink()
        Path('outside.json').write_bytes(raw)
        path.symlink_to('../outside.json')
    before = private_files()
    with pytest.raises(RuntimeError):
        run()
    assert private_files() == before


def test_captured_bytes_not_mutated_inputs_determine_report(monkeypatch):
    setup()
    original = bd.read_local_bytes
    captured = {}
    def read_then_replace(path, root, maximum):
        raw = original(path, root, maximum)
        captured[Path(path).name] = raw
        if Path(path).name == 'snapshot.json':
            Path(path).write_text('invalid after capture')
        return raw
    monkeypatch.setattr(bd, 'read_local_bytes', read_then_replace)
    run()
    assert artifact()['input_sha256']['snapshot'] == hashlib.sha256(captured['snapshot.json']).hexdigest()


def test_input_root_including_output_rejects_collision_without_replacement():
    setup()
    output().write_bytes(Path('inputs/snapshot.json').read_bytes())
    config = {'schema_version': 1, 'prepared': 'inputs/prepared.yaml', 'snapshot': str(output())}
    Path('inputs/diagnosis.yaml').write_text(yaml.safe_dump(config))
    before = private_files()
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'):
        bd.diagnose_local_snapshot('inputs/diagnosis.yaml', '.', 100000)
    assert private_files() == before


def test_target_lock_blocks_report_replacement():
    setup()
    run()
    before = private_files()
    target = next(iter(prepared().values()))['target_account_id']
    path = Path('state/prepare-' + hashlib.sha256(target.encode()).hexdigest() + '.lock')
    with path.open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='^DIAGNOSIS_TARGET_LOCKED$'):
            run()
    assert private_files() == before


@pytest.mark.parametrize('count,maximum,error', [(20, 40000, 'DIAGNOSIS_OUTPUT_LIMIT_EXCEEDED'),
                                              (101, 2000000, 'DIAGNOSIS_CANDIDATE_LIMIT_EXCEEDED'),
                                              (1001, 2000000, 'DIAGNOSIS_COMPARISON_LIMIT_EXCEEDED')])
def test_expansion_budgets_fail_without_publishing_or_truncating(count, maximum, error):
    a = next(iter(prepared().values()))
    setup()
    run()
    p = yaml.safe_load(Path('inputs/prepared.yaml').read_text())
    original = p['activities'][a['id']]
    p['activities'] = {}
    rows = []
    for index in range(count):
        marker = 'BD#v1#' + ACCOUNT + '#' + format(index, '064x')
        p['activities'][marker] = {**original, 'id': marker}
        rows.append(row(a, 'candidate-' + str(index)))
    Path('inputs/prepared.yaml').write_text(yaml.safe_dump(p))
    write_snapshot(rows)
    before = private_files()
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        run(maximum)
    assert private_files() == before


def test_yaml_calendar_date_and_decimal_scales_are_canonical_observations():
    a = next(iter(prepared().values()))
    setup([row(a)])
    path = Path('inputs/prepared.yaml')
    p = yaml.safe_load(path.read_text())
    source = p['activities'][a['id']]
    source['operation_date'] = a['operation_date']
    for field in ('quantity', 'unit_price', 'fee'):
        value = source[field]
        source[field] = value + ('00' if '.' in value else '.00')
    path.write_text(yaml.safe_dump(p))
    run()
    entry = artifact()['activities'][a['id']]
    assert entry['source']['operation_date'] == a['operation_date'].isoformat()
    assert next(iter(entry['candidates'].values()))['different_fields'] == []


def test_invalid_diagnosis_cli_only_logs_safe_code(capsys, caplog):
    setup()
    path = Path('inputs/diagnosis.yaml')
    config = yaml.safe_load(path.read_text())
    config['private-extra-key'] = 'private account name and value must not leak'
    path.write_text(yaml.safe_dump(config))
    assert bd.main(['diagnose', '--config', str(path), '--input-root', 'inputs', '--max-bytes', '100000']) == 1
    assert capsys.readouterr().out == ''
    assert 'INVALID_DIAGNOSIS_CONFIGURATION' in caplog.text
    assert config['private-extra-key'] not in caplog.text

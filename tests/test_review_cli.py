import hashlib
import json
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_prepare import setup as prepare_inputs, run as prepare_run, artifact as prepared_path
from test_holdings import acquired
from test_adoption import prepared, row, resolution
from test_identity import ACCOUNT


@pytest.fixture(autouse=True)
def isolated_and_no_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def setup(existing=False, missing=False):
    prepare_inputs()
    prepare_run()
    root = Path('inputs')
    (root / 'prepared.yaml').write_bytes(prepared_path().read_bytes())
    plan = prepared()
    rows = [] if missing else acquired(plan)
    resolutions = {}
    if existing:
        for i, (marker, a) in enumerate(plan.items()):
            remote_id = 'existing-' + str(i)
            rows.append(row(a, remote_id))
            resolutions[marker] = resolution(a, remote_id)
    raw = json.dumps({'count': len(rows), 'activities': rows}).encode()
    (root / 'snapshot.json').write_bytes(raw)
    evidence = {'kind': 'complete_acquisition_history', 'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
                'target_account_id': next(iter(plan.values()))['target_account_id'],
                'confirmed_by': 'synthetic-operator', 'reference': 'synthetic-proof'}
    (root / 'history.yaml').write_text(yaml.safe_dump(evidence))
    (root / 'resolutions.yaml').write_text(yaml.safe_dump(resolutions))
    config = {'schema_version': 1, 'prepared': 'prepared.yaml', 'snapshot': 'snapshot.json',
              'history_evidence': 'history.yaml', 'resolutions': 'resolutions.yaml'}
    write_config(config)
    return config


def write_config(config):
    Path('inputs/review.yaml').write_text(yaml.safe_dump(config))


def run():
    return bd.review_local_snapshot('inputs/review.yaml', 'inputs', 100000)


def output():
    return Path('outputs/review-' + ACCOUNT + '.yaml')


def test_cli_end_to_end_safe_counts_and_exact_private_wire(capsys):
    setup()
    assert bd.main(['review', '--config', 'inputs/review.yaml', '--input-root', 'inputs', '--max-bytes', '100000']) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary['new_activities'] == 3 and summary['holdings_shortfalls'] == 0
    assert summary['import_ready'] is False
    assert 'synthetic-ghostfolio-account' not in json.dumps(summary)
    artifact = yaml.safe_load(output().read_text())
    wire = artifact['wire']
    assert hashlib.sha256(wire['body_utf8'].encode()).hexdigest() == wire['sha256']
    assert len(bd.reviewed_wire_rows({'body': wire['body_utf8'].encode(), 'sha256': wire['sha256'], 'import_ready': False})) == 3
    assert artifact['input_sha256']['snapshot'] == hashlib.sha256(Path('inputs/snapshot.json').read_bytes()).hexdigest()
    assert artifact['input_sha256']['prepared'] == hashlib.sha256(Path('inputs/prepared.yaml').read_bytes()).hexdigest()
    assert output().stat().st_mode & 0o777 == 0o600
    assert not list(Path('state').glob('writes-*.yaml'))


def test_all_existing_explicitly_adopted_has_no_new_payload():
    setup(existing=True)
    summary = run()
    artifact = yaml.safe_load(output().read_text())
    assert summary['new_activities'] == 0 and summary['adopted_activities'] == 3
    assert artifact['wire'] is None and artifact['import_ready'] is False


def test_shortfalls_are_diagnostic_blockers_not_invented_acquisitions():
    setup(missing=True)
    summary = run()
    assert summary['holdings_shortfalls'] == 2
    assert 'CHRONOLOGICAL_HOLDINGS_SHORTFALL' in summary['blockers']
    assert summary['import_ready'] is False


def test_repeat_is_deterministic_and_does_not_change_preparation_journal():
    setup()
    before = {p.name: p.read_bytes() for p in Path('state').glob('*.yaml')}
    run()
    first = output().read_bytes()
    run()
    assert first == output().read_bytes()
    assert before == {p.name: p.read_bytes() for p in Path('state').glob('*.yaml')}


@pytest.mark.parametrize('tamper', ['binding', 'ready', 'schema', 'snapshot', 'history', 'resolutions', 'path', 'extra'])
def test_invalid_input_preserves_previous_review(tamper):
    config = setup()
    run()
    before = output().read_bytes()
    if tamper in ('binding', 'ready', 'schema'):
        path = Path('inputs/prepared.yaml')
        value = yaml.safe_load(path.read_text())
        if tamper == 'binding':
            value['target_account_id'] = 'changed'
        elif tamper == 'ready':
            value['import_ready'] = True
        else:
            value['schema_version'] = True
        path.write_text(yaml.safe_dump(value))
    elif tamper == 'snapshot':
        Path('inputs/snapshot.json').write_text('{"count":999,"activities":[]}')
    elif tamper == 'history':
        Path('inputs/history.yaml').write_text('{}')
    elif tamper == 'resolutions':
        Path('inputs/resolutions.yaml').write_text('x: {}')
    elif tamper == 'path':
        Path('outside.json').write_text('{}')
        config['snapshot'] = '../outside.json'
    else:
        config['send'] = True
    write_config(config)
    with pytest.raises(RuntimeError):
        run()
    assert output().read_bytes() == before


def test_mutating_original_files_after_read_does_not_change_captured_provenance(monkeypatch):
    setup()
    original = bd.read_local_bytes
    captured = {}
    def read_then_replace(path, root, maximum):
        raw = original(path, root, maximum)
        captured[Path(path).name] = raw
        if Path(path).name == 'prepared.yaml':
            Path(path).write_text('invalid: changed-after-read')
        return raw
    monkeypatch.setattr(bd, 'read_local_bytes', read_then_replace)
    run()
    artifact = yaml.safe_load(output().read_text())
    assert artifact['input_sha256']['prepared'] == hashlib.sha256(captured['prepared.yaml']).hexdigest()
    assert artifact['wire']['activity_count'] == 3


@pytest.mark.parametrize('previous', [False, True])
def test_legacy_quarantine_preserves_inputs_journals_and_previous_output(previous):
    setup()
    if previous:
        run()
    first = next(iter(prepared().values()))
    remote = row(first)
    remote['fee'] += 1
    remote['date'] = first['operation_date'].isoformat() + 'T13:14:15.123Z'
    path = Path('inputs/snapshot.json')
    data = json.loads(path.read_bytes())
    data['activities'].append(remote)
    data['count'] += 1
    path.write_text(json.dumps(data))
    history = Path('inputs/history.yaml')
    evidence = yaml.safe_load(history.read_text())
    evidence['snapshot_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    history.write_text(yaml.safe_dump(evidence))
    paths = [p for folder in ('inputs', 'state', 'outputs') for p in Path(folder).rglob('*') if p.is_file()]
    before = {str(p): p.read_bytes() for p in paths}
    with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
        run()
    after = {str(p): p.read_bytes() for folder in ('inputs', 'state', 'outputs')
             for p in Path(folder).rglob('*') if p.is_file()}
    assert after == before
    assert output().exists() is previous
    assert not list(Path('state').glob('writes-*.yaml'))


@pytest.mark.parametrize('kind', ['config', 'prepared', 'snapshot', 'resolutions', 'history_evidence'])
def test_output_cannot_replace_any_captured_review_input(kind):
    original = setup()
    config = {key: value if key == 'schema_version' else 'inputs/' + value for key, value in original.items()}
    config_path = Path('inputs/review.yaml')
    if kind == 'config':
        config_path = output()
        config_path.write_text(yaml.safe_dump(config))
    else:
        output().write_bytes(Path(config[kind]).read_bytes())
        config[kind] = str(output())
        config_path.write_text(yaml.safe_dump(config))
    before = {str(p): p.read_bytes() for folder in ('inputs', 'outputs', 'state')
              for p in Path(folder).rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'):
        bd.review_local_snapshot(config_path, '.', 100000)
    after = {str(p): p.read_bytes() for folder in ('inputs', 'outputs', 'state')
             for p in Path(folder).rglob('*') if p.is_file()}
    assert after == before


def test_review_rejects_existing_hardlink_to_captured_snapshot():
    setup()
    output().hardlink_to(Path('inputs/snapshot.json'))
    before = {str(p): p.read_bytes() for folder in ('inputs', 'outputs', 'state')
              for p in Path(folder).rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'):
        run()
    assert before == {str(p): p.read_bytes() for folder in ('inputs', 'outputs', 'state')
                      for p in Path(folder).rglob('*') if p.is_file()}


@pytest.mark.parametrize('command', ['review', 'diagnose'])
def test_output_symlink_loop_reports_safe_code_without_path(command, capsys, caplog):
    setup()
    destination = Path('outputs/' + ('review-' if command == 'review' else 'diagnosis-') + ACCOUNT + '.yaml')
    destination.symlink_to(destination.name)
    if command == 'diagnose':
        config = {'schema_version': 1, 'prepared': 'prepared.yaml', 'snapshot': 'snapshot.json'}
        Path('inputs/review.yaml').write_text(yaml.safe_dump(config))
    assert bd.main([command, '--config', 'inputs/review.yaml', '--input-root', 'inputs', '--max-bytes', '100000']) == 1
    assert capsys.readouterr().out == ''
    assert 'INVALID_OUTPUT_PATH' in caplog.text
    assert str(destination) not in caplog.text
    assert destination.is_symlink()

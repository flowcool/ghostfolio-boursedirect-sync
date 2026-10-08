import copy
import fcntl
import hashlib
import json
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_write_intents import setup as intent_inputs, snapshot, proof


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Verification must not use sockets or mutate journals')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(bd, 'persist_write_transition', forbidden)


def setup(state='uncertain', count=3):
    plan, wire, journal = intent_inputs()
    journal = bd.write_intent_transition(journal, wire)
    if state == 'confirmed':
        journal = bd.resolve_write_intent(journal, wire['sha256'], snapshot(plan))
    elif state == 'quiescent':
        journal = bd.resolve_write_intent(journal, wire['sha256'], snapshot(plan, 1), proof(wire['sha256']))
    Path('inputs').mkdir(mode=0o700)
    Path('inputs/journal.yaml').write_text(yaml.safe_dump(journal))
    Path('inputs/snapshot.json').write_text(snapshot(plan, count))
    config = {'schema_version': 1, 'journal': 'journal.yaml', 'snapshot': 'snapshot.json'}
    Path('inputs/verify.yaml').write_text(yaml.safe_dump(config))
    return plan, wire, journal


def run(max_bytes=100000):
    return bd.verify_local_intents('inputs/verify.yaml', 'inputs', max_bytes)


def output():
    journal = yaml.safe_load(Path('inputs/journal.yaml').read_text())
    return Path('outputs/verification-' + journal['binding']['account_key'] + '.yaml')


def observation():
    artifact = yaml.safe_load(output().read_text())
    return next(iter(artifact['intents'].values()))


@pytest.mark.parametrize('state', ['uncertain', 'confirmed', 'quiescent'])
@pytest.mark.parametrize('count', [0, 1, 3])
def test_saved_presence_is_separate_from_recorded_state_and_never_changes_journal(state, count, monkeypatch):
    setup(state, count)
    before = Path('inputs/journal.yaml').read_bytes()
    def forbidden(*a, **k):
        raise AssertionError('Observation cannot resolve a journal')
    monkeypatch.setattr(bd, 'resolve_write_intent', forbidden)
    summary = run()
    seen = observation()
    assert seen['recorded_state'] == state and seen['present_markers'] == count
    assert seen['absent_markers'] == 3 - count
    assert seen['all_expected_exactly_present'] is (count == 3)
    assert Path('inputs/journal.yaml').read_bytes() == before
    assert summary['import_ready'] is False
    assert not list(Path('state').glob('writes-*'))
    if state == 'quiescent' and count == 3:
        codes = {code for v in seen['markers'].values() for code in v['codes']}
        assert 'PRESENT_MARKER_NOT_IN_RECORDED_ACCEPTED_SET' in codes
        assert not any('POST_' in code or 'LATE' in code for code in codes)


@pytest.mark.parametrize('change', ['fee', 'account', 'time', 'inactive', 'type', 'fx', 'duplicate', 'replacement-id', 'changed-marker'])
def test_conflicts_are_visible_across_all_rows_without_reclassifying_state(change):
    setup('confirmed')
    p = Path('inputs/snapshot.json')
    data = json.loads(p.read_text())
    first = data['activities'][0]
    if change == 'fee':
        first['fee'] += 1
    elif change == 'account':
        first['accountId'] = first['account']['id'] = 'another-account'
    elif change == 'time':
        first['date'] = first['date'].replace('T00:', 'T12:')
    elif change == 'inactive':
        first['isDraft'] = True
    elif change == 'type':
        first['type'] = 'DIVIDEND'
    elif change == 'fx':
        first['assetProfile']['currency'] = 'USD'
    elif change == 'replacement-id':
        first['id'] = 'replacement'
    elif change == 'changed-marker':
        first['comment'] = 'private free-text comment'
    else:
        another = copy.deepcopy(first)
        another['id'] = 'duplicate'
        data['activities'].append(another)
        data['count'] += 1
    p.write_text(json.dumps(data))
    before = Path('inputs/journal.yaml').read_bytes()
    run()
    observed = observation()
    assert observed['all_expected_exactly_present'] is False
    assert observed['recorded_state'] == 'confirmed'
    codes = {c for m in observed['markers'].values() for c in m['codes']}
    assert any('CONFLICT' in c or 'UNVERIFIED' in c or 'DUPLICATE' in c for c in codes)
    artifact = output().read_text()
    assert 'private free-text comment' not in artifact and 'body:' not in artifact
    assert Path('inputs/journal.yaml').read_bytes() == before


def test_empty_valid_journal_has_no_delivery_claim():
    _, _, journal = setup()
    journal['intents'] = {}
    Path('inputs/journal.yaml').write_text(yaml.safe_dump(journal))
    assert run()['intents'] == 0
    assert yaml.safe_load(output().read_text())['intents'] == {}


def test_safe_cli_and_exact_provenance_permissions(capsys):
    setup()
    assert bd.main(['verify', '--config', 'inputs/verify.yaml', '--input-root', 'inputs', '--max-bytes', '100000']) == 2
    text = capsys.readouterr().out
    assert json.loads(text)['intents_with_all_expected_exactly_present'] == 1
    assert 'BD#' not in text and 'synthetic' not in text and 'remote-' not in text
    data = yaml.safe_load(output().read_text())
    assert data['input_sha256']['journal'] == hashlib.sha256(Path('inputs/journal.yaml').read_bytes()).hexdigest()
    assert output().stat().st_mode & 0o777 == 0o600
    assert Path('outputs').stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('kind', ['config', 'journal', 'snapshot'])
def test_each_input_publication_collision_preserves_all_files(kind):
    setup()
    config = {'schema_version': 1, 'journal': 'inputs/journal.yaml', 'snapshot': 'inputs/snapshot.json'}
    Path('outputs').mkdir(mode=0o700)
    p = Path('inputs/verify.yaml')
    if kind == 'config':
        p = output()
    else:
        output().write_bytes(Path(config[kind]).read_bytes())
        config[kind] = str(output())
    p.write_text(yaml.safe_dump(config))
    before = {str(p): p.read_bytes() for root in ('inputs', 'outputs') for p in Path(root).rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match='OUTPUT_INPUT_COLLISION'):
        bd.verify_local_intents(p, '.', 100000)
    assert before == {str(p): p.read_bytes() for root in ('inputs', 'outputs') for p in Path(root).rglob('*') if p.is_file()}
    assert not Path('state').exists()


def test_hardlink_alias_is_refused_without_replacing_input():
    setup()
    Path('outputs').mkdir(mode=0o700)
    output().hardlink_to(Path('inputs/snapshot.json'))
    before = output().read_bytes()
    with pytest.raises(RuntimeError, match='OUTPUT_INPUT_COLLISION'):
        run()
    assert output().read_bytes() == before


def test_target_lock_and_invalid_snapshot_preserve_previous_observation():
    _, _, journal = setup()
    run()
    before = output().read_bytes()
    key = hashlib.sha256(journal['binding']['target_account_id'].encode()).hexdigest()
    with open('state/prepare-' + key + '.lock', 'r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='VERIFICATION_TARGET_LOCKED'):
            run()
    Path('inputs/snapshot.json').write_text('{"count":1,"activities":[]}')
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVITY_COUNT_MISMATCH'):
        run()
    assert output().read_bytes() == before


def test_output_budget_fails_without_replacement():
    setup()
    run()
    before = output().read_bytes()
    maximum = max(p.stat().st_size for p in Path('inputs').iterdir())
    with pytest.raises(RuntimeError, match='VERIFICATION_OUTPUT_LIMIT_EXCEEDED'):
        run(maximum)
    assert output().read_bytes() == before


@pytest.mark.parametrize('exponent', ['99999999', '-99999999'])
def test_scientific_decimal_shape_is_rejected_before_formatting(exponent, monkeypatch):
    setup()
    raw = Path('inputs/snapshot.json').read_text()
    data = json.loads(raw)
    marker = data['activities'][0]['fee']
    raw = raw.replace('"fee": ' + str(marker), '"fee": 1e' + exponent, 1)
    Path('inputs/snapshot.json').write_text(raw)
    def forbidden(*a):
        raise AssertionError('Oversized decimal must not reach formatting')
    # Journal wire validation does not need canonical decimal formatting.
    monkeypatch.setattr(bd, 'canonical_decimal', forbidden)
    with pytest.raises(RuntimeError, match='VERIFICATION_DECIMAL_LIMIT_EXCEEDED'):
        run()
    assert not Path('outputs').exists()


def test_marker_and_candidate_reference_boundaries(monkeypatch):
    setup()
    monkeypatch.setattr(bd, 'VERIFICATION_REFERENCE_LIMIT', 3)
    run()
    before = output().read_bytes()
    monkeypatch.setattr(bd, 'VERIFICATION_REFERENCE_LIMIT', 2)
    with pytest.raises(RuntimeError, match='VERIFICATION_MARKER_LIMIT_EXCEEDED'):
        run()
    monkeypatch.setattr(bd, 'VERIFICATION_REFERENCE_LIMIT', 3)
    p = Path('inputs/snapshot.json')
    data = json.loads(p.read_text())
    duplicate = copy.deepcopy(data['activities'][0]); duplicate['id'] = 'extra'
    data['activities'].append(duplicate); data['count'] += 1
    p.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match='VERIFICATION_CANDIDATE_LIMIT_EXCEEDED'):
        run()
    assert output().read_bytes() == before


def test_reused_historical_marker_and_duplicate_rows_count_before_materialization(monkeypatch):
    plan, wire, journal = setup('quiescent')
    # Explicit completed-absent old batch permits a different-shaped later intent.
    _, _, empty = intent_inputs()
    old = bd.resolve_write_intent(bd.write_intent_transition(empty, wire), wire['sha256'], snapshot(plan, 0), proof(wire['sha256']))
    marker, activity = next(iter(plan.items()))
    smaller = bd.build_wire_payload({marker: activity})
    journal = bd.write_intent_transition(old, smaller)
    Path('inputs/journal.yaml').write_text(yaml.safe_dump(journal))
    data = json.loads(Path('inputs/snapshot.json').read_text())
    duplicate = copy.deepcopy(data['activities'][0]); duplicate['id'] = 'duplicate'
    data['activities'].append(duplicate); data['count'] += 1
    Path('inputs/snapshot.json').write_text(json.dumps(data))
    monkeypatch.setattr(bd, 'VERIFICATION_REFERENCE_LIMIT', 4)
    with pytest.raises(RuntimeError, match='VERIFICATION_CANDIDATE_LIMIT_EXCEEDED'):
        run()


def test_captured_snapshot_digest_survives_external_change_after_read(monkeypatch):
    setup()
    original = bd.read_local_bytes
    captured = {}
    def read_then_change(path, root, maximum):
        raw = original(path, root, maximum)
        if Path(path).name == 'snapshot.json':
            captured['snapshot'] = raw
            Path(path).write_text('{"count":0,"activities":[]}')
        return raw
    monkeypatch.setattr(bd, 'read_local_bytes', read_then_change)
    assert run()['intents_with_all_expected_exactly_present'] == 1
    artifact = yaml.safe_load(output().read_text())
    assert artifact['input_sha256']['snapshot'] == hashlib.sha256(captured['snapshot']).hexdigest()


def test_full_snapshot_rejects_unrelated_redacted_row_without_replacement():
    setup()
    run()
    before = output().read_bytes()
    p = Path('inputs/snapshot.json')
    data = json.loads(p.read_text())
    extra = copy.deepcopy(data['activities'][0])
    extra.update(id='unrelated', comment=None, fee=None)
    data['activities'].append(extra); data['count'] += 1
    p.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match='REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED'):
        run()
    assert output().read_bytes() == before


def test_decimal_rendering_boundary_and_exact_difference(monkeypatch):
    setup()
    p = Path('inputs/snapshot.json')
    raw = p.read_text()
    first = json.loads(raw)['activities'][0]['fee']
    p.write_text(raw.replace('"fee": ' + str(first), '"fee": 12345.1', 1))
    monkeypatch.setattr(bd, 'VERIFICATION_DECIMAL_CHAR_LIMIT', 7)
    run()
    before = output().read_bytes()
    assert observation()['all_expected_exactly_present'] is False
    assert '12345.1' in before.decode()
    monkeypatch.setattr(bd, 'VERIFICATION_DECIMAL_CHAR_LIMIT', 6)
    with pytest.raises(RuntimeError, match='VERIFICATION_DECIMAL_LIMIT_EXCEEDED'):
        run()
    assert output().read_bytes() == before


def test_unrepresentable_scientific_exponent_has_safe_cli_error(capsys, caplog):
    setup()
    p = Path('inputs/snapshot.json')
    raw = p.read_text()
    first = json.loads(raw)['activities'][0]['fee']
    p.write_text(raw.replace('"fee": ' + str(first), '"fee": 1e9999999999999999999999999999', 1))
    assert bd.main(['verify', '--config', 'inputs/verify.yaml', '--input-root', 'inputs', '--max-bytes', '100000']) == 1
    assert capsys.readouterr().out == ''
    assert 'INVALID_REMOTE_ACTIVITY_JSON' in caplog.text
    assert '9999999999' not in caplog.text

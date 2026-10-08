import copy
import fcntl
import hashlib
import json
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_verify_cli import setup as verify_inputs, output as verify_output
from test_write_intents import different_review, snapshot, proof


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*a, **k):
        raise AssertionError('Offline compensation cannot resolve, persist or send')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(bd, 'persist_write_transition', forbidden)


def setup(state='confirmed', count=3):
    plan, wire, journal = verify_inputs(state, count)
    config = {'schema_version': 1, 'journal': 'journal.yaml', 'snapshot': 'snapshot.json', 'wire_sha256': wire['sha256']}
    Path('inputs/compensation.yaml').write_text(yaml.safe_dump(config))
    return plan, wire, journal


def run(maximum=100000):
    return bd.plan_local_compensation('inputs/compensation.yaml', 'inputs', maximum)


def output():
    journal = yaml.safe_load(Path('inputs/journal.yaml').read_text())
    return Path('outputs/rollback-plan-' + journal['binding']['account_key'] + '.yaml')


def report():
    return yaml.safe_load(output().read_text())


@pytest.mark.parametrize('count', [0, 1, 3])
def test_confirmed_associations_are_not_creation_or_delete_authority(count, monkeypatch):
    setup(count=count)
    bd.verify_local_intents('inputs/verify.yaml', 'inputs', 100000)
    verification_before = verify_output().read_bytes()
    journal_before = Path('inputs/journal.yaml').read_bytes()
    def forbidden(*a, **k):
        raise AssertionError('No resolution or publishing verify invocation')
    monkeypatch.setattr(bd, 'resolve_write_intent', forbidden)
    monkeypatch.setattr(bd, 'verify_local_intents', forbidden)
    assert run()['candidates'] == count
    seen = report()
    assert seen['candidate_selection_unambiguous'] is True
    assert len(seen['accepted_absent_markers']) == 3 - count
    assert seen['deletion_authorized'] is seen['import_ready'] is False
    assert 'CREATION_PROVENANCE_NOT_ESTABLISHED' in seen['boundaries']
    assert 'FRESH_REMOTE_REVALIDATION_REQUIRED' in seen['boundaries']
    assert Path('inputs/journal.yaml').read_bytes() == journal_before
    assert verify_output().read_bytes() == verification_before
    assert not list(Path('state').glob('writes-*'))


@pytest.mark.parametrize('state,count,candidates', [('uncertain', 3, 0), ('quiescent', 1, 1), ('quiescent', 3, 0), ('quiescent', 0, 0)])
def test_selection_respects_recorded_state_and_unaccepted_capture_presence(state, count, candidates):
    setup(state, count)
    assert run()['candidates'] == candidates
    seen = report()
    assert seen['selected_recorded_state'] == state
    if state == 'uncertain':
        assert seen['selection_codes'] == ['ACCOUNT_WRITE_UNCERTAIN']
    elif count == 3:
        assert seen['selection_codes'] == ['UNACCEPTED_SELECTED_MARKER_PRESENT']
    assert len(seen['unaccepted_markers']) == (3 if state == 'uncertain' else 2)
    assert not any('POST_' in c or 'LATE' in c for c in seen['selection_codes'])


def test_other_uncertain_intent_blocks_selected_confirmed_associations():
    plan, _, journal = setup()
    journal = bd.write_intent_transition(journal, different_review(plan))
    Path('inputs/journal.yaml').write_text(yaml.safe_dump(journal))
    assert run()['candidates'] == 0
    assert report()['selection_codes'] == ['ACCOUNT_WRITE_UNCERTAIN']


@pytest.mark.parametrize('same_marker', [True, False])
def test_structurally_valid_shared_accepted_id_blocks_all_candidates(same_marker):
    plan, wire, journal = setup()
    if same_marker:
        marker, activity = next(iter(plan.items()))
        other_wire = bd.build_wire_payload({marker: activity})
        remote = json.loads(snapshot({marker: activity}))
    else:
        other_wire = different_review(plan)
        remote = json.loads(snapshot(plan, 1))
        remote['activities'][0]['comment'] = next(iter(bd.reviewed_wire_rows(other_wire)))
    # Contradictory historical resolution is valid structurally, not safe selection.
    other = bd.resolve_write_intent(bd.write_intent_transition({'schema_version': 1, 'binding': journal['binding'], 'intents': {}}, other_wire), other_wire['sha256'], json.dumps(remote))
    journal['intents'].update(other['intents'])
    bd.validate_write_journal(journal)
    Path('inputs/journal.yaml').write_text(yaml.safe_dump(journal))
    assert run()['candidates'] == 0
    assert 'REMOTE_ID_SHARED_BY_RETAINED_INTENTS' in report()['selection_codes']


def test_historical_unaccepted_reused_marker_does_not_gain_selected_ownership():
    plan, wire, journal = setup('quiescent', 3)
    journal = bd.resolve_write_intent(bd.write_intent_transition({'schema_version': 1, 'binding': journal['binding'], 'intents': {}}, wire), wire['sha256'], snapshot(plan, 0), proof(wire['sha256']))
    marker, activity = next(iter(plan.items()))
    smaller = bd.build_wire_payload({marker: activity})
    journal = bd.resolve_write_intent(bd.write_intent_transition(journal, smaller), smaller['sha256'], snapshot({marker: activity}))
    Path('inputs/journal.yaml').write_text(yaml.safe_dump(journal))
    assert run()['candidates'] == 0
    assert report()['selection_codes'] == ['UNACCEPTED_SELECTED_MARKER_PRESENT']


@pytest.mark.parametrize('change', ['fee', 'account', 'context', 'replacement', 'changed-marker', 'duplicate'])
def test_any_accepted_conflict_suppresses_otherwise_exact_candidates(change):
    setup()
    p = Path('inputs/snapshot.json')
    data = json.loads(p.read_text())
    first = data['activities'][0]
    if change == 'fee':
        first['fee'] += 1
    elif change == 'account':
        first['accountId'] = first['account']['id'] = 'other'
    elif change == 'context':
        first['isDraft'] = True
    elif change == 'replacement':
        first['id'] = 'replacement'
    elif change == 'changed-marker':
        first['comment'] = 'private arbitrary comment'
    else:
        duplicate = copy.deepcopy(first); duplicate['id'] = 'duplicate'
        data['activities'].append(duplicate); data['count'] += 1
    p.write_text(json.dumps(data))
    assert run()['candidates'] == 0
    assert report()['candidate_selection_unambiguous'] is False
    assert 'private arbitrary comment' not in output().read_text()
    if change in ('replacement', 'changed-marker'):
        assert 'JOURNALED_REMOTE_ID_CONFLICT' in report()['selection_codes']


def test_exact_private_financial_evidence_and_reverse_display_order():
    setup()
    run()
    candidates = report()['candidates']
    assert [(c['observed_evidence']['operation_date'], c['wire_ordinal']) for c in candidates] == sorted([(c['observed_evidence']['operation_date'], c['wire_ordinal']) for c in candidates], reverse=True)
    for c in candidates:
        assert c['financial_fingerprint'] == bd.activity_financial_fingerprint(c['observed_evidence'])
        assert isinstance(c['observed_evidence']['unit_price'], str)
    assert 'body:' not in output().read_text() and 'reviewed_by' not in output().read_text()


@pytest.mark.parametrize('kind', ['config', 'journal', 'snapshot'])
def test_each_publication_input_alias_preserves_all_originals(kind):
    _, wire, _ = setup()
    config = {'schema_version': 1, 'journal': 'inputs/journal.yaml', 'snapshot': 'inputs/snapshot.json', 'wire_sha256': wire['sha256']}
    Path('outputs').mkdir(mode=0o700)
    p = Path('inputs/compensation.yaml')
    if kind == 'config':
        p = output()
    else:
        output().write_bytes(Path(config[kind]).read_bytes())
        config[kind] = str(output())
    p.write_text(yaml.safe_dump(config))
    before = {str(p): p.read_bytes() for root in ('inputs', 'outputs') for p in Path(root).rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match='OUTPUT_INPUT_COLLISION'):
        bd.plan_local_compensation(p, '.', 100000)
    assert before == {str(p): p.read_bytes() for root in ('inputs', 'outputs') for p in Path(root).rglob('*') if p.is_file()}
    assert not Path('state').exists()


def test_hardlink_and_lock_failure_preserve_output_and_journal():
    _, _, journal = setup()
    Path('outputs').mkdir(mode=0o700)
    output().hardlink_to(Path('inputs/snapshot.json'))
    before = output().read_bytes()
    with pytest.raises(RuntimeError, match='OUTPUT_INPUT_COLLISION'):
        run()
    assert output().read_bytes() == before
    output().unlink()
    run()
    before = output().read_bytes()
    key = hashlib.sha256(journal['binding']['target_account_id'].encode()).hexdigest()
    with open('state/prepare-' + key + '.lock', 'r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='COMPENSATION_TARGET_LOCKED'):
            run()
    assert output().read_bytes() == before


@pytest.mark.parametrize('invalid', ['boolean-schema', 'unknown-key', 'bad-digest', 'absent-digest', 'unrelated-redacted', 'budget', 'decimal', 'references'])
def test_invalid_or_budgeted_capture_preserves_previous_output(invalid, monkeypatch):
    setup()
    run()
    before = output().read_bytes()
    p = Path('inputs/compensation.yaml')
    config = yaml.safe_load(p.read_text())
    maximum = 100000
    if invalid == 'boolean-schema':
        config['schema_version'] = True
    elif invalid == 'unknown-key':
        config['delete'] = True
    elif invalid == 'bad-digest':
        config['wire_sha256'] = 'INVALID'
    elif invalid == 'absent-digest':
        config['wire_sha256'] = 'f' * 64
    elif invalid == 'unrelated-redacted':
        source = Path('inputs/snapshot.json'); data = json.loads(source.read_text())
        extra = copy.deepcopy(data['activities'][0]); extra.update(id='unrelated', comment=None, fee=None)
        data['activities'].append(extra); data['count'] += 1
        source.write_text(json.dumps(data))
    elif invalid == 'budget':
        maximum = max(p.stat().st_size for p in Path('inputs').iterdir())
    elif invalid == 'decimal':
        source = Path('inputs/snapshot.json'); raw = source.read_text()
        first = json.loads(raw)['activities'][0]['fee']
        source.write_text(raw.replace('"fee": ' + str(first), '"fee": 1e99999999', 1))
    else:
        monkeypatch.setattr(bd, 'VERIFICATION_REFERENCE_LIMIT', 2)
    p.write_text(yaml.safe_dump(config))
    with pytest.raises(RuntimeError):
        run(maximum)
    assert output().read_bytes() == before


def test_safe_cli_provenance_modes_and_no_resolution(monkeypatch, capsys):
    setup('quiescent', 1)
    before = Path('inputs/journal.yaml').read_bytes()
    original = bd.read_local_bytes
    captured = {}
    def change_after_capture(path, root, maximum):
        raw = original(path, root, maximum)
        captured[Path(path).name] = raw
        if Path(path).name == 'snapshot.json':
            Path(path).write_text('{"count":0,"activities":[]}')
        return raw
    monkeypatch.setattr(bd, 'read_local_bytes', change_after_capture)
    def forbidden(*a, **k):
        raise AssertionError('No resolution')
    monkeypatch.setattr(bd, 'resolve_write_intent', forbidden)
    assert bd.main(['rollback-plan', '--config', 'inputs/compensation.yaml', '--input-root', 'inputs', '--max-bytes', '100000']) == 2
    safe = capsys.readouterr().out
    assert json.loads(safe)['candidates'] == 1
    assert 'BD#' not in safe and 'remote-' not in safe and 'synthetic' not in safe
    assert report()['input_sha256']['snapshot'] == hashlib.sha256(captured['snapshot.json']).hexdigest()
    assert output().stat().st_mode & 0o777 == 0o600
    assert Path('outputs').stat().st_mode & 0o777 == 0o700
    assert Path('inputs/journal.yaml').read_bytes() == before

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_write_intents import setup, snapshot, proof
from test_adoption import row


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*a, **k):
        raise AssertionError('No real network in lab-dispatch tests')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def inputs():
    plan, _, journal = setup()
    marker, activity = next(iter(plan.items()))
    one = {marker: activity}
    wire = bd.build_wire_payload(one)
    unrelated = copy.deepcopy(activity); unrelated['id'] = 'unrelated-comment'
    baseline = row(unrelated, 'baseline', owned=False)
    baseline['date'] = '2026-08-01T12:00:00Z'
    baseline['tags'] = [{'id': 'ordinary-b'}, {'id': 'ordinary-a'}]
    remote = row(activity, 'created', owned=True)
    return one, wire, journal['binding'], baseline, remote


def raw(rows):
    return json.dumps({'count': len(rows), 'activities': rows}).encode()


def journal(binding):
    return yaml.safe_load(Path('state/writes-' + hashlib.sha256(binding['target_account_id'].encode()).hexdigest() + '.yaml').read_bytes())


def call(wire, binding, baseline, responses, calls=None):
    calls = [] if calls is None else calls
    def request(method, path, body):
        calls.append((method, path, body))
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response
    return bd.dispatch_single_lab_intent('state', binding, wire, raw([baseline]), 100000, request)


def success(base, remote):
    return [(200, raw([base])), (201, json.dumps({'activities': [remote]}).encode()), (200, raw([base, remote]))]


def test_exact_body_and_real_competing_locks_held_at_every_boundary():
    _, wire, binding, base, remote = inputs()
    responses = success(base, remote)
    calls = []
    def request(method, path, body):
        for name in ('prepare-' + hashlib.sha256(binding['target_account_id'].encode()).hexdigest(), 'account-' + binding['account_key']):
            with open('state/' + name + '.lock', 'r+') as competing:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(competing, fcntl.LOCK_EX | fcntl.LOCK_NB)
                assert Path(competing.name).stat().st_mode & 0o777 == 0o600
        if method == 'POST':
            assert journal(binding)['intents'][wire['sha256']]['state'] == 'uncertain'
            assert body is wire['body']
        calls.append(method)
        return responses.pop(0)
    result = bd.dispatch_single_lab_intent('state', binding, wire, raw([base]), 100000, request)
    assert calls == ['GET', 'POST', 'GET'] and result['accepted'] == 1
    assert result['import_ready'] is False
    assert journal(binding)['intents'][wire['sha256']]['state'] == 'confirmed'
    # Both locks released after success.
    for p in Path('state').glob('*.lock'):
        with p.open('r+') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


@pytest.mark.parametrize('change', ['time', 'tags', 'flags', 'profile', 'fee', 'marker', 'account', 'add', 'remove'])
@pytest.mark.parametrize('phase', ['baseline', 'readback'])
def test_every_persistent_semantic_drift_blocks_even_if_source_exact(change, phase):
    _, wire, binding, base, remote = inputs()
    if change == 'flags':
        base['isDraft'] = True
    if change == 'profile':
        base['type'] = 'DIVIDEND'
    changed = copy.deepcopy(base)
    if change == 'time': changed['date'] = '2026-08-01T13:00:00Z'
    elif change == 'tags': changed['tags'].append({'id': 'ordinary-c'})
    elif change == 'flags': changed['isExcluded'] = True
    elif change == 'profile': changed['assetProfile']['symbol'] = 'OTHER.PA'
    elif change == 'fee': changed['fee'] += 1
    elif change == 'marker': changed['comment'] = 'different'
    elif change == 'account': changed['accountId'] = changed['account']['id'] = 'other'
    rows = [] if change == 'remove' else [changed]
    if change == 'add':
        another = copy.deepcopy(base); another['id'] = 'extra'; rows.append(another)
    responses = success(base, remote)
    responses[0 if phase == 'baseline' else 2] = (200, raw(rows + ([] if phase == 'baseline' else [remote])))
    calls = []
    with pytest.raises(RuntimeError, match='LAB_DISPATCH_(BASELINE_CHANGED|TRANSITION_CONFLICT)'):
        call(wire, binding, base, responses, calls)
    assert sum(c[0] == 'POST' for c in calls) == (0 if phase == 'baseline' else 1)
    if phase == 'readback':
        assert journal(binding)['intents'][wire['sha256']]['state'] == 'uncertain'


def test_list_tag_order_and_equivalent_full_instant_are_equal():
    _, wire, binding, base, remote = inputs()
    equivalent = copy.deepcopy(base)
    equivalent['tags'].reverse()
    equivalent['date'] = '2026-08-01T14:00:00+02:00'
    assert call(wire, binding, base, [(200, raw([equivalent])), (201, json.dumps({'activities': [remote]}).encode()), (200, raw([remote, equivalent]))])['accepted'] == 1


@pytest.mark.parametrize('failure', ['timeout', 'error-status', 'skip', 'invalid-json', 'bool-amount', 'huge-exponent', 'nan', 'bad-id', 'oversized', 'shape'])
def test_ambiguous_acceptance_never_reads_back_retries_or_clears_fence(failure):
    _, wire, binding, base, remote = inputs()
    response = (201, json.dumps({'activities': [remote]}).encode())
    if failure == 'timeout': response = TimeoutError('SECRET-CALLBACK-TEXT')
    elif failure == 'error-status': response = (500, b'SECRET-SERVER-TEXT')
    elif failure == 'skip': response = (201, b'{"activities":[]}')
    elif failure == 'invalid-json': response = (201, b'not-json')
    elif failure == 'bool-amount':
        remote['fee'] = True; response = (201, json.dumps({'activities': [remote]}).encode())
    elif failure == 'huge-exponent': response = (201, b'{"metadata":1e99999999,"activities":[]}')
    elif failure == 'nan': response = (201, b'{"metadata":NaN,"activities":[]}')
    elif failure == 'bad-id':
        remote['id'] = base['id']; response = (201, json.dumps({'activities': [remote]}).encode())
    elif failure == 'oversized': response = (201, b'x' * 100001)
    elif failure == 'shape': response = (True, b'{}')
    calls = []
    with pytest.raises(RuntimeError) as error:
        call(wire, binding, base, [(200, raw([base])), response], calls)
    assert 'SECRET' not in str(error.value) and error.value.__cause__ is None
    assert [c[0] for c in calls] == ['GET', 'POST']
    assert journal(binding)['intents'][wire['sha256']]['state'] == 'uncertain'
    again = []
    with pytest.raises(RuntimeError, match='ACCOUNT_WRITE_UNCERTAIN'):
        call(wire, binding, base, [], again)
    assert again == []


@pytest.mark.parametrize('failure', ['absent', 'replacement-id', 'fee', 'inactive', 'time', 'duplicate', 'transport', 'status'])
def test_readback_conflict_or_failure_keeps_uncertainty(failure):
    _, wire, binding, base, remote = inputs()
    response = success(base, remote)
    altered = copy.deepcopy(remote)
    if failure == 'replacement-id': altered['id'] = 'replacement'
    elif failure == 'fee': altered['fee'] += 1
    elif failure == 'inactive': altered['isDraft'] = True
    elif failure == 'time': altered['date'] = altered['date'].replace('T00:', 'T12:')
    rows = [base] if failure == 'absent' else [base, altered]
    if failure == 'duplicate':
        duplicate = copy.deepcopy(remote); duplicate['id'] = 'duplicate'; rows.append(duplicate)
    response[2] = TimeoutError('SECRET') if failure == 'transport' else (500, b'{}') if failure == 'status' else (200, raw(rows))
    with pytest.raises(RuntimeError): call(wire, binding, base, response)
    assert journal(binding)['intents'][wire['sha256']]['state'] == 'uncertain'


@pytest.mark.parametrize('state', ['uncertain', 'confirmed', 'quiescent'])
def test_every_retained_digest_rejects_before_any_callback(state):
    plan, wire, binding, base, remote = inputs()
    bd.persist_write_transition('state', binding, 100000, 'intent', review=wire)
    if state != 'uncertain':
        bd.persist_write_transition('state', binding, 100000, 'resolve', digest=wire['sha256'], raw_snapshot=snapshot(plan, None if state == 'confirmed' else 0), completion_evidence=None if state == 'confirmed' else proof(wire['sha256']))
    calls = []
    with pytest.raises(RuntimeError, match='ACCOUNT_WRITE_UNCERTAIN|WRITE_INTENT_ALREADY_RECORDED'):
        call(wire, binding, base, [], calls)
    assert calls == []


@pytest.mark.parametrize('stage', ['intent-before', 'intent-after', 'resolve-before', 'resolve-after'])
def test_persistence_failure_before_after_rename_never_succeeds_or_replays(monkeypatch, stage):
    _, wire, binding, base, remote = inputs()
    write = bd.atomic_private_yaml
    def publication(path, data):
        if Path(path).name.startswith('writes-'):
            state = next(iter(data['intents'].values()))['state']
            wanted = 'uncertain' if stage.startswith('intent') else 'confirmed'
            if state == wanted:
                if stage.endswith('after'): write(path, data)
                raise OSError('SECRET-PATH')
        return write(path, data)
    monkeypatch.setattr(bd, 'atomic_private_yaml', publication)
    calls = []
    with pytest.raises(RuntimeError, match='LAB_DISPATCH_PERSISTENCE_FAILED'):
        call(wire, binding, base, success(base, remote), calls)
    assert sum(c[0] == 'POST' for c in calls) == (0 if stage.startswith('intent') else 1)
    if stage != 'intent-before':
        state = journal(binding)['intents'][wire['sha256']]['state']
        assert state == ('confirmed' if stage == 'resolve-after' else 'uncertain')
        monkeypatch.setattr(bd, 'atomic_private_yaml', write)
        with pytest.raises(RuntimeError, match='ACCOUNT_WRITE_UNCERTAIN|WRITE_INTENT_ALREADY_RECORDED'):
            call(wire, binding, base, [])


@pytest.mark.parametrize('invalid', ['batch', 'binding', 'size', 'bool-limit', 'marker-elsewhere', 'redacted', 'decimal'])
def test_preflight_invalidity_never_calls_adapter(invalid):
    _, wire, binding, base, remote = inputs()
    limit = 100000
    if invalid == 'batch': wire = setup()[1]
    elif invalid == 'binding': binding = {**binding, 'target_account_id': 'other'}
    elif invalid == 'size': limit = 1
    elif invalid == 'bool-limit': limit = True
    elif invalid == 'marker-elsewhere':
        base['comment'] = remote['comment']; base['type'] = 'DIVIDEND'
    elif invalid == 'redacted': base['fee'] = None
    baseline = raw([base])
    if invalid == 'decimal': baseline = baseline.replace(b'"fee": ', b'"irrelevant": 1e-99999999, "fee": ', 1)
    calls = []
    with pytest.raises(RuntimeError):
        bd.dispatch_single_lab_intent('state', binding, wire, baseline, limit, lambda *a: calls.append(a))
    assert not calls


def test_second_lock_failure_closes_first_descriptor_and_existing_locks_are_private():
    _, wire, binding, base, _ = inputs()
    Path('state').mkdir(mode=0o700)
    namespace = Path('state/account-' + binding['account_key'] + '.lock')
    namespace.touch(mode=0o644)
    target = Path('state/prepare-' + hashlib.sha256(binding['target_account_id'].encode()).hexdigest() + '.lock')
    with namespace.open('r+') as busy:
        fcntl.flock(busy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='WRITE_ACCOUNT_LOCKED'):
            call(wire, binding, base, [])
        with target.open('r+') as first:
            fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert namespace.stat().st_mode & 0o777 == 0o600


def test_nonregular_lock_fails_and_closes_all_descriptors():
    _, wire, binding, base, _ = inputs()
    Path('state').mkdir(mode=0o700)
    namespace = Path('state/account-' + binding['account_key'] + '.lock')
    os.mkfifo(namespace)
    with pytest.raises(RuntimeError, match='INVALID_WRITE_LOCK'):
        call(wire, binding, base, [])
    target = Path('state/prepare-' + hashlib.sha256(binding['target_account_id'].encode()).hexdigest() + '.lock')
    with target.open('r+') as first:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)


def test_real_postrename_directory_fsync_failure_retains_visible_tombstone(monkeypatch):
    _, wire, binding, base, remote = inputs()
    original = bd.os.fsync
    def fail_confirmed_directory(descriptor):
        files = list(Path('state').glob('writes-*'))
        if stat.S_ISDIR(os.fstat(descriptor).st_mode) and files and journal(binding)['intents'][wire['sha256']]['state'] == 'confirmed':
            raise OSError('SECRET-DIRECTORY')
        return original(descriptor)
    monkeypatch.setattr(bd.os, 'fsync', fail_confirmed_directory)
    with pytest.raises(RuntimeError, match='LAB_DISPATCH_PERSISTENCE_FAILED'):
        call(wire, binding, base, success(base, remote))
    assert journal(binding)['intents'][wire['sha256']]['state'] == 'confirmed'
    monkeypatch.setattr(bd.os, 'fsync', original)
    with pytest.raises(RuntimeError, match='WRITE_INTENT_ALREADY_RECORDED'):
        call(wire, binding, base, [])
    changed = bd.reviewed_wire_rows(wire)
    marker = next(iter(changed))
    plan = inputs()[0]
    plan[marker]['fee'] = '1.23'
    rewritten = bd.build_wire_payload(plan)
    assert rewritten['sha256'] != wire['sha256']
    with pytest.raises(RuntimeError, match='WRITE_INTENT_PREVIOUSLY_ACCEPTED'):
        call(rewritten, binding, base, [])


def test_future_eligibility_boundary_is_conservative_semantic_drift(monkeypatch):
    _, wire, binding, base, remote = inputs()
    actual = bd.datetime
    instants = iter([actual(2026, 10, 9, tzinfo=bd.timezone.utc), actual(2026, 10, 9, tzinfo=bd.timezone.utc), actual(2026, 10, 11, tzinfo=bd.timezone.utc)])
    from types import SimpleNamespace
    clock = SimpleNamespace(fromisoformat=actual.fromisoformat, strptime=actual.strptime, now=lambda *a: next(instants))
    base['date'] = '2026-10-10T12:00:00Z'
    # Wire canonical validation also needs datetime.strptime, not current time.
    monkeypatch.setattr(bd, 'datetime', clock)
    calls = []
    with pytest.raises(RuntimeError, match='LAB_DISPATCH_BASELINE_CHANGED'):
        call(wire, binding, base, [(200, raw([base]))], calls)
    assert [c[0] for c in calls] == ['GET']

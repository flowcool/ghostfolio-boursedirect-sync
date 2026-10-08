import copy
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


def setup():
    plan = prepared()
    first = next(iter(plan.values()))
    binding = {k: first[k] for k in ('account_key', 'target_account_id')}
    return plan, bd.build_wire_payload(plan), {'schema_version': 1, 'binding': binding, 'intents': {}}


def snapshot(plan, count=None):
    rows = [row(a, 'remote-' + str(i), owned=True) for i, a in enumerate(plan.values())]
    if count is not None:
        rows = rows[:count]
    return json.dumps({'count': len(rows), 'activities': rows})


def proof(digest):
    return {'kind': 'independently_cancelled', 'reviewed_by': 'synthetic-operator',
            'reference': 'synthetic-isolated-completion-evidence', 'wire_sha256': digest}


def different_review(plan):
    changed = copy.deepcopy(plan)
    marker, activity = next(iter(changed.items()))
    del changed[marker]
    new_marker = marker[:-1] + ('a' if marker[-1] != 'a' else 'b')
    changed[new_marker] = {**activity, 'id': new_marker}
    return bd.build_wire_payload({new_marker: changed[new_marker]})


def test_intent_is_uncertain_before_any_dispatch_and_blocks_whole_account():
    plan, review, journal = setup()
    before = copy.deepcopy(journal)
    pending = bd.write_intent_transition(journal, review)
    assert journal == before
    assert pending['intents'][review['sha256']]['state'] == 'uncertain'
    for candidate in (review, different_review(plan)):
        with pytest.raises(RuntimeError, match='ACCOUNT_WRITE_UNCERTAIN'):
            bd.write_intent_transition(pending, candidate)


@pytest.mark.parametrize('count', [0, 1, 2])
def test_empty_or_partial_get_never_clears_fence(count):
    plan, review, journal = setup()
    pending = bd.write_intent_transition(journal, review)
    before = copy.deepcopy(pending)
    with pytest.raises(RuntimeError, match='INDEPENDENT_COMPLETION_EVIDENCE_REQUIRED'):
        bd.resolve_write_intent(pending, review['sha256'], snapshot(plan, count))
    assert pending == before


def test_complete_exact_positive_snapshot_resolves_and_retains_tombstone():
    plan, review, journal = setup()
    pending = bd.write_intent_transition(journal, review)
    raw = snapshot(plan)
    complete = bd.resolve_write_intent(pending, review['sha256'], raw)
    evidence = complete['intents'][review['sha256']]
    assert evidence['state'] == 'confirmed' and len(evidence['resolution']['accepted']) == 3
    assert evidence['resolution']['snapshot_sha256'] == hashlib.sha256(raw.encode()).hexdigest()
    bd.validate_write_journal(complete)
    with pytest.raises(RuntimeError, match='WRITE_INTENT_ALREADY_RECORDED'):
        bd.write_intent_transition(complete, review)
    assert len(bd.write_intent_transition(complete, different_review(plan))['intents']) == 2


@pytest.mark.parametrize('count', [0, 1, 2])
def test_reviewed_independent_completion_can_resolve_missing_rows_without_replay(count):
    plan, review, journal = setup()
    pending = bd.write_intent_transition(journal, review)
    complete = bd.resolve_write_intent(pending, review['sha256'], snapshot(plan, count), proof(review['sha256']))
    intent = complete['intents'][review['sha256']]
    assert intent['state'] == 'quiescent' and len(intent['resolution']['accepted']) == count
    bd.validate_write_journal(complete)
    with pytest.raises(RuntimeError, match='WRITE_INTENT_ALREADY_RECORDED'):
        bd.write_intent_transition(complete, review)


@pytest.mark.parametrize('key,value', [('kind', 'timeout'), ('wire_sha256', 'other'), ('reviewed_by', ''), ('reference', True)])
def test_elapsed_time_self_assertions_and_wrong_digest_are_not_completion_proof(key, value):
    plan, review, journal = setup()
    evidence = proof(review['sha256'])
    evidence[key] = value
    with pytest.raises(RuntimeError, match='INDEPENDENT_COMPLETION_EVIDENCE_REQUIRED'):
        bd.resolve_write_intent(bd.write_intent_transition(journal, review), review['sha256'], snapshot(plan, 0), evidence)


@pytest.mark.parametrize('change', ['fee', 'account', 'date', 'inactive', 'duplicate'])
def test_conflicting_readback_cannot_be_excused_by_completion_proof(change):
    plan, review, journal = setup()
    data = json.loads(snapshot(plan))
    first = data['activities'][0]
    if change == 'fee':
        first['fee'] = 999
    elif change == 'account':
        first['accountId'] = first['account']['id'] = 'other-account'
    elif change == 'date':
        first['date'] = first['date'].replace('T00:', 'T12:')
    elif change == 'inactive':
        first['isDraft'] = True
    else:
        duplicate = copy.deepcopy(first)
        duplicate['id'] = 'duplicate-remote'
        data['activities'].append(duplicate)
        data['count'] += 1
    with pytest.raises(RuntimeError, match='WRITE_READBACK'):
        bd.resolve_write_intent(bd.write_intent_transition(journal, review), review['sha256'], json.dumps(data), proof(review['sha256']))


def test_unrelated_existing_activity_not_part_of_accepted_batch():
    plan, review, journal = setup()
    data = json.loads(snapshot(plan))
    other = copy.deepcopy(data['activities'][0])
    other['id'], other['comment'] = 'unrelated', 'another-importer'
    data['activities'].append(other)
    data['count'] += 1
    complete = bd.resolve_write_intent(bd.write_intent_transition(journal, review), review['sha256'], json.dumps(data))
    assert len(complete['intents'][review['sha256']]['resolution']['accepted']) == 3


def test_different_digest_cannot_resubmit_a_previously_accepted_marker():
    plan, review, journal = setup()
    complete = bd.resolve_write_intent(bd.write_intent_transition(journal, review), review['sha256'], snapshot(plan))
    marker, activity = next(iter(plan.items()))
    smaller = bd.build_wire_payload({marker: activity})
    assert smaller['sha256'] != review['sha256']
    with pytest.raises(RuntimeError, match='WRITE_INTENT_PREVIOUSLY_ACCEPTED'):
        bd.write_intent_transition(complete, smaller)


def test_disk_fence_survives_reload_and_blocks_empty_readback(tmp_path):
    plan, review, journal = setup()
    root = tmp_path / 'state'
    binding = journal['binding']
    result = bd.persist_write_transition(root, binding, 100000, 'intent', review=review)
    assert result['account_fenced'] and result['import_ready'] is False
    for candidate in (review, different_review(plan)):
        with pytest.raises(RuntimeError, match='ACCOUNT_WRITE_UNCERTAIN'):
            bd.persist_write_transition(root, binding, 100000, 'intent', review=candidate)
    with pytest.raises(RuntimeError, match='INDEPENDENT_COMPLETION_EVIDENCE_REQUIRED'):
        bd.persist_write_transition(root, binding, 100000, 'resolve', digest=review['sha256'], raw_snapshot=snapshot(plan, 0))
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in root.iterdir())
    settled = bd.persist_write_transition(root, binding, 100000, 'resolve', digest=review['sha256'], raw_snapshot=snapshot(plan))
    assert not settled['account_fenced'] and settled['import_ready'] is False
    assert bd.persist_write_transition(root, binding, 100000, 'intent', review=different_review(plan))['account_fenced']


def test_crash_after_durable_rename_remains_fenced_on_next_invocation(tmp_path, monkeypatch):
    plan, review, journal = setup()
    root = tmp_path / 'state'
    writer = bd.atomic_private_yaml
    def crash(path, value):
        writer(path, value)
        if path.name.startswith('writes-'):
            raise OSError('synthetic crash after persisted intent before caller returns')
    monkeypatch.setattr(bd, 'atomic_private_yaml', crash)
    with pytest.raises(OSError):
        bd.persist_write_transition(root, journal['binding'], 100000, 'intent', review=review)
    monkeypatch.setattr(bd, 'atomic_private_yaml', writer)
    with pytest.raises(RuntimeError, match='ACCOUNT_WRITE_UNCERTAIN'):
        bd.persist_write_transition(root, journal['binding'], 100000, 'intent', review=different_review(plan))


def test_failed_persist_cannot_return_an_intent_to_a_future_dispatcher(tmp_path, monkeypatch):
    _, review, journal = setup()
    def failed(*args):
        raise OSError('synthetic persistence failure')
    monkeypatch.setattr(bd, 'atomic_private_yaml', failed)
    with pytest.raises(OSError):
        bd.persist_write_transition(tmp_path / 'state', journal['binding'], 100000, 'intent', review=review)


@pytest.mark.parametrize('change', ['binding', 'body', 'state', 'resolution'])
def test_corrupted_persisted_journal_fails_closed(change):
    _, review, journal = setup()
    pending = bd.write_intent_transition(journal, review)
    intent = pending['intents'][review['sha256']]
    if change == 'binding':
        pending['binding']['target_account_id'] = 'different'
    elif change == 'body':
        intent['body'] += ' '
    elif change == 'state':
        intent['state'] = 'complete'
    else:
        intent['resolution'] = {'automatic': True}
    with pytest.raises(RuntimeError):
        bd.validate_write_journal(pending)


def test_changed_account_binding_and_oversized_new_journal_rejected(tmp_path):
    _, review, journal = setup()
    with pytest.raises(RuntimeError, match='WRITE_JOURNAL_TOO_LARGE'):
        bd.persist_write_transition(tmp_path / 'state', journal['binding'], 10, 'intent', review=review)
    altered = {**journal['binding'], 'account_key': '00000000-0000-4000-8000-000000000000'}
    with pytest.raises(RuntimeError, match='WRITE_JOURNAL_BINDING_CONFLICT'):
        bd.persist_write_transition(tmp_path / 'state', altered, 100000, 'intent', review=review)


def test_same_namespace_cannot_move_to_another_target_to_escape_fence(tmp_path):
    plan, review, journal = setup()
    root = tmp_path / 'state'
    bd.persist_write_transition(root, journal['binding'], 100000, 'intent', review=review)
    altered = copy.deepcopy(plan)
    for activity in altered.values():
        activity['target_account_id'] = 'changed-target'
    binding = {**journal['binding'], 'target_account_id': 'changed-target'}
    with pytest.raises(RuntimeError, match='WRITE_JOURNAL_BINDING_CONFLICT'):
        bd.persist_write_transition(root, binding, 100000, 'intent', review=bd.build_wire_payload(altered))

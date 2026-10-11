"""Offline replay integrity checks; no host, vault or broker access."""
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest
import yaml

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPT_ROOT))
spec = importlib.util.spec_from_file_location('source_connection', SCRIPT_ROOT / 'source_connection.py')
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.fixture
def saved(tmp_path):
    lab = tmp_path / 'inputs/lab'
    (lab / 'host').mkdir(parents=True, mode=0o700)
    lab.chmod(0o700)
    proofs = {
        'historical_authentication_manifest': {'authentication': {'password_submissions': 1,
            'totp_submissions': 1, 'credentials_persisted': False}},
        'historical_authentication_journal': {'accounts': {'synthetic': {'stage': 'AUTHENTICATED'}}},
        'vault_inspection': dict.fromkeys(('exact_name_unique', 'broker_uri_verified',
            'credential_fields_verified', 'totp_profile_verified'), True),
        'public_login': {'synthetic': True},
        'auth_app_source': {'http_status': 200, 'credentials_read': False,
            'authentication_requests': 0, 'owned_browser_exit_verified': True},
        'browser_idle': {'browser_init': True, 'counts': {'live_chrome': 0,
            'zombies': 0, 'unexpected_proc_errors': 0}},
    }
    references = {}
    for name, row in proofs.items():
        path = lab / (name + '.yaml')
        replay.private._publish(path, row, exclusive=True)
        references[name] = {'path': str(path.relative_to(tmp_path)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    body = lab / 'body.js'
    body.write_bytes(b'/* inert synthetic source */')
    body.chmod(0o600)
    references['auth_app_body'] = {'path': str(body.relative_to(tmp_path)),
        'sha256': hashlib.sha256(body.read_bytes()).hexdigest()}
    helpers = {}
    for name in ('qualify.py', 'attest.py', 'broker-attest.py', 'broker-stop.py', 'stop.py', 'provision.py'):
        path = lab / 'host' / name
        path.write_bytes(b'# synthetic helper, never imported\n')
        path.chmod(0o600)
        helpers[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    contract = lab / 'source.yaml'
    replay.private._publish(contract, {'roles': {}, 'expected_account_inventory':
        {'accounts': [{'verified': False}, {'verified': False}]}}, exclusive=True)
    replay.private._publish(lab / 'replay.yaml', {'schema_version': 1, 'evidence': references,
        'trusted_helpers': helpers, 'source_contract': str(contract.relative_to(tmp_path))}, exclusive=True)
    return tmp_path, lab


def test_saved_success_is_reused_without_claiming_current_authentication(saved, monkeypatch):
    root, lab = saved
    monkeypatch.setattr(replay, 'helper', lambda *args: pytest.fail('offline check imported a live adapter'))
    inventory, report = replay.inspect_saved(root, lab)
    assert report['historical_authentication_confirmed'] is True
    assert report['current_collector_authentication_ready'] is False
    assert report['declared_accounts'] == 2
    assert report['verified_account_bindings'] == 0
    assert 'password_submit' in report['missing_request_roles']
    before = {p: p.read_bytes() for p in lab.rglob('*') if p.is_file()}
    assert replay.inspect_saved(root, lab) == (inventory, report)
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize('change', ('changed', 'missing', 'public', 'symlink'))
def test_untrusted_saved_source_refuses_before_any_live_adapter(saved, change):
    root, lab = saved
    path = lab / 'body.js'
    if change == 'changed':
        path.write_bytes(b'changed')
    elif change == 'missing':
        path.unlink()
    elif change == 'public':
        path.chmod(0o644)
    else:
        path.unlink()
        path.symlink_to(lab / 'source.yaml')
    with pytest.raises(RuntimeError):
        replay.inspect_saved(root, lab)


def test_changed_control_helper_refuses(saved):
    root, lab = saved
    (lab / 'host/qualify.py').write_bytes(b'# changed\n')
    with pytest.raises(RuntimeError, match='SOURCE_REPLAY_HELPER_CHANGED'):
        replay.inspect_saved(root, lab)


def test_successful_hashes_do_not_turn_uncertain_auth_into_success(saved):
    root, lab = saved
    path = lab / 'historical_authentication_journal.yaml'
    replay.private._publish(path, {'accounts': {'synthetic': {'stage': 'OUTCOME_UNCERTAIN'}}})
    index = replay.private._read(lab / 'replay.yaml')
    index['evidence']['historical_authentication_journal']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    replay.private._publish(lab / 'replay.yaml', index)
    with pytest.raises(RuntimeError):
        replay.inspect_saved(root, lab)

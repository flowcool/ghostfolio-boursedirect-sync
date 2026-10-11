"""Real private IPC composition using synthetic CLI replies, never host access."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_vault_inspection as inspection


@pytest.mark.parametrize('fault', [None, 'hash', 'logout', 'status'])
def test_private_metadata_inspection_never_exports_credentials_or_requests_totp(tmp_path, fault):
    configuration = {'schema_version': 3, 'vaultOrigin': 'https://vault.synthetic.invalid',
        'binding': {'name': 'boursedirect.fr'}, 'cli': {'path': '/usr/local/bin/bw',
            'sha256': 'c' * 64, 'version': 'synthetic-1', 'defaultsVerified': False}}
    identifier = 'a' * 64
    trace = tmp_path / 'commands.json'
    rpc = []

    def attest(row):
        rpc.append(row)
        assert row == {'action': 'attest', 'containerId': identifier, 'pin': configuration['cli']}
        return True

    def stop(row):
        rpc.append(row)
        assert row == {'action': 'stop', 'containerId': identifier}
        return True

    node = shutil.which('node')
    assert node is not None, 'Node test prerequisite is missing'
    process = subprocess.Popen([node, '--import', str(ROOT / 'collector/tests/no-network.mjs'),
        '--import', str(ROOT / 'collector/tests/owned-vault-spawn-fixture.mjs'),
        str(ROOT / 'collector/lab/owned-vault-inspection-command.mjs')],
        env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'SYNTHETIC_VAULT_TRACE': str(trace),
            'SYNTHETIC_VAULT_FAULT': fault or ''},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        args = (process, {'configuration': configuration, 'containerId': identifier,
            'egressProxy': 'http://10.1.2.3:8080', 'destination': 'vault-fixture', 'credentials': {
                'BW_CLIENTID': 'SYNTHETIC_CLIENT', 'BW_CLIENTSECRET': 'SYNTHETIC_API', 'BW_PASSWORD': 'SYNTHETIC_UNLOCK'}},
            {'attest': attest, 'stop': stop})
        if fault:
            with pytest.raises(RuntimeError, match='SOURCE_REPLAY_REFUSED'):
                inspection.exchange(*args, timeout=10)
        else:
            selected = inspection.exchange(*args, timeout=10)
            assert set(selected) == {'itemId', 'principalHash', 'uri', 'uri_count',
                'broker_uri_count', 'uriAliasesSha256', 'profile', 'online_ready'}
            assert selected['uri_count'] == 2 and selected['online_ready'] is False
            assert len(selected['uriAliasesSha256']) == 64
            assert not any(secret in json.dumps(selected) for secret in ('SYNTHETIC', 'SYNTHETIC_PASSWORD',
                'SYNTHETIC_SESSION', 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'))
            assert json.loads(trace.read_bytes())[-2:] == ['logout', 'status']
        calls = json.loads(trace.read_bytes())
        assert 'totp' not in calls
        assert calls.count('login') <= 1 and calls.count('logout') <= 1
        if fault in ('hash', 'logout'):
            assert sum(row['action'] == 'stop' for row in rpc) == 1
        assert all(row['action'] in ('attest', 'stop') for row in rpc)
        assert not any(secret in json.dumps(rpc) for secret in ('SYNTHETIC_PASSWORD', 'SYNTHETIC_SESSION',
            'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', 'postData', 'stdout', 'transport'))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)


def test_alias_inspection_requires_a_pinned_binding_before_importing_live_helpers(tmp_path, monkeypatch):
    monkeypatch.setattr(inspection.replay, 'helper', lambda *args: pytest.fail('unpinned live access'))
    with pytest.raises(RuntimeError):
        inspection.inspect(tmp_path, tmp_path / 'lab', {'evidence': {}})


@pytest.mark.parametrize('state,running', [
    ('routes_qualified', True), ('cli_stop_intent', True),
    ('cli_stop_intent', False), ('cli_stopped_owned', False)])
def test_owned_cleanup_reconciles_interruption_without_new_authority(tmp_path, monkeypatch, state, running):
    import copy
    from types import SimpleNamespace
    identifier = 'a' * 64
    durable = {'state': state, 'containers': {'bitwarden-cli': {'id': identifier, 'pid': 123,
        'state': 'started'}}}
    details = {'Id': identifier, 'State': {'Running': running, 'Pid': 123 if running else 0}}
    mutations = []

    def save(value):
        durable.clear()
        durable.update(copy.deepcopy(value))
        mutations.append(value['state'])

    def stop(args):
        assert durable['state'] == 'cli_stop_intent'
        assert args == ['stop', '--time', '5', identifier]
        details['State'] = {'Running': False, 'Pid': 0}
        mutations.append('stop')

    q = SimpleNamespace(load=lambda: copy.deepcopy(durable), save=save, docker=stop,
        owned=lambda *_: copy.deepcopy(details), validate_container=lambda *_: None)
    monkeypatch.setattr(inspection.replay.private, '_publish', lambda *_args, **_kw: mutations.append('backup'))
    assert inspection.stop_owned_cli(q, tmp_path, identifier) is True
    assert durable['state'] == 'cli_stopped_owned'
    assert mutations.count('stop') == int(running)
    assert inspection.stop_owned_cli(q, tmp_path, identifier) is True
    assert mutations.count('stop') == int(running)


def test_stop_failure_preserves_intent_and_can_reconcile_next_call(tmp_path, monkeypatch):
    import copy
    from types import SimpleNamespace
    identifier = 'a' * 64
    durable = {'state': 'routes_qualified', 'containers': {'bitwarden-cli': {'id': identifier, 'pid': 123}}}
    details = {'State': {'Running': True, 'Pid': 123}}
    calls = []

    def save(value):
        durable.clear()
        durable.update(copy.deepcopy(value))

    def stop(args):
        calls.append(args)
        if len(calls) == 1:
            raise RuntimeError('SYNTHETIC_TRANSPORT_LOSS')
        details['State'] = {'Running': False, 'Pid': 0}

    q = SimpleNamespace(load=lambda: copy.deepcopy(durable), save=save, docker=stop,
        owned=lambda *_: copy.deepcopy(details), validate_container=lambda *_: None)
    monkeypatch.setattr(inspection.replay.private, '_publish', lambda *_args, **_kw: None)
    with pytest.raises(RuntimeError, match='SYNTHETIC_TRANSPORT_LOSS'):
        inspection.stop_owned_cli(q, tmp_path, identifier)
    assert durable['state'] == 'cli_stop_intent'
    assert inspection.stop_owned_cli(q, tmp_path, identifier) is True


@pytest.mark.parametrize('change', ['id', 'pid', 'state', 'validation'])
def test_cleanup_refuses_resource_drift_before_mutation(tmp_path, change):
    from types import SimpleNamespace
    identifier = 'a' * 64
    current = {'state': 'cli_stop_intent', 'containers': {'bitwarden-cli': {'id': identifier, 'pid': 123}}}
    details = {'State': {'Running': True, 'Pid': 123}}
    if change == 'id':
        current['containers']['bitwarden-cli']['id'] = 'b' * 64
    if change == 'pid':
        details['State']['Pid'] = 124
    if change == 'state':
        current['state'] = 'unknown'

    def forbidden(*_):
        raise AssertionError('MUTATION_FORBIDDEN')

    def validate(*_):
        if change == 'validation':
            raise RuntimeError('SYNTHETIC_OWNER_DRIFT')

    q = SimpleNamespace(load=lambda: current, owned=lambda *_: details, validate_container=validate,
        save=forbidden, docker=forbidden)
    with pytest.raises(RuntimeError):
        inspection.stop_owned_cli(q, tmp_path, identifier)

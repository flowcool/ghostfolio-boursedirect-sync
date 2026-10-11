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

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
    item = {'id': '11111111-1111-4111-8111-111111111111', 'name': 'boursedirect.fr', 'type': 1,
        'login': {'username': 'SYNTHETIC', 'password': 'SYNTHETIC_PASSWORD',
            'uris': [{'uri': 'https://www.boursedirect.fr/synthetic'}, {'uri': 'https://alias.synthetic.invalid/'}],
            'totp': 'otpauth://totp/Synthetic?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&algorithm=SHA1&digits=6&period=30'}}
    calls = []

    def attest(row):
        assert row == {'action': 'attest', 'containerId': identifier, 'pin': configuration['cli']}
        return True

    def transport(row):
        assert row['args'][:5] == ['exec', '-i', identifier, '/usr/bin/env', '-i']
        args = row['args']
        mode = args[args.index('vault-cli') + 1] if 'vault-cli' in args else 'hash'
        calls.append(mode)
        output = {'hash': ('d' if fault == 'hash' else 'c') * 64 + '  /usr/local/bin/bw\n',
            'version': 'synthetic-1', 'unlock': 'SYNTHETIC_SESSION', 'lookup': json.dumps([item]),
            'status': json.dumps({'status': 'locked' if fault == 'status' else 'unauthenticated'})}.get(mode, '')
        return {'status': 1 if mode == 'logout' and fault == 'logout' else 0, 'stdout': output, 'stderr': ''}

    def stop(row):
        assert row == {'action': 'stop', 'containerId': identifier}
        calls.append('stop')
        return True

    node = shutil.which('node')
    assert node is not None, 'Node test prerequisite is missing'
    process = subprocess.Popen([node, '--import', str(ROOT / 'collector/tests/no-network.mjs'),
        str(ROOT / 'collector/lab/owned-vault-inspection-command.mjs')],
        env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)},
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        args = (process, {'configuration': configuration, 'containerId': identifier,
            'egressProxy': 'http://10.1.2.3:8080', 'credentials': {
                'BW_CLIENTID': 'SYNTHETIC_CLIENT', 'BW_CLIENTSECRET': 'SYNTHETIC_API', 'BW_PASSWORD': 'SYNTHETIC_UNLOCK'}},
            {'attest': attest, 'transport': transport, 'stop': stop})
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
            assert calls[-2:] == ['logout', 'status']
        assert 'totp' not in calls
        assert calls.count('login') <= 1 and calls.count('logout') <= 1
        if fault in ('hash', 'logout'):
            assert calls.count('stop') == 1
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)


def test_alias_inspection_requires_a_pinned_binding_before_importing_live_helpers(tmp_path, monkeypatch):
    monkeypatch.setattr(inspection.replay, 'helper', lambda *args: pytest.fail('unpinned live access'))
    with pytest.raises(RuntimeError):
        inspection.inspect(tmp_path, tmp_path / 'lab', {'evidence': {}})

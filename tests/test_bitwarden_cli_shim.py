"""Execute only the source shell shim and an owned fake CLI; no Docker or sockets."""
import base64
from pathlib import Path
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode,args,secrets,expected', [
    ('version', [], [], ['--version']),
    ('server', ['https://vault.synthetic.invalid'], [], ['config', 'server', 'https://vault.synthetic.invalid']),
    ('login', [], [('BW_CLIENTID', 'SYNTHETIC_CLIENT'), ('BW_CLIENTSECRET', 'SYNTHETIC_API')], ['login', '--apikey']),
    pytest.param('login', [], [('BW_CLIENTID', 'SYNTHETIC_CLIENT'), ('BW_CLIENTSECRET', 'SYNTHETIC_\'"$(false)_é')],
                 ['login', '--apikey'], id='quoted-unicode'),
    ('unlock', [], [('BW_PASSWORD', 'SYNTHETIC_UNLOCK')], ['unlock', '--passwordenv', 'BW_PASSWORD', '--raw']),
    ('sync', [], [('BW_SESSION', 'SYNTHETIC_SESSION')], ['sync']),
    ('item', ['invented-uuid'], [('BW_SESSION', 'SYNTHETIC_SESSION')], ['get', 'item', 'invented-uuid']),
    pytest.param('lookup', ['boursedirect.fr'], [('BW_SESSION', 'SYNTHETIC_SESSION')],
                 ['list', 'items', '--search', 'boursedirect.fr'], id='named-lookup'),
    ('totp', ['invented-uuid'], [('BW_SESSION', 'SYNTHETIC_SESSION')], ['get', 'totp', 'invented-uuid']),
])
def test_shell_invokes_only_fixed_cli_with_command_specific_env(tmp_path, mode, args, secrets, expected):
    fake = tmp_path / 'bw'
    fake.write_text('#!/bin/sh\nprintf "ARG=%s\\n" "$@"\nenv\n')
    fake.chmod(0o700)
    shim = (ROOT / 'collector/bitwarden-cli.sh').read_text().replace('exec /usr/local/bin/bw', 'exec ' + shlex.quote(str(fake)))
    content = b''.join(base64.b64encode(value.encode()) + b'\n' for _, value in secrets)
    result = subprocess.run(['/bin/sh', '-c', shim, 'vault-cli', mode] + args, input=content,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'BITWARDENCLI_APPDATA_DIR': str(tmp_path)},
                            capture_output=True, timeout=5)
    assert result.returncode == 0
    lines = result.stdout.decode().splitlines()
    assert [line[4:] for line in lines if line.startswith('ARG=')] == expected
    observed = dict(line.split('=', 1) for line in lines if not line.startswith('ARG='))
    assert {key: value for key, value in observed.items() if key.startswith('BW_')} == dict(secrets)
    assert all(value not in ' '.join(expected) for _, value in secrets)


@pytest.mark.parametrize('content', [b'', b'!invalid!\n', b'\n',
    pytest.param(base64.b64encode(b'S' * 4099) + b'\n' + base64.b64encode(b'SYNTHETIC_API') + b'\n',
                 id='oversized-valid-frame'),
])
def test_shell_rejects_bad_private_credential_frame_before_cli(tmp_path, content):
    shim = (ROOT / 'collector/bitwarden-cli.sh').read_text().replace('exec /usr/local/bin/bw', 'exec /bin/echo CLI_WAS_CALLED')
    result = subprocess.run(['/bin/sh', '-c', shim, 'vault-cli', 'login'], input=content,
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)}, capture_output=True, timeout=5)
    assert result.returncode != 0
    assert b'CLI_WAS_CALLED' not in result.stdout


def test_shell_named_lookup_cannot_search_another_item(tmp_path):
    shim = (ROOT / 'collector/bitwarden-cli.sh').read_text().replace('exec /usr/local/bin/bw', 'exec /bin/echo CLI_WAS_CALLED')
    result = subprocess.run(['/bin/sh', '-c', shim, 'vault-cli', 'lookup', 'another'],
                            input=base64.b64encode(b'SYNTHETIC_SESSION') + b'\n',
                            env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)}, capture_output=True, timeout=5)
    assert result.returncode != 0
    assert b'CLI_WAS_CALLED' not in result.stdout

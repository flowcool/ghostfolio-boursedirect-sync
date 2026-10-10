"""Offline owner-guard checks with fake Docker and isolated private receipts."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('cli_qualification', ROOT / 'scripts/qualify-bitwarden-cli.py')
qualifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualifier)


def fixture(fault=None):
    facts = qualifier.private.yaml.safe_load((ROOT / 'docs/verification/bitwarden-cli.yaml').read_bytes())['existing_artifact_facts']
    identifier, calls, state = 'b' * 64, [], {'running': False, 'removed': False}
    details = {'Id': identifier, 'Image': facts['image_id'], 'Mounts': [], 'State': {'Running': False, 'Status': 'created'},
               'Config': {'Labels': {}, 'User': '1000:1000', 'Entrypoint': ['/bin/sleep'], 'Cmd': ['180'], 'Env': qualifier.ENV},
               'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True, 'Privileged': False, 'CapAdd': None,
                              'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges'], 'LogConfig': {'Type': 'none', 'Config': {}},
                              'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                              'Ulimits': [{'Name': 'core', 'Hard': 0, 'Soft': 0}], 'Memory': 268435456, 'NanoCpus': 1000000000,
                              'PidsLimit': 64, 'IpcMode': 'private', 'PidMode': '', 'Tmpfs': qualifier.TMPFS,
                              'Binds': None, 'PortBindings': {}, 'PublishAllPorts': False}}
    def docker(args):
        calls.append(args)
        stdout, status, stderr = b'', 0, b''
        if args[0] == 'info':
            stdout = b'synthetic-daemon'
        elif args[0] == 'inspect' and args[1] == facts['image_id']:
            stdout = json.dumps([{'Id': facts['image_id'], 'Config': {'Labels': {}}}]).encode()
        elif args[0] == 'inspect':
            assert args[1] == identifier
            if state['removed']:
                status, stdout, stderr = 1, b'[]', ('Error: No such object: ' + identifier).encode()
            else:
                current = copy.deepcopy(details)
                current['State'] = {'Running': state['running'], 'Status': 'running' if state['running'] else 'created'}
                if fault:
                    fault(current)
                stdout = json.dumps([current]).encode()
        elif args[0] == 'create':
            label = args[args.index('--label') + 1].split('=', 1)[1]
            details['Config']['Labels'] = {'proof.owner': label}
            stdout = identifier.encode()
        elif args[0] == 'start':
            assert args[1] == identifier
            state['running'] = True
        elif args[0] == 'exec':
            assert args[1:5] == [identifier, '/usr/bin/env', '-i', qualifier.ENV[0]]
            if '/usr/bin/sha256sum' in args:
                stdout = (facts['cli_sha256'] + '  ' + facts['cli_path']).encode()
            elif '--version' in args:
                stdout = facts['cli_version'].encode()
            elif '/usr/bin/head' in args:
                stdout = b'{"environmentUrls":{}}'
            else:
                assert args[-2:] == ['config', 'server'] or args[-3:] == ['config', 'server', qualifier.SERVER]
                stdout = qualifier.SERVER.encode()
        elif args[0] == 'stop':
            assert args[-1] == identifier
            state['running'] = False
        elif args[0] == 'rm':
            assert args[1] == identifier
            state['removed'] = True
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, status, stdout, stderr)
    return docker, calls, state


def test_actual_cli_recipe_uses_only_owned_no_secret_offline_commands_and_retains_absence(tmp_path):
    docker, calls, state = fixture()
    output = tmp_path / 'proof'
    qualifier.qualify('synthetic-host', output, docker)
    assert state['removed']
    receipt = qualifier.private._read(output / 'registry.yaml')
    assert receipt['state'] == 'absence_verified' and receipt['id'] == 'b' * 64
    result = qualifier.private._read(output / 'result.yaml')
    assert result['online_ready'] is False and result['authentication_performed'] is False
    assert result['server_before'] == result['server_after'] == qualifier.SERVER
    executed = [call for call in calls if call[0] == 'exec']
    assert len(executed) == 6
    assert all(not {'login', 'unlock', 'sync', 'item', 'totp', 'serve'} & set(call) for call in calls)
    count = len(calls)
    with pytest.raises(RuntimeError):
        qualifier.qualify('synthetic-host', output, docker)
    assert len(calls) == count


@pytest.mark.parametrize('fault', [
    lambda d: d['Config'].update(User='0:0'),
    lambda d: d['HostConfig'].update(NetworkMode='bridge'),
    lambda d: d['Config']['Env'].append('BW_SESSION=SYNTHETIC'),
    lambda d: d.update(Image='sha256:' + 'd' * 64),
    lambda d: d['Config'].update(Labels={}),
    lambda d: d['HostConfig'].update(Privileged=True),
])
def test_unqualified_create_never_grants_start_or_cleanup(tmp_path, fault):
    docker, calls, state = fixture(fault)
    with pytest.raises(RuntimeError):
        qualifier.qualify('synthetic-host', tmp_path / 'proof', docker)
    assert not any(call[0] in ('start', 'stop', 'rm') for call in calls)
    assert not state['removed']
    assert qualifier.private._read(tmp_path / 'proof/registry.yaml')['state'] == 'intent'


def test_failed_receipt_publication_cannot_use_in_memory_id_for_cleanup(tmp_path, monkeypatch):
    docker, calls, state = fixture()
    original = qualifier.private._publish
    def publish(path, row, exclusive=False):
        if row.get('state') == 'receipted':
            raise RuntimeError('SYNTHETIC_FSYNC_FAILURE')
        return original(path, row, exclusive)
    monkeypatch.setattr(qualifier.private, '_publish', publish)
    with pytest.raises(RuntimeError):
        qualifier.qualify('synthetic-host', tmp_path / 'proof', docker)
    assert not any(call[0] in ('start', 'stop', 'rm') for call in calls)
    assert qualifier.private._read(tmp_path / 'proof/registry.yaml')['id'] is None


def test_metadata_transport_refuses_ssh_option_injection():
    with pytest.raises(RuntimeError):
        qualifier.transport('-oProxyCommand=unsafe')

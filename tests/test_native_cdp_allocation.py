"""Owned filesystem fixtures and fake daemon observations; never Docker or Beads."""

import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import uuid

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def registry(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('native_allocation_fixture', ROOT / 'scripts/native_cdp_allocation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('HOME', str(tmp_path))
    profile = b'{"defaultAction":"invented-test-only","syscalls":[]}'
    monkeypatch.setattr(module, 'PROFILE_SHA', hashlib.sha256(profile).hexdigest())
    module.initialize_registry('invented-daemon')
    return module, profile


def allocation(registry):
    module, profile = registry
    handle = module.acquire_registry()
    identity = str(uuid.uuid4())
    spec = {'image': module.IMAGE, 'profile_sha256': module.PROFILE_SHA,
            'sources': {'invented.mjs': 'a' * 64}, 'entrypoint': '/usr/bin/node',
            'arguments': ['/home/fixture/proof/lab/native-runtime.mjs', 'permitted', identity]}
    owner = module.begin_allocation(handle, 'invented-daemon', identity, spec)
    identifier = 'b' * 64
    details = {'Id': identifier, 'Image': module.IMAGE, 'Mounts': [],
               'Config': {'Labels': {'proof.owner': owner, 'proof.allocation': identity},
                          'User': '1000:1000', 'Entrypoint': [spec['entrypoint']], 'Cmd': spec['arguments'],
                          'Env': ['HOME=/home/fixture', 'PATH=/usr/bin:/bin']},
               'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'CapAdd': None,
                              'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0},
                              'PidMode': '', 'IpcMode': 'private', 'Memory': 805306368,
                              'NanoCpus': 1000000000, 'PidsLimit': 256, 'ShmSize': 134217728,
                              'SecurityOpt': ['seccomp=' + profile.decode()]},
               'State': {'Status': 'created', 'Running': False}}
    return module, profile, handle, identity, identifier, details


def receipt(f):
    module, profile, handle, identity, identifier, details = f
    module.record_receipt(handle, 'invented-daemon', identity, identifier, details, profile)


def test_full_id_receipt_is_durable_before_start_and_exact_cleanup(registry):
    f = allocation(registry)
    module, profile, handle, identity, identifier, details = f
    with pytest.raises(RuntimeError, match='ALLOCATION_RECEIPT_REQUIRED'):
        module.before_start(handle, 'invented-daemon', identity, lambda _: details, profile)
    receipt(f)
    saved = module._read(module._root() / 'registry.yaml')
    assert saved['allocations'][identity]['container'] == identifier
    assert saved['allocations'][identity]['state'] == 'receipted'
    calls = []
    assert module.before_start(handle, 'invented-daemon', identity, lambda value: calls.append(('inspect', value)) or details, profile) == identifier
    result = module.cleanup_allocation(handle, 'invented-daemon', identity, lambda value: details,
                                       lambda value: calls.append(('remove', value)) or True,
                                       lambda value: calls.append(('absent', value)) or True, profile)
    assert calls == [('inspect', identifier), ('remove', identifier), ('absent', identifier)]
    assert result['cleanup_verified'] is True and result['online_ready'] is False
    assert module._read(module._root() / 'registry.yaml')['allocations'][identity]['state'] == 'absence_verified'
    module.release_registry(handle)
    assert (module._root() / 'registry.yaml').stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('window', ['intent-before-create', 'create-before-receipt', 'receipt-before-start', 'dispatch'])
def test_kill_windows_retain_unresolved_allocation(registry, window):
    f = allocation(registry)
    module, profile, handle, identity, identifier, details = f
    if window in ('receipt-before-start', 'dispatch'):
        receipt(f)
    if window == 'dispatch':
        module.before_start(handle, 'invented-daemon', identity, lambda _: details, profile)
    module.release_registry(handle)  # Simulate cooperative exit; abrupt exit retains lock too.
    restarted = module.acquire_registry()
    spec = copy.deepcopy(details['Config']['Cmd'])
    new_id = str(uuid.uuid4())
    spec[2] = new_id
    new = {'image': module.IMAGE, 'profile_sha256': module.PROFILE_SHA,
           'sources': {'invented.mjs': 'a' * 64}, 'entrypoint': '/usr/bin/node', 'arguments': spec}
    with pytest.raises(RuntimeError, match='ALLOCATION_UNRESOLVED'):
        module.begin_allocation(restarted, 'invented-daemon', new_id, new)
    if window in ('intent-before-create', 'create-before-receipt'):
        with pytest.raises(RuntimeError, match='ALLOCATION_RECEIPT_REQUIRED'):
            module.cleanup_allocation(restarted, 'invented-daemon', identity, lambda _: details,
                                      lambda _: pytest.fail('unreceipted removal'), lambda _: True, profile)
    module.release_registry(restarted)


@pytest.mark.parametrize('change', [
    lambda d: d.update(Id='c' * 64),
    lambda d: d.update(Image='sha256:' + 'c' * 64),
    lambda d: d['Config']['Labels'].update({'proof.owner': 'foreign-owner'}),
    lambda d: d['Config']['Labels'].update({'proof.allocation': str(uuid.uuid4())}),
    lambda d: d['Config'].update(User='0:0'),
    lambda d: d['Config']['Env'].append('BD_PASSWORD=invented-forbidden'),
    lambda d: d['HostConfig'].update(NetworkMode='host'),
    lambda d: d['HostConfig'].update(Privileged=True),
    lambda d: d.update(Mounts=[{'Source': '/invented-shared-path'}]),
    lambda d: d['HostConfig'].update(CapAdd=['SYS_ADMIN']),
    lambda d: d['HostConfig'].update(RestartPolicy={'Name': 'always', 'MaximumRetryCount': 0}),
    lambda d: d['Config']['Cmd'].append('--no-sandbox'),
])
def test_receipt_refuses_foreign_or_unsafe_configuration_before_start(registry, change):
    f = allocation(registry)
    module, profile, handle, identity, identifier, details = f
    change(details)
    with pytest.raises(RuntimeError, match='ALLOCATION_OWNER_MISMATCH'):
        module.record_receipt(handle, 'invented-daemon', identity, identifier, details, profile)
    with pytest.raises(RuntimeError, match='ALLOCATION_RECEIPT_REQUIRED'):
        module.before_start(handle, 'invented-daemon', identity, lambda _: details, profile)
    module.release_registry(handle)


@pytest.mark.parametrize('failure', ['inspect-error', 'foreign-owner', 'daemon-change', 'remove-error', 'absence-error'])
def test_cleanup_never_infers_authority_from_failed_or_contradictory_observations(registry, failure):
    f = allocation(registry)
    module, profile, handle, identity, identifier, details = f
    receipt(f)
    mutations = []
    def inspect(value):
        assert value == identifier
        if failure == 'inspect-error':
            raise RuntimeError('invented daemon unavailable')
        if failure == 'foreign-owner':
            details['Config']['Labels']['proof.owner'] = 'foreign-owner'
        return details
    def remove(value):
        mutations.append(value)
        return failure != 'remove-error'
    with pytest.raises(RuntimeError):
        module.cleanup_allocation(handle, 'changed-daemon' if failure == 'daemon-change' else 'invented-daemon',
                                  identity, inspect, remove, lambda _: failure != 'absence-error', profile)
    assert mutations == ([] if failure in ('inspect-error', 'foreign-owner', 'daemon-change') else [identifier])
    assert module._read(module._root() / 'registry.yaml')['allocations'][identity]['state'] == 'receipted'
    module.release_registry(handle)


@pytest.mark.parametrize('phase', ['intent', 'receipt', 'start', 'terminal-absence'])
def test_fsync_uncertainty_poisoned_handle_retains_lock_and_blocks_new_run(registry, monkeypatch, phase):
    f = allocation(registry)
    module, profile, handle, identity, identifier, details = f
    if phase in ('start', 'terminal-absence'):
        receipt(f)
    mutations = []
    def fail(_):
        raise OSError('invented fsync failure')
    monkeypatch.setattr(module.os, 'fsync', fail)
    if phase == 'intent':
        # Every failed publication poisons the lock, including another begin.
        value, state = module._state(handle, 'invented-daemon')
        operation = lambda: module._save(value, state)
    elif phase == 'receipt':
        operation = lambda: receipt(f)
    elif phase == 'start':
        operation = lambda: module.before_start(handle, 'invented-daemon', identity, lambda _: details, profile)
    else:
        operation = lambda: module.cleanup_allocation(handle, 'invented-daemon', identity, lambda _: details,
                                                      lambda value: mutations.append(value) or True, lambda _: True, profile)
    with pytest.raises(OSError):
        operation()
    module.release_registry(handle)
    assert (module._root() / 'lock').is_dir()
    with pytest.raises(RuntimeError, match='ALLOCATION_LOCKED'):
        module.acquire_registry()
    assert mutations == ([identifier] if phase == 'terminal-absence' else [])


def test_fresh_competing_process_uses_fixed_registry_across_output_roots(registry):
    f = allocation(registry)
    module, _, handle, *_ = f
    script = ROOT / 'scripts/native_cdp_allocation.py'
    code = 'import runpy; m=runpy.run_path(' + repr(str(script)) + ');\ntry: m["acquire_registry"]()\nexcept RuntimeError as e: print(str(e))'
    result = subprocess.run([sys.executable, '-c', code], env={'HOME': str(Path.home()), 'PATH': '/usr/bin:/bin'},
                            cwd=ROOT / 'tmp', capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and result.stdout.strip() == 'ALLOCATION_LOCKED'
    module.release_registry(handle)


def test_registry_loss_alias_or_schema_conflict_retains_manual_recovery_lock(registry):
    module, _ = registry
    filename = module._root() / 'registry.yaml'
    filename.write_text('schema_version: 1\nschema_version: 1\n')
    with pytest.raises(RuntimeError, match='ALLOCATION_SCHEMA_INVALID'):
        module.acquire_registry()
    assert (module._root() / 'lock').is_dir()
    with pytest.raises(RuntimeError, match='ALLOCATION_ALREADY_INITIALIZED'):
        module.initialize_registry('invented-daemon')


def test_copied_handle_or_released_handle_cannot_mutate_new_owner(registry):
    module, _ = registry
    handle = module.acquire_registry()
    with pytest.raises(RuntimeError, match='ALLOCATION_HANDLE_CLOSED'):
        module.release_registry(str(uuid.uuid4()))
    module.release_registry(handle)
    new = module.acquire_registry()
    module.release_registry(handle)
    assert (module._root() / 'lock').exists()
    with pytest.raises(RuntimeError, match='ALLOCATION_HANDLE_CLOSED'):
        module._state(handle, 'invented-daemon')
    module.release_registry(new)

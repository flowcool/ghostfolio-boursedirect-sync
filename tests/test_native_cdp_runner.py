"""Runner wiring with fake Docker and owned temp HOME; no live runtime access."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('native_runner_fixture', ROOT / 'scripts/run-native-cdp.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('HOME', str(tmp_path))
    def forbidden(*args, **kwargs):
        raise AssertionError('TEST_DOCKER_OR_CHILD_FORBIDDEN')
    monkeypatch.setattr(module, 'docker', forbidden)
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    return module


def result(code=0, stdout=b'', stderr=b''):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


def test_archive_preserves_transitive_imports_and_pins_final_sources(runner):
    raw, hashes = runner.archive_sources()
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        names = set(archive.getnames())
        for relative in runner.SOURCES:
            assert 'proof/' + relative in names
            data = archive.extractfile('proof/' + relative).read()
            assert hashes['proof/' + relative] == hashlib.sha256(data).hexdigest()
            assert archive.getmember('proof/' + relative).mode == 0o400
    assert 'proof/internal/source-policy.mjs' in names
    assert 'proof/lab/native-restart.mjs' in names
    assert 'proof/node_modules/yaml/package.json' in names
    assert 'runner' in hashes and 'allocation' in hashes
    assert len(runner.modes()) == len(set(runner.modes()))


@pytest.mark.parametrize('stderr', [b'daemon unavailable', b'permission denied', b'Error: No such object: wrong-id', b''])
def test_absence_never_uses_generic_failed_inspection(runner, monkeypatch, stderr):
    monkeypatch.setattr(runner, 'docker', lambda _: result(1, stderr=stderr))
    assert runner.absent('a' * 64) is False


def test_absence_requires_the_exact_daemon_resource_id(runner, monkeypatch):
    identifier = 'a' * 64
    calls = []
    monkeypatch.setattr(runner, 'docker', lambda args: calls.append(args) or result(1, b'[]\n', ('Error: No such object: ' + identifier).encode()))
    assert runner.absent(identifier) is True
    assert calls == [['inspect', identifier]]


def test_unreceipted_create_error_retains_intent_and_never_removes_by_name(runner, monkeypatch, tmp_path):
    profile = tmp_path / 'profile.json'
    profile.write_bytes(b'{"invented":true}')
    monkeypatch.setattr(runner.allocation, 'PROFILE_SHA', hashlib.sha256(profile.read_bytes()).hexdigest())
    runner.allocation.initialize_registry('invented-daemon')
    monkeypatch.setattr(runner, 'daemon_id', lambda: 'invented-daemon')
    calls = []
    def docker(args, **kwargs):
        calls.append(args)
        assert args[0] == 'create'
        return result(0, b'invalid-create-id\n')
    monkeypatch.setattr(runner, 'docker', docker)
    with pytest.raises(RuntimeError, match='NATIVE_QUALIFICATION_INCOMPLETE'):
        runner.run('permitted', profile, tmp_path, b'invented archive', {'invented': 'a' * 64})
    assert len(calls) == 1
    receipt = json.loads((tmp_path / 'permitted-receipt.yaml').read_text())
    assert receipt['cleanup_verified'] is False and 'container' not in receipt
    rows = runner.allocation._read(runner.allocation._root() / 'registry.yaml')['allocations']
    assert len(rows) == 1 and next(iter(rows.values()))['state'] == 'intent'


def test_inspect_failure_after_create_cannot_grant_cleanup(runner, monkeypatch, tmp_path):
    profile = tmp_path / 'profile.json'
    profile.write_bytes(b'{"invented":true}')
    monkeypatch.setattr(runner.allocation, 'PROFILE_SHA', hashlib.sha256(profile.read_bytes()).hexdigest())
    runner.allocation.initialize_registry('invented-daemon')
    monkeypatch.setattr(runner, 'daemon_id', lambda: 'invented-daemon')
    calls = []
    def docker(args, **kwargs):
        calls.append(args)
        if args[0] == 'create':
            return result(0, ('a' * 64).encode())
        assert args == ['inspect', 'a' * 64]
        return result(1, stderr=b'invented daemon unavailable')
    monkeypatch.setattr(runner, 'docker', docker)
    with pytest.raises(RuntimeError, match='NATIVE_QUALIFICATION_INCOMPLETE'):
        runner.run('permitted', profile, tmp_path, b'invented archive', {'invented': 'a' * 64})
    assert [call[0] for call in calls] == ['create', 'inspect']
    assert json.loads((tmp_path / 'permitted-receipt.yaml').read_text())['cleanup_verified'] is False


def test_principal_archive_failure_stops_owned_container_but_refuses_removal(runner, monkeypatch, tmp_path):
    identifier = 'a' * 64
    calls = []
    monkeypatch.setattr(runner, 'inspect', lambda value: {'State': {'Running': False}})
    def docker(args, **kwargs):
        calls.append(args)
        return result(1) if args[0] == 'cp' else result(0)
    monkeypatch.setattr(runner, 'docker', docker)
    assert runner.remove(identifier, tmp_path, 'permitted', True, {}) is False
    assert [call[0] for call in calls] == ['stop', 'cp']
    assert all('rm' not in call for call in calls)


def test_private_output_publication_never_replaces_existing_bytes(runner, tmp_path):
    path = tmp_path / 'retained.bytes'
    path.write_bytes(b'invented original evidence')
    with pytest.raises(RuntimeError, match='NATIVE_OUTPUT_EXISTS'):
        runner.publish(path, b'replacement')
    assert path.read_bytes() == b'invented original evidence'

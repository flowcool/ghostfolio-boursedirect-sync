"""Proof helper boundaries; isolated filesystem only, all live calls forbidden."""

import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('wrong_home', [True, False])
def test_direct_worker_refuses_foreign_home_or_supervisor(monkeypatch, tmp_path, wrong_home):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    spec = importlib.util.spec_from_file_location('allocation_proof_fixture', root / 'scripts/prove-native-allocation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    output = tmp_path / 'tmp/scenario'
    output.mkdir(parents=True)
    home = output / 'home'
    home.mkdir(mode=0o700)
    monkeypatch.setenv('HOME', str(tmp_path if wrong_home else home))
    monkeypatch.setenv('NATIVE_PROOF_SUPERVISOR', str(module.os.getppid() if wrong_home else 0))
    profile = tmp_path / 'profile.json'
    profile.write_bytes(b'{}')
    monkeypatch.setattr(module.allocation, 'PROFILE_SHA', hashlib.sha256(profile.read_bytes()).hexdigest())
    def forbidden(*args, **kwargs):
        raise AssertionError('TEST_LIVE_OR_REGISTRY_ACCESS_FORBIDDEN')
    monkeypatch.setattr(module, 'worker', forbidden)
    monkeypatch.setattr(module, 'runner_module', forbidden)
    monkeypatch.setattr(module.allocation, 'acquire_registry', forbidden)
    monkeypatch.setattr(sys, 'argv', ['proof', '--worker', 'before-create', '--profile', str(profile), '--output', str(output)])
    with pytest.raises(RuntimeError, match='ALLOCATION_PROOF_SUPERVISOR_INVALID'):
        module.main()


def test_supervisor_waits_for_worker_exit_before_reading_checkpoint(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(root / 'scripts'))
    spec = importlib.util.spec_from_file_location('allocation_checkpoint_fixture', root / 'scripts/prove-native-allocation.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / 'proof'
    checkpoint = output / 'checkpoint.json'
    calls = []
    child = SimpleNamespace(returncode=None)
    def poll():
        calls.append('poll')
        if len(calls) == 1:
            checkpoint.write_text('')
            return None
        checkpoint.write_text('{"stage":"before-create","container":null}')
        child.returncode = -module.signal.SIGKILL
        return child.returncode
    child.poll = poll
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args, **kwargs: child)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(module, 'runner_module', lambda: None)
    def retained_state(*args):
        assert child.returncode == -module.signal.SIGKILL
        raise RuntimeError('CHECKPOINT_READ_AFTER_DURABLE_WORKER_EXIT')
    monkeypatch.setattr(module.allocation, '_read', retained_state)
    with pytest.raises(RuntimeError, match='CHECKPOINT_READ_AFTER_DURABLE_WORKER_EXIT'):
        module.prove('before-create', tmp_path / 'unused-profile', output)

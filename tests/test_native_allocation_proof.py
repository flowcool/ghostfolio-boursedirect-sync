"""Proof helper boundaries; isolated filesystem only, all live calls forbidden."""

import hashlib
import importlib.util
from pathlib import Path
import sys

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

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner(monkeypatch):
    module = load('run-cdp-first-request')
    def forbidden(*args, **kwargs):
        raise AssertionError('No real Docker or child process in unit tests')
    monkeypatch.setattr(module, 'docker', forbidden)
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    return module


def result(code=0, stdout=b'', stderr=b''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


@pytest.mark.parametrize('inspection', ['empty', 'timeout', 'nonzero'])
def test_inspection_failure_still_removes_exact_created_id(runner, monkeypatch, inspection):
    identifier = 'a' * 64
    calls = []
    def docker(args, **kwargs):
        calls.append(args)
        if args[0] == 'inspect':
            if inspection == 'nonzero':
                return result(1, stdout=json.dumps([{'Id': identifier, 'Config': {'Labels': {'proof.owner': 'owned-name'}}}]).encode())
            if inspection == 'timeout':
                raise subprocess.TimeoutExpired([], 20)
            if inspection == 'empty':
                return result()
            return result(stdout=json.dumps([{'Id': identifier, 'Config': {'Labels': {'proof.owner': 'foreign'}}}]).encode())
        return result()
    monkeypatch.setattr(runner, 'docker', docker)
    receipt = {}
    runner.cleanup_owned(identifier, 'owned-name', receipt)
    assert ['rm', '-f', identifier] in calls
    assert receipt['cleanup_verified'] is False
    assert receipt['owner_verified'] is False


def test_explicit_foreign_owner_is_never_removed(runner, monkeypatch):
    identifier = 'd' * 64
    calls = []
    def docker(args, **kwargs):
        calls.append(args)
        if args[0] == 'inspect':
            return result(stdout=json.dumps([{'Id': identifier, 'Config': {'Labels': {'proof.owner': 'foreign'}}}]).encode())
        return result()
    monkeypatch.setattr(runner, 'docker', docker)
    receipt = {}
    runner.cleanup_owned(identifier, 'owned-name', receipt)
    assert not any(args[0] == 'rm' for args in calls)
    assert receipt['cleanup_verified'] is False
    assert 'FIXTURE_OWNER_MISMATCH' in receipt['cleanup_errors']


@pytest.mark.parametrize('failure', ['remove', 'absence'])
def test_cleanup_errors_cannot_report_success(runner, monkeypatch, failure):
    identifier = 'b' * 64
    def docker(args, **kwargs):
        if args[0] == 'inspect':
            return result(stdout=json.dumps([{'Id': identifier, 'Config': {'Labels': {'proof.owner': 'owned-name'}}}]).encode())
        if args[0] == ('rm' if failure == 'remove' else 'ps'):
            return result(1)
        return result()
    monkeypatch.setattr(runner, 'docker', docker)
    receipt = {}
    runner.cleanup_owned(identifier, 'owned-name', receipt)
    assert receipt['cleanup_verified'] is False
    assert receipt['cleanup_errors']


def test_invalid_id_never_becomes_removal_target(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(runner, 'docker', lambda args: calls.append(args) or result())
    receipt = {}
    runner.cleanup_owned('foreign-name', 'owned-name', receipt)
    assert not any(args[0] == 'rm' for args in calls)
    assert receipt['cleanup_verified'] is False


def test_original_execution_error_and_receipt_survive_cleanup_failure(runner, monkeypatch, tmp_path):
    identifier = 'c' * 64
    original = RuntimeError('FIXTURE_ORIGINAL_FAILURE')
    inspections = 0
    def docker(args, **kwargs):
        nonlocal inspections
        if args[0] == 'create':
            return result(stdout=identifier.encode())
        if args[0] == 'inspect':
            inspections += 1
            if inspections == 1:
                raise original
        raise subprocess.TimeoutExpired([], 20)
    monkeypatch.setattr(runner, 'docker', docker)
    with pytest.raises(RuntimeError) as caught:
        runner.run('permitted', tmp_path / 'profile', tmp_path, b'', {})
    assert caught.value is original
    receipt = json.loads((tmp_path / 'permitted-receipt.json').read_text())
    assert receipt['container'] == identifier
    assert receipt['execution_error'] == 'FIXTURE_EXECUTION_FAILED'
    assert receipt['cleanup_verified'] is False
    assert receipt['cleanup_errors']


def test_security_checks_are_not_assert_statements(runner):
    import ast
    tree = ast.parse(Path(runner.__file__).read_text())
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    with pytest.raises(RuntimeError, match='^PIN_REJECTED$'):
        runner.require(False, 'PIN_REJECTED')


def test_invalid_create_output_preserves_uncertainty_without_untrusted_removal(runner, monkeypatch, tmp_path):
    calls = []
    def docker(args, **kwargs):
        calls.append(args)
        return result(stdout=b'foreign-name' if args[0] == 'create' else b'')
    monkeypatch.setattr(runner, 'docker', docker)
    with pytest.raises(RuntimeError, match='^FIXTURE_ID_INVALID$'):
        runner.run('permitted', tmp_path / 'profile', tmp_path, b'', {})
    receipt = json.loads((tmp_path / 'permitted-receipt.json').read_text())
    assert receipt['execution_error'] == 'FIXTURE_EXECUTION_FAILED'
    assert receipt['cleanup_verified'] is False
    assert receipt['cleanup_errors'] == ['FIXTURE_ID_INVALID']
    assert 'container' not in receipt
    assert not any(args[0] in ['inspect', 'rm', 'start', 'cp'] for args in calls)


@pytest.fixture
def proof(monkeypatch):
    module = load('consolidate-cdp-proof')
    monkeypatch.setattr(module, 'current_pins', lambda root: {'first-request.mjs': 'fixed', 'capture-document.mjs': 'current'})
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: result())
    return module


def receipts(proof, directory, capture='current'):
    import hashlib
    directory.mkdir()
    runner_hash = hashlib.sha256(Path(proof.runner.__file__).read_bytes()).hexdigest()
    for index, mode in enumerate(proof.runner.SCENARIOS):
        r = {'mode': mode, 'image': proof.runner.IMAGE, 'profile_sha256': proof.runner.PROFILE_SHA,
             'runner_sha256': runner_hash, 'cleanup_verified': True, 'browser_proven': False,
             'owner_verified': True, 'remove_returncode': 0, 'cleanup_errors': [],
             'source_sha256': {'first-request.mjs': 'fixed', 'capture-document.mjs': capture},
             'container': format(index + 1, '064x'),
             'evidence': {'mode': mode, 'passed': True, 'owned_browser_exit': True,
                          'browser_proven': False, 'node': 'v20.19.2'}}
        (directory / (mode + '-receipt.json')).write_text(json.dumps(r))


def mutate(directory, mode, update):
    path = directory / (mode + '-receipt.json')
    value = json.loads(path.read_text())
    update(value)
    path.write_text(json.dumps(value))


def test_complete_current_receipts_consolidate_offline(proof, tmp_path):
    receipts(proof, tmp_path / 'matrix')
    summary = proof.consolidate(tmp_path / 'matrix')
    assert summary['modes'] == 28 and summary['receipts'] == 28
    assert summary['live_absence_verified'] is False
    assert summary['browser_proven'] is False


@pytest.mark.parametrize('case', ['missing', 'cleanup', 'verdict', 'source', 'runner', 'runtime', 'container', 'owner', 'remove'])
def test_incomplete_or_incompatible_receipts_refuse(proof, tmp_path, case):
    directory = tmp_path / 'matrix'
    receipts(proof, directory)
    if case == 'missing':
        (directory / 'capture-receipt.json').unlink()
    else:
        def update(r):
            if case == 'cleanup': r['cleanup_verified'] = False
            if case == 'verdict': r['evidence']['passed'] = False
            if case == 'source': r['source_sha256']['first-request.mjs'] = 'stale'
            if case == 'runner': r['runner_sha256'] = 'stale'
            if case == 'runtime': r['image'] = 'other'
            if case == 'container': r['container'] = 'foreign-name'
            if case == 'owner': r['owner_verified'] = False
            if case == 'remove': r['remove_returncode'] = 1
        mutate(directory, 'capture', update)
    with pytest.raises(RuntimeError):
        proof.consolidate(directory)


def replacement(proof, tmp_path):
    directory = tmp_path / 'replacement'
    receipts(proof, directory)
    for path in directory.glob('*-receipt.json'):
        if path.name != 'capture-receipt.json': path.unlink()
    mutate(directory, 'capture', lambda r: r.update(container='f' * 64))
    return directory


def test_explicit_capture_replacement_requires_identical_common_pins(proof, tmp_path):
    matrix = tmp_path / 'matrix'
    receipts(proof, matrix, capture='older-capture')
    with pytest.raises(RuntimeError, match='PROOF_CURRENT_PIN_MISMATCH'):
        proof.consolidate(matrix)
    extra = replacement(proof, tmp_path)
    summary = proof.consolidate(matrix, extra)
    assert summary['capture_replaced'] is True and summary['receipts'] == 29
    mutate(extra, 'capture', lambda r: r['source_sha256'].update({'first-request.mjs': 'changed'}))
    with pytest.raises(RuntimeError, match='PROOF_REPLACEMENT_COMMON_PIN_MISMATCH'):
        proof.consolidate(matrix, extra)


@pytest.mark.parametrize('with_replacement', [False, True])
def test_container_identity_cannot_be_reused_across_any_receipts(proof, tmp_path, with_replacement):
    matrix = tmp_path / 'matrix'
    receipts(proof, matrix)
    if with_replacement:
        extra = replacement(proof, tmp_path)
        original = json.loads((matrix / 'capture-receipt.json').read_text())
        mutate(extra, 'capture', lambda r: r.update(container=original['container']))
    else:
        extra = None
        original = json.loads((matrix / 'permitted-receipt.json').read_text())
        mutate(matrix, 'capture', lambda r: r.update(container=original['container']))
    with pytest.raises(RuntimeError, match='^PROOF_CONTAINER_REUSED$'):
        proof.consolidate(matrix, extra)


def test_live_absence_requires_definitive_daemon_response(proof, monkeypatch, tmp_path):
    receipts(proof, tmp_path / 'matrix')
    monkeypatch.setattr(proof.runner, 'docker', lambda args: result(1, stderr=b'daemon unavailable'))
    with pytest.raises(RuntimeError, match='PROOF_RESOURCE_ABSENCE_UNVERIFIED'):
        proof.consolidate(tmp_path / 'matrix', verify_absent=True)
    monkeypatch.setattr(proof.runner, 'docker', lambda args: result(1, stderr=b'Error: No such object'))
    assert proof.consolidate(tmp_path / 'matrix', verify_absent=True)['live_absence_verified'] is True


def test_forged_passed_flag_is_rechecked_by_pure_evaluator(proof, monkeypatch, tmp_path):
    receipts(proof, tmp_path / 'matrix')
    monkeypatch.setattr(proof.subprocess, 'run', lambda *args, **kwargs: result(1))
    with pytest.raises(RuntimeError, match='PROOF_OBSERVATIONS_REJECTED'):
        proof.consolidate(tmp_path / 'matrix')


def test_receipt_symlink_is_refused(proof, tmp_path):
    directory = tmp_path / 'matrix'
    receipts(proof, directory)
    path = directory / 'capture-receipt.json'
    moved = tmp_path / 'saved-capture.json'
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(RuntimeError, match='PROOF_RECEIPT_REJECTED'):
        proof.consolidate(directory)

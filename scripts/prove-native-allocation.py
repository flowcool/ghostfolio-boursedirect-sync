#!/usr/bin/env python3
"""Opt-in SIGKILL proof of the actual native runner in newly owned lab HOMEs.

Only the pinned agentvm-local fixture is permitted. No production or shared
registry is used. Unreceipted resources are recovered from the supervisor's
fsynced full create-ID observation, never names, labels or resource discovery.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import native_cdp_allocation as allocation


ROOT = Path(__file__).resolve().parents[1]
STAGES = ('before-create', 'create-before-receipt', 'receipt-before-start', 'dispatch')


def runner_module():
    spec = importlib.util.spec_from_file_location('owned_native_runner', ROOT / 'scripts/run-native-cdp.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_for(condition, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise RuntimeError('ALLOCATION_PROOF_TIMEOUT')


def worker(stage, profile, output):
    runner = runner_module()
    original = runner.docker

    def checkpoint(identifier=None):
        runner.publish(output / 'checkpoint.json', json.dumps({'stage': stage, 'container': identifier}).encode())
        os.kill(os.getpid(), signal.SIGKILL)

    def docker(args, **kwargs):
        if args[0] == 'create' and stage == 'before-create':
            checkpoint()
        result = original(args, **kwargs)
        if args[0] == 'start' and stage == 'dispatch':
            allocation.require(result.returncode == 0, 'ALLOCATION_PROOF_DISPATCH_FAILED')
            runner.validate_evidence(result.stdout)
            checkpoint(args[-1])
        if args[0] == 'create' and stage == 'create-before-receipt':
            allocation.require(result.returncode == 0, 'ALLOCATION_PROOF_CREATE_FAILED')
            checkpoint(result.stdout.decode().strip())
        return result

    runner.docker = docker
    if stage == 'receipt-before-start':
        def before_start(*args):
            state = allocation._validate(allocation._read(allocation._root() / 'registry.yaml'))
            checkpoint(next(iter(state['allocations'].values()))['container'])
        allocation.before_start = before_start
    archive, hashes = runner.archive_sources()
    runner.run('permitted', profile, output, archive, hashes)


def prove(stage, profile, output):
    runner = runner_module()
    allocation._private_directory(output, create=True)
    home = output / 'home'
    allocation._private_directory(home, create=True)
    environment = dict(os.environ, HOME=str(home), NATIVE_PROOF_SUPERVISOR=str(os.getpid()))
    init = subprocess.run([sys.executable, '-c',
        'import native_cdp_allocation as a; import importlib.util; '
        's=importlib.util.spec_from_file_location("r", "scripts/run-native-cdp.py"); '
        'r=importlib.util.module_from_spec(s); s.loader.exec_module(r); '
        'a.initialize_registry(r.daemon_id())'], cwd=ROOT,
        env=dict(environment, PYTHONPATH=str(ROOT / 'scripts')), capture_output=True)
    allocation.require(init.returncode == 0, 'ALLOCATION_PROOF_INITIALIZATION_FAILED')
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--worker', stage,
        '--profile', str(profile), '--output', str(output)], env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checkpoint = output / 'checkpoint.json'
    try:
        wait_for(lambda: child.poll() is not None)
        allocation.require(child.returncode == -signal.SIGKILL, 'ALLOCATION_PROOF_KILL_UNVERIFIED')
        allocation.require(checkpoint.exists(), 'ALLOCATION_PROOF_CHECKPOINT_MISSING')
        observed = json.loads(checkpoint.read_text())
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)

    registry = home / '.local/state/ghostfolio-boursedirect-sync/synthetic-cdp/allocations'
    state = allocation._validate(allocation._read(registry / 'registry.yaml'))
    identity, row = next(iter(state['allocations'].items()))
    expected = {'before-create': 'intent', 'create-before-receipt': 'intent',
                'receipt-before-start': 'receipted', 'dispatch': 'started'}[stage]
    allocation.require(row['state'] == expected and (registry / 'lock').is_dir(), 'ALLOCATION_PROOF_STATE_INVALID')
    contender = subprocess.run([sys.executable, '-c',
        'import native_cdp_allocation as a; '
        'a.acquire_registry()'], env=dict(environment, PYTHONPATH=str(ROOT / 'scripts')),
        cwd=output, capture_output=True)
    allocation.require(contender.returncode != 0 and b'ALLOCATION_LOCKED' in contender.stderr,
                       'ALLOCATION_PROOF_EXCLUSION_FAILED')
    proof = {'stage': stage, 'allocation': identity, 'killed_exit': -signal.SIGKILL,
             'retained_state': expected, 'alternate_output_refused': True,
             'image': allocation.IMAGE, 'profile_sha256': allocation.PROFILE_SHA,
             'proof_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'runner_sources': row['spec']['sources'], 'online_ready': False,
             'browser_proven': False, 'import_ready': False, 'cleanup_verified': False}
    runner.publish(output / 'killed-state-proof.json', json.dumps(proof, indent=2).encode())

    # Explicit supervisor reconciliation after observing this exact child exit.
    # Preserve the old lock as evidence; this is no automatic stale-lock expiry.
    os.rename(registry / 'lock', registry / 'terminated-worker-lock')
    allocation._sync_directory(registry)
    old_home = os.environ.get('HOME')
    os.environ['HOME'] = str(home)
    handle = allocation.acquire_registry()
    try:
        current_daemon = runner.daemon_id()
        value, current = allocation._state(handle, current_daemon)
        current_row = current['allocations'][identity]
        if stage == 'before-create':
            # Never entered the Docker create call; retain the aborted intent.
            # A new begin still refuses ALLOCATION_UNRESOLVED in this owned HOME.
            try:
                new_identity = str(uuid.uuid4())
                spec = dict(current_row['spec'], arguments=[*current_row['spec']['arguments'][:2], new_identity])
                allocation.begin_allocation(handle, current_daemon, new_identity, spec)
            except RuntimeError as error:
                allocation.require(str(error) == 'ALLOCATION_UNRESOLVED')
            else:
                raise RuntimeError('ALLOCATION_PROOF_REPLAY_ACCEPTED')
            proof['no_create_entered'] = True
            proof['retained_aborted_intent'] = True
        else:
            identifier = observed['container']
            if stage == 'create-before-receipt':
                allocation.record_receipt(handle, runner.daemon_id(), identity, identifier,
                                          runner.inspect(identifier), profile.read_bytes())
            allocation.require(current_row['container'] in (None, identifier), 'ALLOCATION_PROOF_ID_MISMATCH')
            if stage == 'dispatch':
                wait_for(lambda: runner.inspect(identifier)['State']['Running'] is False)
                logs = runner.docker(['logs', identifier])
                allocation.require(logs.returncode == 0, 'ALLOCATION_PROOF_LOGS_FAILED')
                runner.publish(output / 'dispatch-stdout.bytes', logs.stdout)
                runner.validate_evidence(logs.stdout)
                allocation.require(json.loads(logs.stdout)['allowed'] == 1, 'ALLOCATION_PROOF_DISPATCH_MISSING')
                proof['observed_native_dispatch'] = True
            proof.update(allocation.cleanup_allocation(handle, runner.daemon_id(), identity, runner.inspect,
                lambda identifier: runner.remove(identifier, output, stage, stage == 'dispatch', proof, current_daemon),
                lambda identifier: runner.daemon_id() == current_daemon and runner.absent(identifier), profile.read_bytes()))
    finally:
        allocation.release_registry(handle)
        if old_home is None:
            os.environ.pop('HOME', None)
        else:
            os.environ['HOME'] = old_home
    runner.publish(output / 'reconciled-proof.json', json.dumps(proof, indent=2).encode())
    allocation.require(stage == 'before-create' or proof['cleanup_verified'], 'ALLOCATION_PROOF_CLEANUP_FAILED')
    print(stage + ': PASS; killed runner refused replay; exact recovery evidence retained', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', choices=STAGES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    profile = args.profile.resolve(strict=True)
    allocation.require(hashlib.sha256(profile.read_bytes()).hexdigest() == allocation.PROFILE_SHA)
    output = args.output.absolute()
    allocation.require(output == output.resolve() and output.is_relative_to(ROOT / 'tmp') and output != ROOT / 'tmp')
    if args.worker:
        allocation.require(Path.home() == output / 'home' and os.getppid() == int(os.environ.get('NATIVE_PROOF_SUPERVISOR', '0')), 'ALLOCATION_PROOF_SUPERVISOR_INVALID')
        allocation._private_directory(Path.home())
        worker(args.worker, profile, output)
        return
    allocation.require(not output.exists(), 'ALLOCATION_PROOF_OUTPUT_EXISTS')
    runner = runner_module()
    image = runner.checked_json(['image', 'inspect', allocation.IMAGE])[0]
    allocation.require(image['Id'] == allocation.IMAGE, 'ALLOCATION_PROOF_IMAGE_INVALID')
    allocation._private_directory(output, create=True)
    for stage in STAGES:
        prove(stage, profile, output / stage)


if __name__ == '__main__':
    main()

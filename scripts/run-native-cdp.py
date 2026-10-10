#!/usr/bin/env python3
"""Opt-in owned final-code synthetic CDP fixture; no broker or credentials.

Requires the exact pinned local image, explicit registry initialization once,
and separately applicable allocation/cleanup permission. Historical harness
receipts never count as this runner's qualification.
"""

import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import uuid

import native_cdp_allocation as allocation


ROOT = Path(__file__).resolve().parents[1]
BASE = ['/usr/bin/docker', '--host', allocation.ENDPOINT]
SOURCES = ['core.mjs', 'request-controller.mjs', 'internal/source-policy.mjs',
           'capability-pipe.mjs', 'capability-ordering.mjs', 'capability-bootstrap.mjs',
           'lab/native-composition.mjs', 'lab/native-capture.mjs', 'lab/native-runtime.mjs',
           'lab/native-restart.mjs', 'lab/native-verdict.mjs', 'lab/verify-native-observations.mjs']


def modes():
    raw = (ROOT / 'collector/lab/native-verdict.mjs').read_text()
    match = re.search(r'export const NATIVE_MODES = Object.freeze\((\[.*?\])\);', raw, re.S)
    allocation.require(match is not None, 'NATIVE_MODES_INVALID')
    values = ast.literal_eval(match.group(1))
    allocation.require(isinstance(values, list) and 0 < len(values) <= 64
                       and len(set(values)) == len(values)
                       and all(isinstance(v, str) and re.fullmatch(r'[a-z][a-z0-9-]{0,40}', v) for v in values), 'NATIVE_MODES_INVALID')
    return values


def docker(args, timeout=20, content=None):
    result = subprocess.run(BASE + args, env={'PATH': '/usr/bin:/bin'}, input=content,
                            capture_output=True, timeout=timeout)
    allocation.require(len(result.stdout) <= 1048576 and len(result.stderr) <= 1048576, 'NATIVE_OUTPUT_LIMIT')
    return result


def checked_json(args):
    result = docker(args)
    allocation.require(result.returncode == 0, 'NATIVE_DAEMON_OBSERVATION_FAILED')
    return json.loads(result.stdout)


def daemon_id():
    identity = docker(['info', '--format', '{{.ID}}'])
    allocation.require(identity.returncode == 0, 'NATIVE_DAEMON_UNAVAILABLE')
    value = identity.stdout.decode().strip()
    allocation.require(0 < len(value) <= 256, 'NATIVE_DAEMON_INVALID')
    return value


def inspect(identifier):
    rows = checked_json(['inspect', identifier])
    allocation.require(isinstance(rows, list) and len(rows) == 1, 'NATIVE_INSPECT_INVALID')
    return rows[0]


def absent(identifier):
    allocation.require(re.fullmatch(r'[0-9a-f]{64}', identifier), 'NATIVE_ID_INVALID')
    result = docker(['inspect', identifier])
    # Require an explicit daemon absence response for this exact full ID;
    # transport, permissions or generic inspection failures never prove it.
    if result.returncode == 0:
        return False
    stderr = result.stderr.decode('utf-8', errors='replace').strip()
    exact = re.fullmatch(r'(?:Error: No such object: |Error response from daemon: No such (?:object|container): )' + identifier, stderr)
    return result.returncode == 1 and bool(exact) and result.stdout.strip() in (b'', b'[]')


def remove(identifier, output, mode, retain_principal, receipt, expected_daemon=None):
    # Bounded container-level recovery, only after receipt/configuration checks.
    def same_daemon():
        if expected_daemon is not None:
            allocation.require(daemon_id() == expected_daemon, 'ALLOCATION_DAEMON_MISMATCH')
    same_daemon()
    stopped = docker(['stop', '--time', '10', identifier], timeout=15)
    if stopped.returncode != 0:
        same_daemon()
        killed = docker(['kill', identifier])
        if killed.returncode != 0:
            return False
    if inspect(identifier).get('State', {}).get('Running') is not False:
        return False
    if retain_principal:
        same_daemon()
        source = '/home/fixture/.local/state/ghostfolio-boursedirect-sync/synthetic-cdp/auth'
        captured = docker(['cp', identifier + ':' + source, '-'])
        if captured.returncode != 0:
            return False
        with tarfile.open(fileobj=io.BytesIO(captured.stdout), mode='r:') as archive:
            members = archive.getmembers()
            allocation.require(0 < len(members) <= 1000 and all(value.isdir() or value.isfile() for value in members), 'NATIVE_PRINCIPAL_ARCHIVE_INVALID')
            principal = hashlib.sha256(b'BD-SYNTHETIC-CDP-v1\nSYNTHETIC-NATIVE-CDP').hexdigest()
            journals = [value for value in members if value.name.rstrip('/') == 'auth/' + principal + '/journal.yaml' and value.isfile()]
            allocation.require(len(journals) == 1 and journals[0].size <= 1048576, 'NATIVE_PRINCIPAL_ARCHIVE_INVALID')
            # Full tar preserves uncertainty and temporary publications as well
            # as the journal; no extracted path can replace host state.
        publish(output / (mode + '-principal.tar'), captured.stdout)
        receipt['principal_archive_sha256'] = hashlib.sha256(captured.stdout).hexdigest()
        receipt['principal_retained'] = True
    same_daemon()
    removed = docker(['rm', identifier])
    return removed.returncode == 0


def archive_sources():
    files = {}
    for relative in SOURCES:
        source = ROOT / 'collector' / relative
        allocation.require(not source.is_symlink(), 'NATIVE_SOURCE_ALIAS')
        files['proof/' + relative] = source.read_bytes()
    package = ROOT / 'collector/node_modules/yaml'
    allocation.require(json.loads((package / 'package.json').read_text())['version'] == '2.9.1', 'NATIVE_DEPENDENCY_INVALID')
    for source in sorted(package.rglob('*')):
        allocation.require(not source.is_symlink(), 'NATIVE_SOURCE_ALIAS')
        if source.is_file():
            files['proof/node_modules/yaml/' + str(source.relative_to(package))] = source.read_bytes()
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
    hashes['runner'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hashes['allocation'] = hashlib.sha256((ROOT / 'scripts/native_cdp_allocation.py').read_bytes()).hexdigest()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, content in files.items():
            entry = tarfile.TarInfo(name)
            entry.uid = entry.gid = 1000
            entry.mode = 0o400
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    return buffer.getvalue(), hashes


def publish(filename, raw):
    allocation.require(not filename.exists() and not filename.is_symlink(), 'NATIVE_OUTPUT_EXISTS')
    with filename.open('xb') as stream:
        os.chmod(filename, 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    allocation._sync_directory(filename.parent)


def validate_evidence(raw):
    result = subprocess.run(['/usr/bin/node', '--import', str(ROOT / 'collector/tests/no-network.mjs'),
                             str(ROOT / 'collector/lab/verify-native-observations.mjs')],
                            input=raw, env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=5)
    allocation.require(result.returncode == 0 and len(result.stdout) <= 32768
                       and json.loads(result.stdout).get('passed') is True, 'NATIVE_VERDICT_FAILED')


def run(mode, profile_path, output, archive, hashes):
    profile = profile_path.read_bytes()
    allocation.require(hashlib.sha256(profile).hexdigest() == allocation.PROFILE_SHA, 'NATIVE_PROFILE_INVALID')
    handle = allocation.acquire_registry()
    identity = str(uuid.uuid4())
    spec = {'image': allocation.IMAGE, 'profile_sha256': allocation.PROFILE_SHA,
            'sources': hashes, 'entrypoint': '/usr/bin/node',
            'arguments': ['/home/fixture/proof/lab/native-runtime.mjs', mode, identity]}
    receipt = {'allocation': identity, 'mode': mode, 'sources': hashes, 'image': allocation.IMAGE,
               'profile_sha256': allocation.PROFILE_SHA, 'cleanup_verified': False,
               'online_ready': False, 'browser_proven': False, 'import_ready': False}
    owns_receipt = False
    attempted_start = False
    error = None
    try:
        daemon = daemon_id()
        owner = allocation.begin_allocation(handle, daemon, identity, spec)
        result = docker(['create', '--name', owner, '--label', 'proof.owner=' + owner,
                         '--label', 'proof.allocation=' + identity, '--network', 'none', '--user', '1000:1000',
                         '--env', 'HOME=/home/fixture', '--env', 'PATH=/usr/bin:/bin', '--restart', 'no',
                         '--ipc', 'private', '--memory', '768m', '--cpus', '1', '--pids-limit', '256', '--shm-size', '128m',
                         '--security-opt', 'seccomp=' + str(profile_path), '--entrypoint', spec['entrypoint'],
                         allocation.IMAGE] + spec['arguments'])
        allocation.require(result.returncode == 0, 'NATIVE_CREATE_UNCERTAIN')
        identifier = result.stdout.decode().strip()
        allocation.require(re.fullmatch(r'[0-9a-f]{64}', identifier), 'NATIVE_CREATE_UNCERTAIN')
        details = inspect(identifier)
        allocation.record_receipt(handle, daemon_id(), identity, identifier, details, profile)
        owns_receipt = True
        receipt['container'] = identifier
        copied = docker(['cp', '-', identifier + ':/home/fixture'], content=archive)
        allocation.require(copied.returncode == 0, 'NATIVE_ARCHIVE_COPY_FAILED')
        allocation.require(archive_sources()[1] == hashes, 'NATIVE_SOURCES_CHANGED')
        allocation.before_start(handle, daemon_id(), identity, inspect, profile)
        allocation.require(daemon_id() == daemon, 'ALLOCATION_DAEMON_MISMATCH')
        attempted_start = True
        result = docker(['start', '-a', identifier], timeout=55)
        publish(output / (mode + '-stdout.bytes'), result.stdout)
        publish(output / (mode + '-stderr.bytes'), result.stderr)
        allocation.require(result.returncode == 0, 'NATIVE_RUNTIME_FAILED')
        allocation.require(archive_sources()[1] == hashes, 'NATIVE_SOURCES_CHANGED')
        validate_evidence(result.stdout)
        evidence = json.loads(result.stdout)
        allocation.require(evidence['mode'] == mode and evidence['node'] == 'v20.19.2'
                           and evidence['passed'] is True and evidence['owned_browser_exit'] is True
                           and all(evidence[k] is False for k in ('online_ready', 'browser_proven', 'import_ready')), 'NATIVE_VERDICT_FAILED')
        receipt['evidence'] = evidence
    except Exception:
        error = 'NATIVE_QUALIFICATION_INCOMPLETE'
    finally:
        if owns_receipt:
            try:
                receipt.update(allocation.cleanup_allocation(handle, daemon_id(), identity, inspect,
                    lambda identifier: remove(identifier, output, mode, attempted_start, receipt, daemon),
                    lambda identifier: daemon_id() == daemon and absent(identifier), profile))
            except Exception:
                error = 'NATIVE_CLEANUP_UNCERTAIN'
        allocation.release_registry(handle)
        receipt['error'] = error
        publish(output / (mode + '-receipt.yaml'), json.dumps(receipt, indent=2).encode())
    allocation.require(error is None and receipt['cleanup_verified'], 'NATIVE_QUALIFICATION_INCOMPLETE')
    print(mode + ': PASS; exact owned cleanup verified; readiness false', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New ignored tmp/ private evidence directory')
    parser.add_argument('--scenario', action='append', choices=modes())
    parser.add_argument('--initialize-registry', action='store_true', help='Explicit first-use initialization only; never reset existing state')
    args = parser.parse_args()
    selected = args.scenario or modes()
    allocation.require(len(set(selected)) == len(selected), 'NATIVE_MODES_INVALID')
    profile = args.profile.resolve(strict=True)
    allocation.require(hashlib.sha256(profile.read_bytes()).hexdigest() == allocation.PROFILE_SHA, 'NATIVE_PROFILE_INVALID')
    output = args.output.absolute()
    allocation.require(output == output.resolve() and output.is_relative_to(ROOT / 'tmp')
                       and output != ROOT / 'tmp' and not output.exists(), 'NATIVE_OUTPUT_INVALID')
    image = checked_json(['image', 'inspect', allocation.IMAGE])[0]
    allocation.require(image['Id'] == allocation.IMAGE
                       and image['Config']['Labels']['bd.cdp-capability'] == '415a78dfcc5444e3902473da5af2fd07', 'NATIVE_IMAGE_INVALID')
    archive, hashes = archive_sources()
    if args.initialize_registry:
        allocation.initialize_registry(daemon_id())
    allocation._private_directory(output, create=True)
    for mode in selected:
        run(mode, profile, output, archive, hashes)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('NATIVE_QUALIFICATION_INCOMPLETE') from None

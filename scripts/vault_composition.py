#!/usr/bin/env python3
"""Owned two-container synthetic vault/Chromium acceptance, never live access.

Uses the current locally built image by exact ID. Private pipes carry invented
secrets; receipts/journals persist under a new ignored output root. No discovery,
shared mounts, production credentials, real vault CLI or broker requests.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import tarfile
import time
import uuid

import native_cdp_allocation as private

ROOT = Path(__file__).resolve().parents[1]
BASE = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']
SCENARIOS = ['success', 'wrong-stage', 'expired', 'fsync', 'pipe-loss', 'browser-crash']
SECRETS = ['SYNTHETIC_API', 'SYNTHETIC_UNLOCK', 'SYNTHETIC_SESSION', 'SYNTHETIC_PASSWORD',
           'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ', '123456']
FILES = ['core.mjs', 'credential-provider.mjs', 'vault-worker.mjs', 'private-channel.mjs',
         'private-process.mjs', 'request-controller.mjs', 'capability-pipe.mjs',
         'capability-bootstrap.mjs', 'capability-ordering.mjs', 'internal/source-policy.mjs',
         'lab/native-composition.mjs', 'lab/fake-bw.mjs', 'lab/vault-worker-runtime.mjs',
         'lab/vault-browser-launcher.mjs', 'lab/vault-collector-runtime.mjs']


def require(value, code='VAULT_COMPOSITION_REJECTED'):
    private.require(value, code)


def docker(args, content=None, timeout=20):
    result = subprocess.run(BASE + args, input=content, capture_output=True,
                            env={'PATH': '/usr/bin:/bin'}, timeout=timeout)
    require(len(result.stdout) <= 2097152 and len(result.stderr) <= 1048576)
    return result


def daemon():
    result = docker(['info', '--format', '{{.ID}}'])
    require(result.returncode == 0, 'VAULT_DAEMON_UNAVAILABLE')
    value = result.stdout.decode().strip()
    require(0 < len(value) <= 256)
    return value


def inspect(identifier):
    require(re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', identifier))
    result = docker(['inspect', identifier])
    require(result.returncode == 0, 'VAULT_INSPECTION_FAILED')
    rows = json.loads(result.stdout)
    require(isinstance(rows, list) and len(rows) == 1)
    return rows[0]


def archive(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as tar:
        for name, (raw, mode) in files.items():
            entry = tarfile.TarInfo(name)
            entry.uid = entry.gid = 1000
            entry.mode = mode
            entry.size = len(raw)
            tar.addfile(entry, io.BytesIO(raw))
    return out.getvalue()


def sources():
    files = {'proof/' + name: ((ROOT / 'collector' / name).read_bytes(),
                              0o500 if name == 'lab/fake-bw.mjs' else 0o400) for name in FILES}
    dependency = ROOT / 'collector/node_modules/yaml'
    require(json.loads((dependency / 'package.json').read_bytes())['version'] == '2.9.1')
    for filename in sorted(dependency.rglob('*')):
        require(not filename.is_symlink())
        if filename.is_file():
            files['proof/node_modules/yaml/' + str(filename.relative_to(dependency))] = (filename.read_bytes(), 0o400)
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, (raw, _) in files.items()}
    hashes['runner'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    hashes['private-allocation'] = hashlib.sha256((ROOT / 'scripts/native_cdp_allocation.py').read_bytes()).hexdigest()
    return archive(files), hashes


def validate_runtime(details, row, profile):
    config, host = details.get('Config', {}), details.get('HostConfig', {})
    require(details.get('Id') == row['id'] and details.get('Image') == row['image']
            and config.get('Labels') == {'proof.owner': row['owner']}
            and config.get('User') == '1000:1000' and config.get('Entrypoint') == ['/usr/bin/node']
            and config.get('Cmd') == [row['entry']]
            and set(config.get('Env', [])) == {'HOME=/home/fixture', 'PATH=/usr/bin:/bin'}
            and host.get('NetworkMode') == 'none' and host.get('LogConfig') == {'Type': 'none', 'Config': {}}
            and host.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0}
            and host.get('Privileged') is False and not host.get('CapAdd')
            and host.get('PidMode', '') == '' and host.get('IpcMode') == 'private'
            and host.get('Memory') == 805306368 and host.get('NanoCpus') == 1000000000
            and host.get('PidsLimit') == 256 and host.get('ShmSize') == 134217728
            and details.get('Mounts') == [], 'VAULT_RUNTIME_MISMATCH')
    require(host.get('Ulimits') == [{'Name': 'core', 'Hard': 0, 'Soft': 0}], 'VAULT_RUNTIME_MISMATCH')
    require(host.get('Tmpfs') == {'/vault': 'rw,noexec,nosuid,mode=0700,uid=1000,gid=1000'}, 'VAULT_RUNTIME_MISMATCH')
    opts = host.get('SecurityOpt', [])
    require(len(opts) == 1 and opts[0].startswith('seccomp=')
            and json.loads(opts[0].split('=', 1)[1]) == json.loads(profile), 'VAULT_RUNTIME_MISMATCH')
    require(not any(value in json.dumps(details) for value in SECRETS), 'VAULT_METADATA_LEAK')


def allocate(state, filename, role, image, profile_path, payload, operations=None):
    # A deliberately small, fixed lifecycle; injected operations exist for offline
    # kill-window tests. A receipt is the only grant for start/remove authority.
    ops = operations or {'daemon': daemon, 'docker': docker, 'inspect': inspect}
    require(state['daemon'] == ops['daemon'](), 'VAULT_DAEMON_MISMATCH')
    require(role in ('worker', 'browser') and role not in state['resources'])
    owner = 'owned-vault-' + role + '-' + state['run']
    entry = '/home/fixture/proof/lab/' + ('vault-worker-runtime.mjs' if role == 'worker' else 'vault-browser-launcher.mjs')
    row = {'state': 'intent', 'owner': owner, 'image': image, 'entry': entry, 'id': None}
    state['resources'][role] = row
    private._publish(filename, state)  # Must succeed before create.
    args = ['create', '--interactive', '--name', owner, '--label', 'proof.owner=' + owner,
            '--network', 'none', '--user', '1000:1000', '--env', 'HOME=/home/fixture', '--env', 'PATH=/usr/bin:/bin',
            '--restart', 'no', '--log-driver', 'none', '--ulimit', 'core=0', '--ipc', 'private', '--memory', '768m',
            '--cpus', '1', '--pids-limit', '256', '--shm-size', '128m', '--tmpfs', '/vault:rw,noexec,nosuid,mode=0700,uid=1000,gid=1000',
            '--security-opt', 'seccomp=' + str(profile_path), '--entrypoint', '/usr/bin/node', image, entry]
    created = ops['docker'](args)
    require(created.returncode == 0, 'VAULT_CREATE_UNCERTAIN')
    identifier = created.stdout.decode().strip()
    require(re.fullmatch(r'[0-9a-f]{64}', identifier), 'VAULT_CREATE_UNCERTAIN')
    candidate = {**row, 'id': identifier}
    details = ops['inspect'](identifier)
    validate_runtime(details, candidate, profile_path.read_bytes())
    require(details['State']['Running'] is False and details['State']['Status'] == 'created')
    require(state['daemon'] == ops['daemon'](), 'VAULT_DAEMON_MISMATCH')
    row.update(id=identifier, state='receipted')
    private._publish(filename, state)  # No start/secret delivery until this fsync completes.
    require(ops['docker'](['cp', '-', identifier + ':/home/fixture'], content=payload).returncode == 0)
    return identifier


def before_start(state, filename, role, profile, operations=None):
    ops = operations or {'daemon': daemon, 'inspect': inspect}
    # Re-read durable state, rather than trusting a failed publication's memory.
    durable = private._read(filename)
    require(durable == state and durable['daemon'] == ops['daemon'](), 'VAULT_DAEMON_MISMATCH')
    row = durable['resources'][role]
    require(row['state'] == 'receipted' and re.fullmatch(r'[0-9a-f]{64}', row['id']), 'VAULT_RECEIPT_REQUIRED')
    details = ops['inspect'](row['id'])
    validate_runtime(details, row, profile)
    require(details['State']['Status'] == 'created' and details['State']['Running'] is False)
    state['resources'][role]['state'] = 'started'
    private._publish(filename, state)
    return row['id']


def send(process, value):
    raw = json.dumps(value, separators=(',', ':')).encode() + b'\n'
    require(len(raw) <= 32768)
    process.stdin.write(raw)
    process.stdin.flush()


def receive(process, timeout=45, allow_result=False):
    raw, stderr = b'', 0
    end = time.monotonic() + timeout
    with selectors.DefaultSelector() as ready:
        ready.register(process.stdout, selectors.EVENT_READ, 'out')
        ready.register(process.stderr, selectors.EVENT_READ, 'err')
        while time.monotonic() < end:
            for key, _ in ready.select(max(0, end - time.monotonic())):
                chunk = os.read(key.fileobj.fileno(), 32769)
                require(chunk, 'VAULT_PIPE_LOST')
                if key.data == 'err':
                    stderr += len(chunk)
                    require(stderr <= 32768)
                    continue
                raw += chunk
                require(len(raw) <= 32768)
                if b'\n' in raw:
                    require(raw.count(b'\n') == 1 and raw.endswith(b'\n'))
                    def unique(pairs):
                        result = {}
                        for key, value in pairs:
                            require(key not in result)
                            result[key] = value
                        return result
                    value = json.loads(raw, object_pairs_hook=unique)
                    require(isinstance(value, dict) and ('error' not in value or (allow_result
                            and value['error'] == 'SYNTHETIC_COMPOSITION_REFUSED')), 'VAULT_PRIVATE_REFUSAL')
                    return value
    raise RuntimeError('VAULT_PIPE_TIMEOUT')


def cleanup(state, filename, profile, output):
    # Only durable receipted IDs are eligible; intent-only orphans remain fenced.
    durable = private._read(filename)
    require(durable['daemon'] == daemon(), 'VAULT_DAEMON_MISMATCH')
    for role in ('browser', 'worker'):
        row = durable['resources'].get(role)
        if row is None or row['state'] == 'absence_verified':
            continue
        require(row['state'] in ('receipted', 'started'), 'VAULT_UNRECEIPTED_ORPHAN')
        identifier = row['id']
        validate_runtime(inspect(identifier), row, profile)
        require(durable['daemon'] == daemon(), 'VAULT_DAEMON_MISMATCH')
        stopped = docker(['stop', '--time', '5', identifier], timeout=10)
        require(stopped.returncode == 0 and inspect(identifier)['State']['Running'] is False, 'VAULT_STOP_UNVERIFIED')
        if role == 'browser':
            if docker(['cp', identifier + ':/home/fixture/bootstrap-protocol.bytes', str(output / 'bootstrap-protocol.bytes')]).returncode == 0:
                os.chmod(output / 'bootstrap-protocol.bytes', 0o600)
            captured = docker(['cp', identifier + ':/home/fixture/.local', '-'])
            require(captured.returncode == 0)
            # Keep the complete private journal archive; never extract onto host.
            with tarfile.open(fileobj=io.BytesIO(captured.stdout)) as tar:
                members = tar.getmembers()
                require(all(m.isdir() or m.isfile() for m in members))
                journals = [m for m in members if m.name.endswith('/journal.yaml')]
                require(len(journals) == 1 and journals[0].size < 1048576)
                journal = private.yaml.safe_load(tar.extractfile(journals[0]).read())
                require(journal['installation_id'] == state['installation'])
            private._publish(output / 'retained-auth.yaml', journal, exclusive=True)
            with (output / 'retained-auth.tar').open('xb') as stream:
                os.chmod(stream.name, 0o600)
                stream.write(captured.stdout)
                stream.flush()
                os.fsync(stream.fileno())
            private._sync_directory(output)
        require(durable['daemon'] == daemon(), 'VAULT_DAEMON_MISMATCH')
        require(docker(['rm', identifier]).returncode == 0, 'VAULT_REMOVE_UNVERIFIED')
        absence = docker(['inspect', identifier])
        require(absence.returncode == 1 and absence.stdout.strip() in (b'', b'[]')
                and re.fullmatch(r'(?:Error: No such object: |error: no such object: |Error response from daemon: No such (?:object|container): )'
                                 + identifier, absence.stderr.decode().strip()), 'VAULT_ABSENCE_UNVERIFIED')
        row['state'] = 'absence_verified'
        private._publish(filename, durable)
    state.update(durable)


def run(scenario, image, chrome_version, profile_path, output, payload, hashes):
    private._private_directory(output, create=True)
    allocation = str(uuid.uuid4())
    installation = str(uuid.uuid4())
    state = {'run': allocation, 'installation': installation, 'daemon': daemon(), 'image': image,
             'chrome': chrome_version, 'sources': hashes, 'resources': {}}
    filename = output / 'registry.yaml'
    private._publish(filename, state, exclusive=True)
    enrollment = {'schema_version': 2, 'principal': hashlib.sha256(b'BD-SYNTHETIC-CDP-v1\nSYNTHETIC-NATIVE-CDP').hexdigest(),
                  'installation_id': installation, 'attempts': {}, 'policy': 'synthetic-cdp-v1',
                  'origin': 'http://127.0.0.1:48123', 'allocation_id': allocation}
    private._publish(output / 'enrollment.yaml', enrollment, exclusive=True)
    journal_path = '.local/state/ghostfolio-boursedirect-sync/synthetic-cdp/auth/' + enrollment['principal'] + '/journal.yaml'
    auth = archive({journal_path: (private.yaml.safe_dump(enrollment).encode(), 0o600)})
    # tar parents need private ownership/mode for the existing authority helper.
    auth_io = io.BytesIO()
    with tarfile.open(fileobj=auth_io, mode='w') as tar:
        parts = Path(journal_path).parts[:-1]
        for i in range(1, len(parts) + 1):
            entry = tarfile.TarInfo('/'.join(parts[:i]))
            entry.type = tarfile.DIRTYPE
            entry.uid = entry.gid = 1000
            entry.mode = 0o700
            tar.addfile(entry)
        with tarfile.open(fileobj=io.BytesIO(auth)) as original:
            entry = original.getmembers()[0]
            tar.addfile(entry, original.extractfile(entry))
    account = b'source_account: invented\n'
    binding = {'itemId': str(uuid.uuid4()), 'name': 'invented', 'uri': 'https://www.boursedirect.fr/synthetic',
               'principalHash': hashlib.sha256(b'BD-AUTH-v1\nSYNTHETIC').hexdigest(),
               'accountConfig': {'path': '/home/fixture/account.yaml', 'sha256': hashlib.sha256(account).hexdigest()}}
    expected = {'runNonce': allocation, 'stageNonce': str(uuid.uuid4())}
    worker = browser = None
    result, worker_result, failure = None, None, None
    try:
        worker_id = allocate(state, filename, 'worker', image, profile_path, payload)
        browser_id = allocate(state, filename, 'browser', image, profile_path, payload)
        require(docker(['cp', '-', browser_id + ':/home/fixture'], content=auth_io.getvalue()).returncode == 0)
        require(docker(['cp', '-', browser_id + ':/home/fixture'], content=archive({'account.yaml': (account, 0o600)})).returncode == 0)
        require(sources()[1] == hashes, 'VAULT_SOURCES_CHANGED')
        before_start(state, filename, 'worker', profile_path.read_bytes())
        worker = subprocess.Popen(BASE + ['start', '-ai', worker_id], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin'}, bufsize=0)
        config = {'schema_version': 1, 'vaultOrigin': 'https://vault.synthetic.invalid', 'binding': binding,
                  'cli': {'path': '/home/fixture/proof/lab/fake-bw.mjs',
                          'sha256': hashes['proof/lab/fake-bw.mjs'], 'version': 'synthetic-1', 'defaultsVerified': False}}
        send(worker, {'configuration': config, 'expected': expected, 'credentials': {
            'BW_CLIENTID': 'SYNTHETIC_CLIENT', 'BW_CLIENTSECRET': 'SYNTHETIC_API', 'BW_PASSWORD': 'SYNTHETIC_UNLOCK'}})
        selected = receive(worker)['selected']
        require(selected['itemId'] == binding['itemId'] and selected['principalHash'] == binding['principalHash']
                and selected['accountConfig'] == binding['accountConfig'] and selected['online_ready'] is False)
        require('totp' not in selected and not any(value in json.dumps(selected) for value in SECRETS[:3] + SECRETS[4:]))
        # Existing enrollment and immutable account reference precede browser startup.
        require(private._read(output / 'enrollment.yaml') == enrollment)
        before_start(state, filename, 'browser', profile_path.read_bytes())
        browser = subprocess.Popen(BASE + ['start', '-ai', browser_id], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, env={'PATH': '/usr/bin:/bin'}, bufsize=0)
        send(browser, {'selected': selected, 'expected': expected, 'allocation': allocation, 'scenario': scenario,
                       'chromeVersion': chrome_version})
        request = receive_result(browser)
        if request != expected:
            result = request
        require(request == expected)
        send(worker, request)
        code = receive(worker)
        require(set(code) == {'runNonce','stageNonce','code','startedAt','completedAt','profile'})
        if scenario == 'wrong-stage':
            code['stageNonce'] = str(uuid.uuid4())
        send(browser, code)
        # Refusal is an expected negative result, not a transport exception.
        result = receive_result(browser)
        send(worker, {'finish': True})
        worker_result = receive(worker)
        require(worker_result == {'commands': 6, 'totpCalls': 1, 'online_ready': False})
        require(result['passwordPosts'] == 1 and result['otpPosts'] == (1 if scenario == 'success' else 0)
                and result['browserExited'] is True and result['restartFenced'] is True
                and result['passed'] == (scenario == 'success')
                and all(result[key] is False for key in ('online_ready','browser_proven','import_ready')))
        require(not any(value in json.dumps(result) for value in SECRETS))
        require(sources()[1] == hashes, 'VAULT_SOURCES_CHANGED')
    except Exception as error:
        failure = 'VAULT_COMPOSITION_INCOMPLETE'
        # Fixed code only; private runtime failures are never printed verbatim.
        if str(error) in ('VAULT_PIPE_LOST','VAULT_PRIVATE_REFUSAL','VAULT_PIPE_TIMEOUT'):
            failure = str(error)
    finally:
        cleanup(state, filename, profile_path.read_bytes(), output)
        # Stop exact owned containers before closing live host-side pipes.
        for process in (browser, worker):
            if process:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
        private._publish(output / 'evidence.yaml', {'scenario': scenario, 'failure': failure, 'result': result,
                                                  'worker': worker_result, 'cleanup_verified': True,
                                                  'online_ready': False}, exclusive=True)
    require(failure is None, failure)
    print(scenario + ': PASS; two exact owned IDs removed; readiness false', flush=True)


def receive_result(process):
    # Negative collector results have a fixed public error field. Keep channel's
    # ordinary worker errors as failures while accepting that typed final result.
    return receive(process, allow_result=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, help='Exact locally built image ID')
    parser.add_argument('--chrome-version', required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scenario', action='append', choices=SCENARIOS)
    args = parser.parse_args()
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', args.image))
    require(re.fullmatch(r'\d+\.\d+\.\d+\.\d+', args.chrome_version))
    profile = args.profile.resolve(strict=True)
    require(hashlib.sha256(profile.read_bytes()).hexdigest() == private.PROFILE_SHA)
    image = inspect(args.image)['Id']
    output = args.output.absolute()
    require(output == output.resolve() and output.is_relative_to(ROOT / 'tmp') and not output.exists())
    payload, hashes = sources()
    private._private_directory(output, create=True)
    selected = args.scenario or SCENARIOS
    require(len(selected) == len(set(selected)))
    for scenario in selected:
        run(scenario, image, args.chrome_version, profile, output / scenario, payload, hashes)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('VAULT_COMPOSITION_INCOMPLETE') from None

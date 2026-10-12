"""Refresh missing vault metadata through the existing exact-owned CLI only."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import uuid

import source_connection as replay

CODE_ROOT = Path(__file__).resolve().parents[1]
LIMIT = 32768


def read_frame(process, selector, pending, deadline):
    while b'\n' not in pending:
        replay.require(time.monotonic() < deadline)
        ready = selector.select(min(1, max(0, deadline - time.monotonic())))
        for key, _ in ready:
            raw = os.read(key.fd, LIMIT + 1)
            if key.data == 'stderr':
                replay.require(raw == b'')
                selector.unregister(key.fd)
                continue
            replay.require(raw)
            pending += raw
            replay.require(len(pending) <= LIMIT)
            if b'\n' in pending:
                break
    row, trailing = pending.split(b'\n', 1)
    replay.require(not trailing and row)
    value = replay.private._decode(row)
    replay.require(isinstance(value, dict))
    return value


def write_frame(process, value):
    raw = json.dumps(value, separators=(',', ':')).encode() + b'\n'
    replay.require(len(raw) <= LIMIT)
    process.stdin.write(raw)
    process.stdin.flush()


def exchange(process, input_record, operations, timeout=300):
    """Private serial RPC; terminal output can never be a raw CLI response."""
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
        selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
        write_frame(process, input_record)
        deadline = time.monotonic() + timeout
        for _ in range(40):
            row = read_frame(process, selector, b'', deadline)
            action = row.get('action')
            if action == 'complete':
                replay.require(set(row) == {'action', 'selected', 'session_logged_out', 'totp_requests'}
                    and row['session_logged_out'] is True and type(row['totp_requests']) is int
                    and row['totp_requests'] == 0)
                replay.require(process.wait(timeout=10) == 0)
                process.stdin.close()
                replay.require(process.stdout.read(1) == b'' and process.stderr.read(1) == b'')
                return row['selected']
            replay.require(action in operations)
            write_frame(process, {'result': operations[action](row)})
        raise RuntimeError('SOURCE_REPLAY_REFUSED')
    finally:
        selector.close()


def stop_owned_cli(q, lab, identifier):
    """Reconcile only the previously receipted CLI, including an interrupted stop."""
    current = q.load()
    replay.require(current['containers']['bitwarden-cli']['id'] == identifier)
    replay.require(current['state'] in ('routes_qualified', 'cli_stop_intent', 'cli_stopped_owned'))
    details = q.owned(current, 'container', identifier)
    q.validate_container(current, 'bitwarden-cli', details)
    if details['State']['Running']:
        replay.require(current['state'] != 'cli_stopped_owned'
            and details['State']['Pid'] == current['containers']['bitwarden-cli']['pid'])
        if current['state'] == 'routes_qualified':
            replay.private._publish(lab / ('vault-before-stop-' + uuid.uuid4().hex + '.yaml'), current, exclusive=True)
            current['state'] = 'cli_stop_intent'
            q.save(current)
        q.docker(['stop', '--time', '5', identifier])
        details = q.owned(current, 'container', identifier)
        q.validate_container(current, 'bitwarden-cli', details)
    replay.require(details['State']['Running'] is False and details['State']['Pid'] == 0)
    replay.require(current['state'] in ('cli_stop_intent', 'cli_stopped_owned'))
    if current['state'] != 'cli_stopped_owned':
        current['state'] = 'cli_stopped_owned'
        current['containers']['bitwarden-cli'].update(state='stopped', pid=0)
        q.save(current)
    return True


def inspect(root, lab, inventory):
    reference = inventory['evidence'].get('vault_cli_binding')
    replay.require(reference is not None)
    raw = replay.private._read_bytes(replay.contained(root, reference['path']))
    replay.require(hashlib.sha256(raw).hexdigest() == reference['sha256'])
    binding = json.loads(raw)
    previous_ref = inventory['evidence']['vault_inspection']
    previous = replay.private._read(replay.contained(root, previous_ref['path']))
    replay.require(previous['binding_sha256'] == reference['sha256'])
    configuration = binding['configuration']
    replay.require(configuration['schema_version'] == 3)
    verified = inventory['_verified_helpers']
    vault = replay.helper(lab, 'attest', verified).attest()
    q = replay.helper(lab, 'qualify', verified)
    identifier = vault['containers']['bitwarden-cli']['id']
    replay.require(binding['containerId'] == identifier
        and binding['egressProxy'] == 'http://' + vault['proxy_ip'] + ':8080')
    source = CODE_ROOT / 'collector/lab/owned-vault-inspection-command.mjs'
    clean = subprocess.run(['git', '-C', str(CODE_ROOT), 'status', '--porcelain'], capture_output=True, check=True)
    replay.require(clean.stdout == b'')
    head = subprocess.run(['git', '-C', str(CODE_ROOT), 'rev-parse', 'HEAD'],
        capture_output=True, check=True, text=True).stdout.strip()
    files = ['collector/owned-vault-inspection.mjs', 'collector/lab/owned-vault-inspection-command.mjs',
        'collector/bitwarden-cli.mjs', 'collector/bitwarden-cli.sh', 'collector/vault-worker.mjs',
        'collector/credential-provider.mjs', 'collector/private-channel.mjs', 'collector/core.mjs',
        'collector/internal/source-policy.mjs', 'collector/private-process.mjs',
        'collector/package-lock.json', 'scripts/source_vault_inspection.py', 'scripts/source_connection.py']
    hashes = {name: hashlib.sha256((CODE_ROOT / name).read_bytes()).hexdigest() for name in files}
    output = root / ('inputs/vault-access/alias-inspection-' + uuid.uuid4().hex)
    output.mkdir(mode=0o700)
    intent = {'schema_version': 1, 'owner': 'infra-4g8u.70', 'state': 'vault_metadata_inspection_reserved',
        'source_commit': head, 'source_hashes': hashes,
        'binding_sha256': reference['sha256'], 'previous_inspection_sha256': previous_ref['sha256'],
        'broker_requests': 0, 'totp_requests': 0}
    replay.private._publish(output / 'attempt.yaml', intent, exclusive=True)
    process = None
    passed = False

    def attest(row):
        replay.require(set(row) == {'action', 'containerId', 'pin'}
            and row['containerId'] == identifier and row['pin'] == configuration['cli'])
        current = replay.helper(lab, 'attest', verified).attest()
        replay.require(current['containers']['bitwarden-cli']['id'] == identifier)
        return True

    def stop(row):
        replay.require(set(row) == {'action', 'containerId'} and row['containerId'] == identifier)
        return stop_owned_cli(q, lab, identifier)

    lease = lab / 'vault-operation.lock'
    lease.mkdir(mode=0o700)
    lease_parent = os.open(lab, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(lease_parent)
    finally:
        os.close(lease_parent)
    try:
        credentials = replay.helper(lab, 'provision', verified).initial_environment()
        process = subprocess.Popen(['/usr/bin/node', str(source)], cwd=CODE_ROOT,
            env={'PATH': '/usr/bin:/bin', 'HOME': str(Path.home())},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        selected = exchange(process, {'configuration': configuration, 'containerId': identifier,
            'egressProxy': binding['egressProxy'], 'destination': binding['destination'], 'credentials': credentials},
            {'attest': attest, 'stop': stop})
        credentials = None
        expected = previous['selected']
        replay.require(set(selected) == set(expected) | {'uriAliasesSha256'}
            and all(selected[key] == value for key, value in expected.items())
            and isinstance(selected['uriAliasesSha256'], str)
            and len(selected['uriAliasesSha256']) == 64
            and all(char in '0123456789abcdef' for char in selected['uriAliasesSha256']))
        replay.private._publish(output / 'inspection.yaml', {**intent,
            'state': 'same_identity_alias_metadata_verified', 'selected': selected,
            'session_logged_out': True, 'owned_process_exited': True}, exclusive=True)
        replay.private._publish(output / 'attempt.yaml', {**intent, 'state': 'verified_logged_out'})
        passed = True
        return {'code': 'SOURCE_VAULT_ALIAS_METADATA_VERIFIED', 'matched_items': 1,
            'session_logged_out': True, 'totp_requests': 0, 'broker_requests': 0}
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        if not passed:
            try:
                stop({'action': 'stop', 'containerId': identifier})
                cleanup = 'OWNED_CLI_STOPPED'
            except Exception:
                cleanup = 'OWNED_CLI_STOP_UNCERTAIN'
            replay.private._publish(output / 'attempt.yaml', {**intent, 'state': 'refused_preserved', 'cleanup': cleanup})

        if passed or cleanup == 'OWNED_CLI_STOPPED':
            lease.rmdir()
            parent = os.open(lab, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)

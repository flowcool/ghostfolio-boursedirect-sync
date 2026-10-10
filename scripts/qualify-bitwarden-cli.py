#!/usr/bin/env python3
"""One actual-CLI offline metadata proof; no secrets, authentication or networking."""
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import uuid
from pathlib import Path

import native_cdp_allocation as private

ROOT = Path(__file__).resolve().parents[1]
ENV = ['PATH=/usr/bin:/bin', 'HOME=/data', 'BITWARDENCLI_APPDATA_DIR=/data']
SERVER = 'https://bitwarden.com'
TMPFS = {'/data': 'rw,noexec,nosuid,nodev,mode=0700,uid=1000,gid=1000',
         '/tmp': 'rw,nosuid,nodev,mode=1777'}


def require(value):
    private.require(value, 'CLI_QUALIFICATION_REFUSED')


def transport(destination):
    require(isinstance(destination, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}', destination))
    def docker(args):
        command = shlex.join(['/usr/bin/docker'] + args)
        result = subprocess.run(['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                                 '-o', 'ConnectTimeout=10', '--', destination, command],
                                capture_output=True, env={'PATH': '/usr/bin:/bin'}, timeout=25)
        require(len(result.stdout) <= 2097152 and len(result.stderr) <= 32768)
        return result
    return docker


def daemon(docker):
    result = docker(['info', '--format', '{{.ID}}'])
    require(result.returncode == 0)
    value = result.stdout.decode().strip()
    require(0 < len(value) <= 256)
    return value


def inspect(docker, identifier):
    require(re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', identifier))
    result = docker(['inspect', identifier])
    require(result.returncode == 0)
    rows = json.loads(result.stdout)
    require(isinstance(rows, list) and len(rows) == 1)
    return rows[0]


def validate(details, row):
    config, host = details.get('Config', {}), details.get('HostConfig', {})
    require(details.get('Id') == row['id'] and details.get('Image') == row['image']
            and config.get('Labels') == row['labels'] and config.get('User') == '1000:1000'
            and config.get('Entrypoint') == ['/bin/sleep'] and config.get('Cmd') == ['180']
            and set(config.get('Env', [])) == set(ENV) and host.get('NetworkMode') == 'none'
            and host.get('ReadonlyRootfs') is True and host.get('Privileged') is False
            and not host.get('CapAdd') and host.get('CapDrop') == ['ALL']
            and host.get('SecurityOpt') == ['no-new-privileges']
            and host.get('LogConfig') == {'Type': 'none', 'Config': {}}
            and host.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0}
            and host.get('Ulimits') == [{'Name': 'core', 'Hard': 0, 'Soft': 0}]
            and host.get('Memory') == 268435456 and host.get('NanoCpus') == 1000000000
            and host.get('PidsLimit') == 64 and host.get('IpcMode') == 'private'
            and host.get('PidMode', '') == '' and host.get('Tmpfs') == TMPFS
            and not host.get('Binds') and details.get('Mounts') == []
            and not host.get('PortBindings') and host.get('PublishAllPorts') is False)


def attest(filename, docker):
    row = private._read(filename)
    require(row['state'] in ('receipted', 'started') and row['daemon'] == daemon(docker))
    details = inspect(docker, row['id'])
    validate(details, row)
    return row, details


def cleanup(filename, docker):
    # Re-read the published receipt. An in-memory create ID never grants removal.
    row = private._read(filename)
    if row['state'] == 'intent':
        return False
    row, details = attest(filename, docker)
    if details['State']['Running']:
        require(docker(['stop', '--time', '5', row['id']]).returncode == 0)
    row, details = attest(filename, docker)
    require(details['State']['Running'] is False)
    require(docker(['rm', row['id']]).returncode == 0)
    require(row['daemon'] == daemon(docker))
    absent = docker(['inspect', row['id']])
    require(absent.returncode == 1 and absent.stdout.strip() in (b'', b'[]')
            and re.fullmatch(r'(?:Error: No such object: |error: no such object: |Error response from daemon: No such (?:object|container): )'
                             + row['id'], absent.stderr.decode().strip()))
    row['state'] = 'absence_verified'
    private._publish(filename, row)
    return True


def qualify(destination, output, docker):
    private._private_directory(output, create=True)
    filename = output / 'registry.yaml'
    require(not filename.exists() and not filename.is_symlink())  # Never reset/reallocate.
    facts_path = ROOT / 'docs/verification/bitwarden-cli.yaml'
    facts = private.yaml.safe_load(facts_path.read_bytes())['existing_artifact_facts']
    image = inspect(docker, facts['image_id'])
    require(image['Id'] == facts['image_id'])
    owner = 'owned-cli-offline-' + str(uuid.uuid4())
    row = {'schema_version': 1, 'kind': 'offline-cli-metadata', 'destination': destination,
           'daemon': daemon(docker), 'owner': owner, 'labels': {**(image['Config'].get('Labels') or {}), 'proof.owner': owner},
           'image': facts['image_id'], 'id': None, 'state': 'intent',
           'inputs': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in [Path(__file__).resolve(), ROOT / 'scripts/native_cdp_allocation.py']}}
    row['inputs']['docs/verification/bitwarden-cli.yaml#existing_artifact_facts'] = hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    private._publish(filename, row, exclusive=True)  # Reservation and fsync precede create.
    try:
        args = ['create', '--name', owner, '--label', 'proof.owner=' + owner, '--network', 'none',
                '--user', '1000:1000', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--restart', 'no', '--log-driver', 'none', '--ulimit', 'core=0', '--ipc', 'private',
                '--memory', '256m', '--cpus', '1', '--pids-limit', '64', '--entrypoint', '/bin/sleep']
        for value in ENV:
            args.extend(['--env', value])
        for path, options in TMPFS.items():
            args.extend(['--tmpfs', path + ':' + options])
        created = docker(args + [facts['image_id'], '180'])
        require(created.returncode == 0)
        identifier = created.stdout.decode().strip()
        require(re.fullmatch(r'[0-9a-f]{64}', identifier))
        candidate = {**row, 'id': identifier}
        details = inspect(docker, identifier)
        validate(details, candidate)
        require(details['State']['Running'] is False and details['State']['Status'] == 'created'
                and row['daemon'] == daemon(docker))
        row.update(id=identifier, state='receipted')
        private._publish(filename, row)
        durable, details = attest(filename, docker)
        require(durable == row and details['State']['Status'] == 'created')
        row['state'] = 'started'
        private._publish(filename, row)
        require(docker(['start', identifier]).returncode == 0)
        def command(args):
            receipt, details = attest(filename, docker)
            require(receipt['state'] == 'started' and details['State']['Running'] is True)
            result = docker(['exec', identifier, '/usr/bin/env', '-i'] + ENV + args)
            require(result.returncode == 0)
            return result.stdout.decode().strip()
        require(command(['/usr/bin/sha256sum', facts['cli_path']]) == facts['cli_sha256'] + '  ' + facts['cli_path'])
        require(command([facts['cli_path'], '--version']) == facts['cli_version'])
        before = command([facts['cli_path'], 'config', 'server'])
        require(before == SERVER)
        command([facts['cli_path'], 'config', 'server', SERVER])
        after = command([facts['cli_path'], 'config', 'server'])
        require(after == before)
        raw = command(['/usr/bin/head', '-c', '1048577', '/data/data.json'])
        require(len(raw.encode()) <= 1048576)
        data = json.loads(raw)
        # This appdata is newly owned and has never received credentials or login.
        metadata = data.get('environmentUrls', {})
        require(isinstance(metadata, dict))
        private._publish(output / 'result.yaml', {'schema_version': 1, 'kind': 'offline-cli-metadata',
                         'cli_sha256': facts['cli_sha256'], 'cli_version': facts['cli_version'],
                         'server_before': before, 'server_after': after, 'environment_urls': metadata,
                         'environment_metadata_recognized': 'environmentUrls' in data,
                         'authentication_performed': False, 'credentials_supplied': False,
                         'network': 'none', 'online_ready': False}, exclusive=True)
    finally:
        require(cleanup(filename, docker))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ssh', required=True)
    args = parser.parse_args()
    try:
        qualify(args.ssh, ROOT / 'tmp/cli-offline-qualification', transport(args.ssh))
    except Exception:
        print('CLI_QUALIFICATION_REFUSED')
        return 1
    print('CLI_OFFLINE_METADATA_QUALIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

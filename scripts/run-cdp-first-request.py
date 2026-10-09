#!/usr/bin/env python3
"""Opt-in local Docker fixture: no endpoints, sources, credentials or shared mounts."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import uuid


IMAGE = 'sha256:11b6dc0eb079e10e625ff8de54af6018100289b51fa500e72196adfca8233df8'
PROFILE_SHA = 'cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849'
BASE = ['/usr/bin/docker', '--host', 'unix:///var/run/docker.sock']
ROOT = Path(__file__).resolve().parents[1]


def docker(args, timeout=20):
    return subprocess.run(BASE + args, env={'PATH': '/usr/bin:/bin'},
                          capture_output=True, timeout=timeout)


def publish(path, content):
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def fixture_archive():
    buffer = io.BytesIO()
    hashes = {}
    sources = [ROOT / ('collector/' + name) for name in [
        'lab/first-request.mjs', 'lab/restart-principal.mjs',
        'lab/capture-document.mjs', 'core.mjs',
        'capability-pipe.mjs', 'capability-ordering.mjs',
        'capability-bootstrap.mjs', 'capability-policy.mjs']]
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for path in sources:
            content = path.read_bytes()
            hashes[path.name] = hashlib.sha256(content).hexdigest()
            info = tarfile.TarInfo('proof/' + path.name)
            info.uid = info.gid = 1000
            info.mode = 0o400
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        dependency = ROOT / 'collector/node_modules/yaml'
        version = json.loads((dependency / 'package.json').read_text())['version']
        assert version == '2.9.1', 'FIXTURE_DEPENDENCY_PIN_MISMATCH'
        for path in sorted(dependency.rglob('*')):
            assert not path.is_symlink(), 'FIXTURE_DEPENDENCY_SYMLINK'
            if path.is_file():
                content = path.read_bytes()
                relative = 'proof/node_modules/yaml/' + str(path.relative_to(dependency))
                hashes[relative] = hashlib.sha256(content).hexdigest()
                info = tarfile.TarInfo(relative)
                info.uid = info.gid = 1000
                info.mode = 0o400
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue(), hashes


def run(mode, profile, output, archive, hashes):
    name = 'owned-cdp-first-request-' + uuid.uuid4().hex
    identifier = None
    receipt = {'mode': mode, 'image': IMAGE, 'profile_sha256': PROFILE_SHA,
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'source_sha256': hashes, 'cleanup_verified': False, 'browser_proven': False}
    try:
        created = docker(['create', '--name', name, '--label', 'proof.owner=' + name,
                          '--network', 'none', '--user', '1000:1000', '--memory', '768m',
                          '--cpus', '1', '--pids-limit', '256', '--shm-size', '128m',
                          '--security-opt', 'seccomp=' + str(profile), '--entrypoint', '/usr/bin/node',
                          IMAGE, '/home/fixture/proof/first-request.mjs', mode])
        assert created.returncode == 0, 'FIXTURE_CREATE_FAILED'
        identifier = created.stdout.decode().strip()
        details = json.loads(docker(['inspect', identifier]).stdout)[0]
        assert details['Id'] == identifier and details['Config']['Labels']['proof.owner'] == name
        assert details['HostConfig']['NetworkMode'] == 'none' and not details['Mounts']
        assert not details['HostConfig']['Privileged'] and not details['HostConfig']['CapAdd']
        assert details['Config']['User'] == '1000:1000'
        receipt.update(container=identifier, apparmor=details['AppArmorProfile'],
                       security_options=details['HostConfig']['SecurityOpt'])
        copied = subprocess.run(BASE + ['cp', '-', identifier + ':/home/fixture'], input=archive,
                                env={'PATH': '/usr/bin:/bin'}, capture_output=True, timeout=20)
        assert copied.returncode == 0, 'FIXTURE_COPY_FAILED'
        result = docker(['start', '-a', identifier], timeout=55)
        publish(output / (mode + '-stdout.bytes'), result.stdout[:1048576])
        publish(output / (mode + '-stderr.bytes'), result.stderr[:1048576])
        assert len(result.stdout) <= 1048576 and len(result.stderr) <= 1048576, 'FIXTURE_OUTPUT_LIMIT'
        assert result.returncode == 0, 'FIXTURE_FAILED'
        evidence = json.loads(result.stdout)
        assert evidence['mode'] == mode and evidence['passed'] and evidence['owned_browser_exit']
        assert evidence['browser_proven'] is False
        if mode.startswith('popup'):
            assert evidence['counts'].get('Target.attachedToTarget', 0) >= 2, 'POPUP_CONTROL_INCONCLUSIVE'
        receipt['evidence'] = evidence
    finally:
        if identifier:
            details = json.loads(docker(['inspect', identifier]).stdout)[0]
            assert details['Id'] == identifier and details['Config']['Labels']['proof.owner'] == name
            assert docker(['rm', '-f', identifier]).returncode == 0, 'FIXTURE_CLEANUP_FAILED'
        receipt['cleanup_verified'] = not docker(['ps', '-a', '--filter', 'name=^/' + name + '$',
                                                 '--format', '{{.ID}}']).stdout.strip()
        publish(output / (mode + '-receipt.json'), json.dumps(receipt, indent=2).encode())
    assert receipt['cleanup_verified'], 'FIXTURE_CLEANUP_UNVERIFIED'
    print(mode + ': PASS; exact owned cleanup verified; full qualification remains false', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True, help='Exact qualified Playwright seccomp file')
    parser.add_argument('--scenario', action='append', help='Optional fixed synthetic scenario subset')
    parser.add_argument('--output', type=Path, required=True, help='New private evidence directory')
    args = parser.parse_args()
    profile = args.profile.resolve()
    assert hashlib.sha256(profile.read_bytes()).hexdigest() == PROFILE_SHA, 'PROFILE_PIN_MISMATCH'
    image = json.loads(docker(['image', 'inspect', IMAGE]).stdout)[0]
    assert image['Id'] == IMAGE and image['Config']['Labels']['bd.cdp-capability'] == '415a78dfcc5444e3902473da5af2fd07'
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    archive, hashes = fixture_archive()
    modes = ['permitted', 'denied', 'negative', 'popup', 'popup-negative', 'frame', 'frame-negative', 'worker', 'worker-negative', 'shared-worker', 'shared-worker-negative', 'service-worker', 'service-worker-negative', 'redirect307', 'redirect307-negative', 'redirect308', 'redirect308-negative', 'second-auth', 'second-auth-negative', 'http-auth', 'concurrent', 'concurrent-negative', 'fsync-failure', 'browser-crash', 'pipe-loss', 'forced-stop', 'late-guard-negative', 'capture']
    selected = args.scenario or modes
    assert all(mode in modes for mode in selected) and len(set(selected)) == len(selected), 'FIXTURE_MODE_REJECTED'
    for mode in selected:
        run(mode, profile, args.output, archive, hashes)


if __name__ == '__main__':
    main()

"""Fixed private registry for owned synthetic-only Docker allocation.

No Docker calls are made by this module; its caller supplies bounded operations.
Never use resource discovery to grant start or cleanup authority.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid

import yaml


ENDPOINT = 'unix:///var/run/docker.sock'
IMAGE = 'sha256:05f2836ccd6a6b66a18e21e9d940e36336b7d40e353a3e97b05b01df0654f721'
PROFILE_SHA = 'cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849'
_HANDLES = {}
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z')
_LIMIT = 1048576


def require(condition, code='ALLOCATION_REJECTED'):
    if not condition:
        raise RuntimeError(code)


def _sync_directory(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _private_directory(directory, create=False):
    current = Path(directory.anchor)
    for part in directory.parts[1:]:
        current /= part
        if not current.exists() and not current.is_symlink():
            require(create, 'ALLOCATION_PATH_MISSING')
            current.mkdir(mode=0o700)
            _sync_directory(current.parent)
        require(not current.is_symlink() and current.is_dir(), 'ALLOCATION_PATH_INVALID')
    stat = directory.stat()
    require(stat.st_uid == os.getuid() and stat.st_mode & 0o077 == 0, 'ALLOCATION_PERMISSIONS_INVALID')


def _read(filename):
    _private_directory(filename.parent)
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid()
                and info.st_mode & 0o077 == 0 and info.st_size <= _LIMIT, 'ALLOCATION_FILE_INVALID')
        raw = os.read(fd, _LIMIT + 1)
        require(len(raw) == info.st_size and len(raw) <= _LIMIT, 'ALLOCATION_FILE_INVALID')
        decoded = raw.decode('utf-8')
        for token in yaml.scan(decoded):
            require(not isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)), 'ALLOCATION_SCHEMA_INVALID')
        def unique(node, depth=0):
            require(depth <= 16, 'ALLOCATION_SCHEMA_INVALID')
            if isinstance(node, yaml.nodes.MappingNode):
                keys = [key.value for key, _ in node.value if isinstance(key, yaml.nodes.ScalarNode)
                        and key.tag == 'tag:yaml.org,2002:str']
                require(len(keys) == len(node.value) and len(keys) == len(set(keys)), 'ALLOCATION_SCHEMA_INVALID')
                for _, value in node.value:
                    unique(value, depth + 1)
            elif isinstance(node, yaml.nodes.SequenceNode):
                for value in node.value:
                    unique(value, depth + 1)
        unique(yaml.compose(decoded, Loader=yaml.SafeLoader))
        return yaml.safe_load(decoded)
    finally:
        os.close(fd)


def _publish(filename, value, exclusive=False):
    _private_directory(filename.parent)
    if filename.exists() or filename.is_symlink():
        require(not exclusive, 'ALLOCATION_ALREADY_INITIALIZED')
        _read(filename)
    raw = yaml.safe_dump(value, sort_keys=True).encode()
    require(len(raw) <= _LIMIT, 'ALLOCATION_LIMIT')
    temporary = filename.parent / ('.' + str(uuid.uuid4()) + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            os.link(temporary, filename)
            temporary.unlink()
        else:
            os.replace(temporary, filename)
        _sync_directory(filename.parent)
    except BaseException:
        # Retain incomplete publication and the registry lock for manual recovery.
        raise


def _root():
    return Path.home() / '.local/state/ghostfolio-boursedirect-sync/synthetic-cdp/allocations'


def initialize_registry(daemon):
    require(isinstance(daemon, str) and 0 < len(daemon) <= 256)
    root = _root()
    require(not root.exists() and not root.is_symlink(), 'ALLOCATION_ALREADY_INITIALIZED')
    _private_directory(root, create=True)
    _publish(root / 'registry.yaml', {'schema_version': 1, 'installation_id': str(uuid.uuid4()),
                                     'endpoint': ENDPOINT, 'daemon': daemon, 'allocations': {}}, exclusive=True)


def _validate(state):
    require(isinstance(state, dict) and set(state) == {'schema_version', 'installation_id', 'endpoint', 'daemon', 'allocations'}, 'ALLOCATION_SCHEMA_INVALID')
    require(type(state['schema_version']) is int and state['schema_version'] == 1
            and isinstance(state['installation_id'], str) and _UUID.fullmatch(state['installation_id'])
            and state['endpoint'] == ENDPOINT and isinstance(state['daemon'], str) and 0 < len(state['daemon']) <= 256,
            'ALLOCATION_SCHEMA_INVALID')
    require(isinstance(state['allocations'], dict) and len(state['allocations']) <= 1000, 'ALLOCATION_SCHEMA_INVALID')
    for allocation, row in state['allocations'].items():
        require(isinstance(allocation, str) and _UUID.fullmatch(allocation)
                and isinstance(row, dict) and set(row) == {'state', 'owner', 'spec', 'container', 'receipt'}, 'ALLOCATION_SCHEMA_INVALID')
        require(row['state'] in ('intent', 'receipted', 'started', 'absence_verified')
                and row['owner'] == 'owned-native-cdp-' + allocation, 'ALLOCATION_SCHEMA_INVALID')
        _validate_spec(row['spec'])
        require(row['spec']['arguments'][2] == allocation, 'ALLOCATION_SCHEMA_INVALID')
        if row['state'] == 'intent':
            require(row['container'] is None and row['receipt'] is None, 'ALLOCATION_SCHEMA_INVALID')
        else:
            require(isinstance(row['container'], str) and _HASH.fullmatch(row['container'])
                    and isinstance(row['receipt'], dict) and set(row['receipt']) == {'daemon', 'configuration_sha256'}
                    and row['receipt']['daemon'] == state['daemon']
                    and row['receipt']['configuration_sha256'] == _digest(row['spec']), 'ALLOCATION_SCHEMA_INVALID')
    return state


def _validate_spec(spec):
    require(isinstance(spec, dict) and set(spec) == {'image', 'profile_sha256', 'sources', 'entrypoint', 'arguments'}, 'ALLOCATION_SCHEMA_INVALID')
    require(spec['image'] == IMAGE and spec['profile_sha256'] == PROFILE_SHA
            and spec['entrypoint'] == '/usr/bin/node'
            and isinstance(spec['arguments'], list) and len(spec['arguments']) == 3
            and spec['arguments'][0] == '/home/fixture/proof/lab/native-runtime.mjs'
            and isinstance(spec['arguments'][1], str) and re.fullmatch(r'[a-z][a-z0-9-]{0,40}', spec['arguments'][1])
            and isinstance(spec['arguments'][2], str) and _UUID.fullmatch(spec['arguments'][2]), 'ALLOCATION_SCHEMA_INVALID')
    require(isinstance(spec['sources'], dict) and 0 < len(spec['sources']) <= 1000
            and all(isinstance(k, str) and 0 < len(k) <= 512 and isinstance(v, str) and _HASH.fullmatch(v)
                    for k, v in spec['sources'].items()), 'ALLOCATION_SCHEMA_INVALID')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def acquire_registry():
    root = _root()
    _private_directory(root)
    lock = root / 'lock'
    try:
        lock.mkdir(mode=0o700)
    except OSError:
        raise RuntimeError('ALLOCATION_LOCKED') from None
    _sync_directory(root)
    handle = str(uuid.uuid4())
    _HANDLES[handle] = {'root': root, 'lock': lock, 'closed': False, 'poisoned': False}
    try:
        _validate(_read(root / 'registry.yaml'))
    except BaseException:
        _HANDLES[handle]['poisoned'] = True
        release_registry(handle)
        raise
    return handle


def _owned(handle):
    value = _HANDLES.get(handle)
    require(value is not None and not value['closed'] and not value['poisoned'], 'ALLOCATION_HANDLE_CLOSED')
    return value


def release_registry(handle):
    value = _HANDLES.get(handle)
    require(value is not None, 'ALLOCATION_HANDLE_CLOSED')
    if value['closed']:
        return
    value['closed'] = True
    if value['poisoned']:
        return
    value['lock'].rmdir()
    _sync_directory(value['root'])


def _state(handle, daemon):
    value = _owned(handle)
    state = _validate(_read(value['root'] / 'registry.yaml'))
    require(daemon == state['daemon'], 'ALLOCATION_DAEMON_MISMATCH')
    return value, state


def _save(value, state):
    value['poisoned'] = True
    _publish(value['root'] / 'registry.yaml', state)
    value['poisoned'] = False


def begin_allocation(handle, daemon, allocation, spec):
    value, state = _state(handle, daemon)
    _validate_spec(spec)
    require(isinstance(allocation, str) and _UUID.fullmatch(allocation)
            and spec['arguments'][2] == allocation and allocation not in state['allocations'])
    require(len(state['allocations']) < 1000, 'ALLOCATION_LIMIT')
    require(all(row['state'] == 'absence_verified' for row in state['allocations'].values()), 'ALLOCATION_UNRESOLVED')
    state['allocations'][allocation] = {'state': 'intent', 'owner': 'owned-native-cdp-' + allocation,
                                      'spec': json.loads(json.dumps(spec)), 'container': None, 'receipt': None}
    _save(value, state)
    return state['allocations'][allocation]['owner']


def _configuration(details, row, identifier):
    require(isinstance(details, dict) and details.get('Id') == identifier, 'ALLOCATION_OWNER_MISMATCH')
    config, host = details.get('Config', {}), details.get('HostConfig', {})
    spec = row['spec']
    require(config.get('Labels', {}).get('proof.owner') == row['owner']
            and config.get('Labels', {}).get('proof.allocation') == spec['arguments'][2]
            and details.get('Image') == spec['image'] and config.get('User') == '1000:1000'
            and config.get('Entrypoint') == [spec['entrypoint']] and config.get('Cmd') == spec['arguments']
            and isinstance(config.get('Env'), list) and len(config['Env']) == 2
            and set(config['Env']) == {'HOME=/home/fixture', 'PATH=/usr/bin:/bin'}
            and host.get('NetworkMode') == 'none' and details.get('Mounts') == []
            and host.get('Privileged') is False and not host.get('CapAdd')
            and host.get('RestartPolicy') == {'Name': 'no', 'MaximumRetryCount': 0}
            and host.get('PidMode', '') == '' and host.get('IpcMode') == 'private'
            and host.get('Memory') == 805306368 and host.get('NanoCpus') == 1000000000
            and host.get('PidsLimit') == 256 and host.get('ShmSize') == 134217728,
            'ALLOCATION_OWNER_MISMATCH')
    options = host.get('SecurityOpt')
    require(isinstance(options, list) and len(options) == 1 and options[0].startswith('seccomp='), 'ALLOCATION_OWNER_MISMATCH')
    # Docker inspection expands the profile to JSON, not a trustworthy input path.
    try:
        profile = json.loads(options[0].split('=', 1)[1])
    except (ValueError, TypeError):
        raise RuntimeError('ALLOCATION_OWNER_MISMATCH') from None
    return profile


def record_receipt(handle, daemon, allocation, identifier, details, profile):
    value, state = _state(handle, daemon)
    require(isinstance(identifier, str) and _HASH.fullmatch(identifier), 'ALLOCATION_ID_INVALID')
    row = state['allocations'].get(allocation)
    require(row is not None and row['state'] == 'intent')
    require(hashlib.sha256(profile).hexdigest() == PROFILE_SHA, 'ALLOCATION_PROFILE_MISMATCH')
    require(_configuration(details, row, identifier) == json.loads(profile), 'ALLOCATION_PROFILE_MISMATCH')
    require(details.get('State', {}).get('Status') == 'created' and details['State'].get('Running') is False, 'ALLOCATION_NOT_STOPPED')
    row.update(state='receipted', container=identifier,
               receipt={'daemon': daemon, 'configuration_sha256': _digest(row['spec'])})
    _save(value, state)


def before_start(handle, daemon, allocation, inspect, profile):
    value, state = _state(handle, daemon)
    row = state['allocations'].get(allocation)
    require(row is not None and row['state'] == 'receipted', 'ALLOCATION_RECEIPT_REQUIRED')
    require(hashlib.sha256(profile).hexdigest() == PROFILE_SHA, 'ALLOCATION_PROFILE_MISMATCH')
    details = inspect(row['container'])
    require(_configuration(details, row, row['container']) == json.loads(profile), 'ALLOCATION_PROFILE_MISMATCH')
    require(details.get('State', {}).get('Status') == 'created' and details['State'].get('Running') is False, 'ALLOCATION_NOT_STOPPED')
    row['state'] = 'started'
    _save(value, state)  # A failed/uncertain start remains explicitly unfinished.
    return row['container']


def cleanup_allocation(handle, daemon, allocation, inspect, remove, absent, profile):
    value, state = _state(handle, daemon)
    row = state['allocations'].get(allocation)
    require(row is not None and row['state'] in ('receipted', 'started'), 'ALLOCATION_RECEIPT_REQUIRED')
    identifier = row['container']
    require(hashlib.sha256(profile).hexdigest() == PROFILE_SHA, 'ALLOCATION_PROFILE_MISMATCH')
    require(_configuration(inspect(identifier), row, identifier) == json.loads(profile), 'ALLOCATION_PROFILE_MISMATCH')
    require(remove(identifier) is True, 'ALLOCATION_REMOVE_UNVERIFIED')
    require(absent(identifier) is True, 'ALLOCATION_ABSENCE_UNVERIFIED')
    row['state'] = 'absence_verified'
    _save(value, state)
    return {'cleanup_verified': True, 'container': identifier,
            'online_ready': False, 'browser_proven': False, 'import_ready': False}

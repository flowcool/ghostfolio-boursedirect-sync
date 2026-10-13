"""Community one-shot acquisition and saved-input preview; never financial writes."""
import base64
import fcntl
import http.client
import ipaddress
import json
import os
import platform
from pathlib import Path
import select
import selectors
import signal
import stat
import subprocess
import sys
import time
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import boursedirect_to_ghostfolio as importer
import source_qualification as source
from source_vault_inspection import read_frame, write_frame

MAX_BYTES = 8 * 1024 * 1024


def require(condition, code='COMMUNITY_CONNECT_REFUSED'):
    if not condition:
        raise RuntimeError(code)


def ghostfolio_origin(origin):
    """HTTPS by default; exact operator-approved private Docker service only."""
    if origin == 'http://ghostfolio:3333':
        return 'ghostfolio', 3333, False
    host, port = importer.validated_ghost_origin(origin)
    return host, port, True


def ghostfolio_snapshot(origin, security_token, request=None):
    """One anonymous token exchange and two fixed GETs; no redirect or retry."""
    host, port, secure = ghostfolio_origin(origin)
    require(isinstance(security_token, str) and 0 < len(security_token) <= 4096
            and security_token.isascii() and not any(ord(c) < 33 or ord(c) == 127 for c in security_token),
            'GHOSTFOLIO_ACCESS_INVALID')

    def send(method, path, body, headers):
        connection = (http.client.HTTPSConnection if secure else http.client.HTTPConnection)(host, port, timeout=30)
        try:
            if not secure:
                connection.connect()
                peer = ipaddress.ip_address(connection.sock.getpeername()[0])
                require(any(peer in ipaddress.ip_network(network) for network in
                            ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')),
                        'GHOSTFOLIO_ACCESS_REFUSED')
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            require(200 <= response.status < 300 if method == 'POST' else response.status == 200,
                    'GHOSTFOLIO_ACCESS_REFUSED')
            require(response.getheader('Content-Type', '').split(';')[0].strip().lower() == 'application/json',
                    'GHOSTFOLIO_ACCESS_REFUSED')
            raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, 'GHOSTFOLIO_RESPONSE_TOO_LARGE')
            return raw
        finally:
            connection.close()

    send_request = send if request is None else request
    exchange = json.loads(send_request('POST', '/api/v1/auth/anonymous',
        json.dumps({'accessToken': security_token}).encode(), {'Content-Type': 'application/json'}),
        object_pairs_hook=importer.unique_json_object)
    token = exchange.get('authToken') if isinstance(exchange, dict) else None
    require(isinstance(token, str) and 0 < len(token) <= 16384 and token.isascii()
            and not any(ord(c) < 33 or ord(c) == 127 for c in token), 'GHOSTFOLIO_ACCESS_REFUSED')
    headers = {'Authorization': 'Bearer ' + token}
    accounts_raw = send_request('GET', '/api/v1/account', None, headers)
    activities_raw = send_request('GET', '/api/v1/activities', None, headers)
    accounts = json.loads(accounts_raw, object_pairs_hook=importer.unique_json_object).get('accounts')
    require(isinstance(accounts, list) and 0 < len(accounts) <= 256, 'GHOSTFOLIO_ACCOUNTS_INVALID')
    ids = []
    for row in accounts:
        require(isinstance(row, dict) and isinstance(row.get('id'), str) and isinstance(row.get('name'), str)
                and all(0 < len(row[k]) <= 256 and not any(ord(c) < 32 or ord(c) == 127 for c in row[k])
                        for k in ('id', 'name')), 'GHOSTFOLIO_ACCOUNTS_INVALID')
        ids.append(row['id'])
    require(len(set(ids)) == len(ids), 'GHOSTFOLIO_ACCOUNTS_INVALID')
    importer.parse_remote_activity_snapshot(activities_raw)
    return accounts, accounts_raw, activities_raw


def choose(options, title, selected=None, timeout=None):
    values = [row['value'] for row in options]
    if selected:
        require(values.count(selected) == 1, 'CONFIGURED_ACCOUNT_UNAVAILABLE')
        return selected
    require(sys.stdin.isatty(), 'ACCOUNT_SELECTION_REQUIRES_TERMINAL')
    print(title, flush=True)
    for number, row in enumerate(options, 1):
        print(f"  {number}. {row['label']}", flush=True)
    print('Choose a number: ', end='', flush=True)
    if timeout is not None and not select.select([sys.stdin], [], [], timeout)[0]:
        return None
    answer = sys.stdin.readline().strip()
    require(answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(options), 'ACCOUNT_SELECTION_INVALID')
    return options[int(answer) - 1]['value']


def reconcile_binding(saved, origin, source_ref, target_id):
    if saved is None:
        return None
    require(isinstance(saved, dict) and set(saved) == {'schema_version', 'ghostfolio_origin', 'account'}
            and type(saved['schema_version']) is int and saved['schema_version'] == 1,
            'ACCOUNT_BINDING_INVALID')
    account = source.source_account_binding(saved['account'])
    require(saved['ghostfolio_origin'] == origin
            and (not source_ref or source_ref == account['source_account_ref'])
            and (not target_id or target_id == account['target_account_id']), 'ACCOUNT_BINDING_CONFLICT')
    return account


def wait_proxy_ready(proxy, timeout=15):
    """The owned proxy emits its fixed signal only after binding the listener."""
    deadline = time.monotonic() + timeout
    pending = b''
    while time.monotonic() < deadline:
        require(proxy.poll() is None, 'SOURCE_PROXY_UNAVAILABLE')
        if select.select([proxy.stdout], [], [], min(0.1, max(0, deadline - time.monotonic())))[0]:
            pending += os.read(proxy.stdout.fileno(), 32)
            require(pending and b'SOURCE_PROXY_READY\n'.startswith(pending), 'SOURCE_PROXY_UNAVAILABLE')
            if pending == b'SOURCE_PROXY_READY\n':
                return
    raise RuntimeError('SOURCE_PROXY_UNAVAILABLE')


def broker_lock(root):
    """One lock on the common state volume, shared by every broker service."""
    descriptor = os.open(root / 'connect.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and info.st_nlink == 1 and info.st_mode & 0o077 == 0, 'BROKER_STATE_INVALID')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('BROKER_RUN_LOCKED') from None
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def close_proxy(proxy):
    if proxy is not None:
        if proxy.poll() is None:
            proxy.terminate()
            proxy.wait(timeout=10)
        proxy.stdout.close()


def broker_login_ready(root):
    result = subprocess.run(['/usr/local/bin/node', str(ROOT / 'native-source-command.mjs'),
        '--check-login-state'], env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(root)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    require(result.returncode == 0, 'BROKER_LOGIN_UNRESOLVED')


def discovery_receipt(root):
    path = root / 'discovery.yaml'
    if not path.exists() and not path.is_symlink():
        return None
    saved = source.replay.private._read(path)
    require(isinstance(saved, dict) and set(saved) == {'schema_version', 'state', 'run_id', 'accounts'}
        and type(saved['schema_version']) is int and saved['schema_version'] == 1
        and source.re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', saved['run_id'])
        and saved['state'] in ('started', 'completed') and isinstance(saved['accounts'], dict),
        'BROKER_DISCOVERY_INVALID')
    if saved['state'] == 'started':
        raise RuntimeError('BROKER_DISCOVERY_UNRESOLVED')
    require(0 < len(saved['accounts']) <= 256 and all(isinstance(ref, str)
        and source.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63} (?:PEA|PEA-PME)', ref)
        and wrapper == ref.split(' ', 1)[1] for ref, wrapper in saved['accounts'].items()),
        'BROKER_DISCOVERY_INVALID')
    return saved


def print_discovery(saved, reused):
    for ref, wrapper in saved['accounts'].items():
        print(json.dumps({'code': 'BD_SOURCE_ACCOUNT_OPTION', 'BD_SOURCE_ACCOUNT_REF': ref,
            'wrapper': wrapper, 'configuration': 'BD_SOURCE_ACCOUNT_REF=' + repr(ref)}), flush=True)
    print(json.dumps({'code': 'SOURCE_ACCOUNT_CONFIGURATION_REQUIRED', 'discovery_reused': reused,
        'broker_attempts': 0 if reused else 1, 'imported': 0, 'financial_writes': 0}), flush=True)


def account_binding_path(root, source_ref):
    directory = root / 'accounts'
    importer.private_directory(directory)
    return directory / (source.digest(source_ref.encode()) + '.yaml')


def saved_account_binding(root, path, source_ref):
    if path.exists() or path.is_symlink():
        return importer.read_keyed_yaml(path, root, MAX_BYTES)
    legacy = root / 'community-binding.yaml'
    if legacy.exists() or legacy.is_symlink():
        saved = importer.read_keyed_yaml(legacy, root, MAX_BYTES)
        require(isinstance(saved, dict) and isinstance(saved.get('account'), dict), 'ACCOUNT_BINDING_INVALID')
        if saved['account'].get('source_account_ref') == source_ref:
            return saved
    return None


def acquire(run, as_of, existing, source_ref, target_id, vault_env, select_source=None, origin=None,
            discovery_only=False, binding_path=None):
    """Compose a local owned browser worker with the existing inert planner."""
    sequence = 0
    document = None
    consumed = set()
    candidate = existing
    binding_saved = False

    def select_account(available):
        nonlocal candidate
        if candidate is None:
            chosen = select_source(available) if select_source else choose(
                [{'value': value, 'label': value} for value in available], 'Bourse Direct account', source_ref, timeout=20)
            if chosen is None:
                return None
            candidate = source.source_account_binding({'source_account_ref': chosen,
                'account_key': str(uuid.uuid4()), 'target_account_id': target_id})
        return candidate

    state = source.planner(notice_as_of=as_of, account=existing,
        choose_account=select_account if existing is None and not discovery_only else None,
        discovery_only=discovery_only)
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': '/state', **vault_env}
    process = subprocess.Popen(['/usr/local/bin/node', str(ROOT / 'native-source-command.mjs')],
        env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
    selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
    write_frame(process, {'action': 'connect'})
    deadline = time.monotonic() + 620
    try:
        for _ in range(4096):
            row = read_frame(process, selector, b'', deadline)
            action = row.get('action')
            result = True
            if action == 'reserve_enrollment':
                require(set(row) == {'action', 'principal'} and isinstance(row['principal'], str)
                        and source.re.fullmatch('[a-f0-9]{64}', row['principal']))
                source.replay.private._publish(run / 'enrollment-intent.yaml', row, exclusive=True)
            elif action == 'retain':
                require(set(row) == {'action', 'observation'} and isinstance(row['observation'], dict))
                sequence += 1
                source.replay.private._publish(run / f'request-{sequence}.yaml', row['observation'], exclusive=True)
            elif action == 'consume_read':
                require(set(row) == {'action', 'grant'} and isinstance(row['grant'], dict)
                        and isinstance(row['grant'].get('grant'), str) and 0 < len(row['grant']['grant']) <= 256)
                grant = row['grant']
                require(grant['grant'] not in consumed)
                source.replay.private._publish(run / f'grant-{len(consumed)}.yaml', grant, exclusive=True)
                consumed.add(grant['grant'])
            elif action == 'document_begin':
                expected = state['current']
                require(document is None and (expected is None
                        or row['url'] == expected['url'] and row['role'] == expected['role']))
                source.source_url(row['url'], row['url'])
                document = {**row, 'body': bytearray()}
            elif action == 'document_chunk':
                require(document is not None)
                document['body'].extend(base64.b64decode(row['body'], validate=True))
                require(len(document['body']) <= 1048576)
            elif action == 'document_end':
                require(document is not None)
                state['captures'] += 1
                require(state['captures'] <= 256)
                raw = bytes(document.pop('body'))
                name = f"document-{state['captures']}"
                importer.atomic_private_bytes(run / (name + '.html'), raw)
                current = state['current'] or {}
                source.replay.private._publish(run / (name + '.yaml'), {**document, 'sha256': source.digest(raw),
                    'path': name + '.html', 'original_response_bytes': False,
                    'account_wrapper': current.get('account'),
                    'broker_account_id': state['account_ids'].get(current.get('account'))}, exclusive=True)
                source.discover(state, document['url'], raw, document['role'])
                document = None
            elif action == 'next_document':
                result = source.next_document(state)
                if result.get('accounts_verified') and not binding_saved and not discovery_only:
                    require(candidate is not None)
                    source.replay.private._publish(binding_path or Path('/state/community-binding.yaml'), {
                        'schema_version': 1, 'ghostfolio_origin': origin or os.environ['GHOSTFOLIO_ORIGIN'], 'account': candidate})
                    binding_saved = True
            elif action == 'complete':
                if not discovery_only:
                    require(source.notice_coverage(state)['complete'], 'NOTICE_WINDOW_INCOMPLETE')
                require(row.get('accounts_verified') is True and row.get('session_logged_out') is True
                        and row.get('browser_exit_verified') is True and row.get('totp_requests') == 1
                        and row.get('documents') == source.next_document(state)['documents']
                        and row['documents']['complete'] is True and process.wait(timeout=20) == 0)
                require(process.stdout.read(1) == b'' and process.stderr.read(1) == b''
                        and (binding_saved or discovery_only))
                source.replay.private._publish(run / 'qualification.yaml', {**row, 'schema_version': 1,
                    'state': 'owned_session_closed', 'captures': state['captures'], 'accounts': state['accounts'],
                    'account_ids': state['account_ids'], 'verified_wrappers': sorted(state['verified']),
                    'account_binding': candidate, 'notice_window': state['notice_window'],
                    **({'notice_coverage': source.notice_coverage(state)} if not discovery_only else {}),
                    **({'discovered_accounts': state['discovered_accounts']} if discovery_only else {})}, exclusive=True)
                return (state['discovered_accounts'] if discovery_only else candidate), row['documents']
            else:
                raise RuntimeError('SOURCE_CONNECT_REFUSED')
            write_frame(process, {'result': result})
        raise RuntimeError('SOURCE_CONNECT_REFUSED')
    finally:
        selector.close()
        if process.poll() is None:
            process.stdin.close()
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)


def connect():
    os.umask(0o077)
    root = Path('/state')
    source.replay.private._private_directory(root)
    origin = os.environ.get('GHOSTFOLIO_ORIGIN')
    ghostfolio_origin(origin)
    source_ref = os.environ.get('BD_SOURCE_ACCOUNT_REF', '')
    target_id = os.environ.get('GHOSTFOLIO_ACCOUNT_ID', '')
    if source_ref:
        require(source.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63} (?:PEA|PEA-PME)', source_ref), 'ACCOUNT_BINDING_INVALID')
    mappings_path = Path('/config/mappings.yaml')
    mappings_raw = importer.read_local_bytes(mappings_path, Path('/config'), MAX_BYTES) if mappings_path.exists() or mappings_path.is_symlink() else b'{}'
    require(len(mappings_raw) <= MAX_BYTES, 'COMMUNITY_CONFIGURATION_INVALID')
    mappings = importer.parse_keyed_yaml(mappings_raw)
    require(isinstance(mappings, dict), 'COMMUNITY_CONFIGURATION_INVALID')
    binding_path = root / 'community-binding.yaml'
    saved = source.replay.private._read(binding_path) if binding_path.exists() or binding_path.is_symlink() else None
    existing = reconcile_binding(saved, origin, source_ref, target_id)
    require(existing is not None or source_ref and target_id or sys.stdin.isatty(), 'ACCOUNT_SELECTION_REQUIRES_TERMINAL')
    vault_env = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith(('BW_', 'BD_'))}
    token = os.environ.pop('GHOSTFOLIO_SECURITY_TOKEN', None)
    lock = broker_lock(root)
    proxy = None
    try:
        broker_login_ready(root)
        accounts, accounts_raw, activities_raw = ghostfolio_snapshot(origin, token)
        token = None
        target_id = choose([{'value': row['id'], 'label': row['name']} for row in accounts],
            'Ghostfolio destination account', existing['target_account_id'] if existing else target_id)
        run = root / 'runs' / str(uuid.uuid4())
        source.replay.private._private_directory(run, create=True)
        importer.atomic_private_bytes(run / 'accounts.json', accounts_raw)
        importer.atomic_private_bytes(run / 'activities.json', activities_raw)
        as_of = importer.daily_preview_today()
        source.replay.private._publish(run / 'attempt.yaml', {'schema_version': 1, 'state': 'started', 'as_of': as_of}, exclusive=True)
        proxy = subprocess.Popen(['/usr/bin/python3', '-I', str(ROOT / 'collector/vault-egress.py'), '--broker-inspection', '--ready'],
            env={'PATH': '/usr/bin:/bin'}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        wait_proxy_ready(proxy)
        account, documents = acquire(run, as_of, existing, source_ref, target_id, vault_env)
        relative = str(run.relative_to(root))
        configuration = {'schema_version': 1, 'source_mode': 'notices', 'account': account, 'mappings': mappings,
            'snapshot': relative + '/activities.json', 'acquisition_runs': {'current': relative}}
        raw = yaml.safe_dump(configuration).encode()
        config_path = run / 'preview.yaml'
        importer.atomic_private_bytes(config_path, raw)
        os.chdir(root)
        summary = importer.preview_local_notices(configuration, config_path, raw, root, as_of, MAX_BYTES, 16)
        print(json.dumps({'code': 'COMMUNITY_DRY_RUN_COMPLETED', 'contract_notes': documents['contract_notes'],
            **summary, 'report': 'outputs/daily-notices-' + account['account_key'] + '.yaml'}), flush=True)
        return 2 if summary['unresolved_exceptions'] else 0
    finally:
        token = None
        if proxy is not None and proxy.poll() is None:
            proxy.terminate()
            proxy.wait(timeout=10)
        if proxy is not None:
            proxy.stdout.close()
        os.close(lock)


def main():
    try:
        if sys.argv[1:] == ['inspect']:
            os.environ.pop('GHOSTFOLIO_SECURITY_TOKEN', None)
            os.execv('/usr/local/bin/node', ['/usr/local/bin/node', str(ROOT / 'native-vault-command.mjs'), 'inspect'])
        require(sys.argv[1:] == ['connect'], 'COMMUNITY_COMMAND_INVALID')
        require(platform.machine() == 'x86_64', 'COMMUNITY_ARCH_UNSUPPORTED')
        return connect()
    except Exception as error:
        code = str(error)
        allowed = {'GHOSTFOLIO_ACCESS_INVALID', 'GHOSTFOLIO_ACCESS_REFUSED', 'GHOSTFOLIO_RESPONSE_TOO_LARGE',
            'GHOSTFOLIO_ACCOUNTS_INVALID', 'CONFIGURED_ACCOUNT_UNAVAILABLE', 'ACCOUNT_SELECTION_REQUIRES_TERMINAL',
            'ACCOUNT_SELECTION_INVALID', 'ACCOUNT_BINDING_INVALID', 'ACCOUNT_BINDING_CONFLICT',
            'SOURCE_CONNECT_REFUSED', 'SOURCE_PROXY_UNAVAILABLE', 'COMMUNITY_COMMAND_INVALID', 'COMMUNITY_ARCH_UNSUPPORTED',
            'COMMUNITY_CONFIGURATION_INVALID', 'INVALID_GHOST_ORIGIN'}
        print(json.dumps({'code': code if code in allowed else 'COMMUNITY_CONNECT_REFUSED', 'import_ready': False}), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())

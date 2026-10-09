"""Opt-in owned local Docker acceptance lab; never a production dispatcher."""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
import uuid

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
import boursedirect_to_ghostfolio as bd

IMAGES = {
    'app': 'ghostfolio/ghostfolio@sha256:7c925671dba267cc2175195f064b42b9733f3ea170a21db488b7d2be3319e088',
    'pg': 'postgres@sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81',
    'redis': 'redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499',
}
RUN = {}
NAME = ''
port = None
accounts = {}
MAX_RESPONSE = 1048576
ENV_KEYS = ('POSTGRES_PASSWORD', 'POSTGRES_DB', 'POSTGRES_USER', 'DATABASE_URL',
            'REDIS_HOST', 'REDIS_PORT', 'ACCESS_TOKEN_SALT', 'JWT_SECRET_KEY',
            'TZ', 'NODE_ENV', 'ENABLE_FEATURE_TELEMETRY')


def fail(code):
    raise RuntimeError(code)


def emit(event, **values):
    # Intermediate milestones are durable private data, never overall success.
    RUN['events'].append({'event': event, **values})
    save_manifest()


def save_manifest():
    bd.atomic_private_yaml(RUN['root'] / 'manifest.yaml', {
        'schema_version': 1, 'namespace': NAME, 'resources': RUN['resources'],
        'events': RUN['events'], 'creation_uncertain': RUN['creation_uncertain']})


def docker(*args, env_keys=()):
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin'}
    environment.update({key: os.environ[key] for key in env_keys if key in ENV_KEYS})
    command = ['/usr/bin/docker', '--config', str(RUN['root'] / 'docker-config'),
               '--host', 'unix:///var/run/docker.sock', *args]
    try:
        result = subprocess.run(command, env=environment, capture_output=True,
                                text=True, timeout=90)
    except subprocess.TimeoutExpired:
        fail('LAB_DOCKER_TIMEOUT')
    except OSError:
        fail('LAB_DOCKER_UNAVAILABLE')
    if result.returncode or len(result.stdout) > MAX_RESPONSE:
        fail('LAB_DOCKER_FAILED')
    return result.stdout.strip()


def query_resource(kind, name):
    args = ('container', 'ls', '-a', '--no-trunc') if kind == 'container' else ('network', 'ls', '--no-trunc')
    raw = docker(*args, '--format', '{{.ID}} {{.Name}}' if kind == 'network' else '{{.ID}} {{.Names}}')
    matches = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) != 2:
            fail('LAB_RESOURCE_LIST_INVALID')
        if parts[1] == name:
            matches.append(parts[0])
    if len(matches) > 1:
        fail('LAB_RESOURCE_NAME_CONFLICT')
    return matches[0] if matches else None


def owned_resource(resource):
    identifier = query_resource(resource['kind'], resource['name'])
    if identifier is None:
        return None
    template = '{"id":{{json .Id}},"name":{{json .Name}},"labels":{{json .Labels}}}'
    if resource['kind'] == 'container':
        template = ('{"id":{{json .Id}},"name":{{json .Name}},"labels":{{json .Config.Labels}},'
                    '"image":{{json .Image}},"networks":{{json .NetworkSettings.Networks}},'
                    '"ports":{{json .NetworkSettings.Ports}},"running":{{json .State.Running}}}')
    try:
        data = json.loads(docker(resource['kind'], 'inspect', identifier, '--format', template))
    except ValueError:
        fail('LAB_RESOURCE_INSPECTION_INVALID')
    if (not isinstance(data, dict) or data.get('id') != identifier
            or data.get('name', '').lstrip('/') != resource['name']
            or not isinstance(data.get('labels'), dict)
            or data['labels'].get('bd.acceptance-lab') != NAME
            or resource.get('id') not in (None, identifier)):
        fail('LAB_RESOURCE_OWNER_MISMATCH')
    return data


def create_resource(kind, name, args, env_keys=()):
    resource = {'kind': kind, 'name': name, 'id': None}
    if query_resource(kind, name) is not None:
        fail('LAB_RESOURCE_NAME_CONFLICT')
    RUN['resources'].append(resource)
    save_manifest()  # Attempt recorded before daemon mutation, including timeout.
    try:
        identifier = docker(*args, env_keys=env_keys)
        if not re.fullmatch(r'[0-9a-f]{64}', identifier):
            fail('LAB_RESOURCE_ID_INVALID')
        resource['id'] = identifier
        data = owned_resource(resource)
        if data is None:
            fail('LAB_RESOURCE_CREATION_UNVERIFIED')
        if kind == 'container':
            image_kind = name.removeprefix(NAME + '-')
            if (data.get('image') != RUN['image_ids'][image_kind]
                    or set(data.get('networks', {})) != {NAME}
                    or data['networks'][NAME].get('NetworkID') != RUN['network']['id']):
                fail('LAB_CONTAINER_ISOLATION_CONFLICT')
        save_manifest()
        return resource
    except Exception:
        RUN['creation_uncertain'] = True
        save_manifest()
        raise


def validate_app():
    data = owned_resource(RUN['app'])
    if (data is None or data.get('running') is not True
            or data.get('image') != RUN['image_ids']['app']
            or set(data.get('networks', {})) != {NAME}
            or data['networks'][NAME].get('NetworkID') != RUN['network']['id']):
        fail('LAB_APP_ISOLATION_CONFLICT')
    bindings = data.get('ports', {})
    if set(bindings) != {'3333/tcp'}:
        fail('LAB_APP_BINDING_CONFLICT')
    rows = bindings['3333/tcp']
    if (not isinstance(rows, list) or len(rows) != 1 or rows[0].get('HostIp') != '127.0.0.1'
            or not re.fullmatch(r'[0-9]{1,5}', rows[0].get('HostPort', ''))
            or not 1 <= int(rows[0]['HostPort']) <= 65535):
        fail('LAB_APP_BINDING_CONFLICT')
    return int(rows[0]['HostPort'])


def request(method, path, body=None, auth=True):
    global port
    paths = {'GET': {'/api/v1/health', '/api/v1/activities'},
             'POST': {'/api/v1/user', '/api/v1/auth/anonymous', '/api/v1/account', '/api/v1/import'}}
    deletion = method == 'DELETE' and path.startswith('/api/v1/activities/')
    if deletion:
        try:
            if str(uuid.UUID(path.removeprefix('/api/v1/activities/'))) != path.removeprefix('/api/v1/activities/'):
                fail('LAB_API_PATH_REJECTED')
        except ValueError:
            fail('LAB_API_PATH_REJECTED')
    elif path not in paths.get(method, set()):
        fail('LAB_API_PATH_REJECTED')
    port = validate_app()
    headers = {'Content-Type': 'application/json', 'Accept-Encoding': 'identity'}
    if auth:
        headers['Authorization'] = 'Bearer ' + os.environ['LAB_GHOST_TOKEN']
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=45)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            fail('LAB_HTTP_REDIRECT_REJECTED')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            fail('LAB_HTTP_ENCODING_REJECTED')
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            fail('LAB_HTTP_RESPONSE_TOO_BIG')
        return response.status, raw
    except (OSError, http.client.HTTPException):
        fail('LAB_HTTP_TRANSPORT_FAILED')
    finally:
        connection.close()


def api(method, path, body=None, auth=True):
    status, raw = request(method, path, None if body is None else json.dumps(body).encode(), auth)
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        fail('LAB_HTTP_JSON_INVALID')


def all_activities():
    status, raw = request('GET', '/api/v1/activities')
    if status != 200:
        fail('LAB_SNAPSHOT_FAILED')
    bd.parse_remote_activity_snapshot(raw)
    return json.loads(raw)['activities']


def cleanup():
    failures = []
    for resource in reversed(RUN['resources']):
        try:
            data = owned_resource(resource)
            if data is not None:
                args = ('rm', '-f', '-v', data['id']) if resource['kind'] == 'container' else ('network', 'rm', data['id'])
                docker(*args)
        except Exception:
            failures.append('LAB_RESOURCE_CLEANUP_FAILED')
    for resource in RUN['resources']:
        try:
            if query_resource(resource['kind'], resource['name']) is not None:
                failures.append('LAB_RESOURCE_REMAINS')
        except Exception:
            failures.append('LAB_RESOURCE_ABSENCE_UNVERIFIED')
    if RUN['creation_uncertain']:
        failures.append('LAB_CREATION_OUTCOME_UNCERTAIN')
    return sorted(set(failures))


def start_lab():
    global port, accounts
    if not stat.S_ISSOCK(Path('/var/run/docker.sock').stat().st_mode):
        fail('LAB_LOCAL_DAEMON_REQUIRED')
    executable = Path('/usr/bin/docker')
    if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
        fail('LAB_DOCKER_EXECUTABLE_REQUIRED')
    docker('info', '--format', '{{.ServerVersion}}')
    RUN['image_ids'] = {key: docker('image', 'inspect', image, '--format', '{{.Id}}') for key, image in IMAGES.items()}
    if any(not re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in RUN['image_ids'].values()):
        fail('LAB_IMAGE_ID_INVALID')
    for key in ('POSTGRES_PASSWORD', 'ACCESS_TOKEN_SALT', 'JWT_SECRET_KEY'):
        os.environ[key] = secrets.token_hex(24)
    os.environ.update(POSTGRES_DB='lab', POSTGRES_USER='lab',
                      DATABASE_URL='postgresql://lab:' + os.environ['POSTGRES_PASSWORD'] + '@postgres:5432/lab?connect_timeout=60',
                      REDIS_HOST='redis', REDIS_PORT='6379', TZ='Europe/Paris', NODE_ENV='production',
                      ENABLE_FEATURE_TELEMETRY='false')
    RUN['network'] = create_resource('network', NAME, ['network', 'create', '--label', 'bd.acceptance-lab=' + NAME, NAME])
    for key, memory, cpu, alias, extra, variables in (
            ('pg', '384m', '1', 'postgres', ['--tmpfs', '/var/lib/postgresql/data:rw,size=512m'], ('POSTGRES_PASSWORD', 'POSTGRES_DB', 'POSTGRES_USER')),
            ('redis', '96m', '0.5', 'redis', ['--tmpfs', '/data:rw,size=64m'], ())):
        args = ['run', '--pull=never', '-d', '--name', NAME + '-' + key, '--label', 'bd.acceptance-lab=' + NAME,
                '--network', NAME, '--network-alias', alias, '--memory', memory, '--cpus', cpu, *extra]
        for variable in variables:
            args += ['-e', variable]
        args.append(IMAGES[key])
        if key == 'redis':
            args += ['redis-server', '--save', '', '--appendonly', 'no']
        create_resource('container', NAME + '-' + key, args, variables)
    args = ['run', '--pull=never', '-d', '--name', NAME + '-app', '--label', 'bd.acceptance-lab=' + NAME,
            '--network', NAME, '--memory', '1536m', '--cpus', '1.5', '--publish', '127.0.0.1::3333',
            '--init', '--security-opt', 'no-new-privileges:true']
    for key in ENV_KEYS:
        args += ['-e', key]
    args.append(IMAGES['app'])
    RUN['app'] = create_resource('container', NAME + '-app', args, ENV_KEYS)
    for _ in range(180):
        try:
            status, _ = request('GET', '/api/v1/health', auth=False)
            if status == 200:
                break
        except RuntimeError as error:
            if str(error) != 'LAB_HTTP_TRANSPORT_FAILED':
                raise
        time.sleep(1)
    else:
        fail('LAB_APP_NOT_READY')
    version = docker('exec', RUN['app']['id'], 'node', '-e', "process.stdout.write(require('/ghostfolio/apps/api/package.json').version)")
    if version != '3.81.0':
        fail('LAB_APP_VERSION_MISMATCH')
    status, user = api('POST', '/api/v1/user', {}, auth=False)
    if status not in (200, 201) or not isinstance(user, dict) or not user.get('accessToken'):
        fail('LAB_SIGNUP_FAILED')
    os.environ['LAB_GHOST_ACCESS_TOKEN'] = user['accessToken']
    status, login = api('POST', '/api/v1/auth/anonymous', {'accessToken': os.environ['LAB_GHOST_ACCESS_TOKEN']}, auth=False)
    if status not in (200, 201) or not isinstance(login, dict) or not login.get('authToken'):
        fail('LAB_AUTH_FAILED')
    os.environ['LAB_GHOST_TOKEN'] = login['authToken']
    status, account = api('POST', '/api/v1/account', {'name': 'SYNTHETIC OWNED LAB', 'currency': 'EUR', 'platformId': None})
    if status not in (200, 201) or not isinstance(account, dict):
        fail('LAB_ACCOUNT_CREATE_FAILED')
    try:
        identifier = str(uuid.UUID(account['id']))
    except (ValueError, KeyError, TypeError):
        fail('LAB_ACCOUNT_ID_INVALID')
    accounts = {'A': identifier}
    if all_activities():
        fail('LAB_INITIAL_STATE_NOT_EMPTY')
    emit('LAB_READY', version=version, initial_activity_count=0)


def interrupt(signum, frame):
    fail('LAB_INTERRUPTED')


def main(argv=None):
    global NAME, RUN
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-disposable-lab', required=True, action='store_true')
    parser.parse_args(argv)
    NAME = 'bd-acceptance-' + uuid.uuid4().hex
    try:
        parent = PROJECT / 'tmp'
        if any(p.is_symlink() for p in (parent, *parent.parents)):
            fail('LAB_UNSAFE_WORK_ROOT')
        bd.private_directory(parent)
        root = parent / ('disposable-acceptance-' + NAME)
        root.mkdir(mode=0o700)
        (root / 'docker-config').mkdir(mode=0o700)
    except Exception:
        print(json.dumps({'passed': False, 'errors': ['LAB_UNSAFE_WORK_ROOT'], 'import_ready': False}))
        return 1
    RUN = {'root': root, 'resources': [], 'events': [], 'creation_uncertain': False}
    previous = {key: os.environ.get(key) for key in (*ENV_KEYS, 'LAB_GHOST_TOKEN', 'LAB_GHOST_ACCESS_TOKEN')}
    handlers = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    errors = []
    try:
        save_manifest()
        start_lab()
        run(sys.modules[__name__])
    except Exception as error:
        errors.append(str(error) if isinstance(error, RuntimeError) and re.fullmatch(r'LAB_[A-Z_]+', str(error)) else 'LAB_SCENARIO_FAILED')
    finally:
        # Repeated signals must not skip bounded cleanup halfway through.
        for sig in handlers:
            signal.signal(sig, signal.SIG_IGN)
        errors.extend(cleanup())
        try:
            bd.atomic_private_yaml(root / 'result.yaml', {'schema_version': 1, 'passed': not errors,
                                   'namespace': NAME, 'events': RUN['events'], 'errors': sorted(set(errors)),
                                   'import_ready': False})
        except Exception:
            errors.append('LAB_FINAL_REPORT_FAILED')
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    print(json.dumps({'passed': not errors, 'namespace': NAME, 'errors': sorted(set(errors)), 'import_ready': False}))
    return 1 if errors else 0


# The fixture lifecycle calls only the owned lab boundary above.


def run(lab):
    root = RUN['root']
    inputs = root / 'inputs'
    inputs.mkdir(mode=0o700)
    seed_markers = set()
    source_markers = set()
    account_key = str(uuid.uuid4())
    binding = {'account_key': account_key, 'target_account_id': lab.accounts['A']}
    symbols = {'FR0000000010': 'AIR.PA', 'FR0000000028': 'OR.PA', 'FR0000000036': 'MC.PA'}

    def snapshot(expected_count):
        status, raw = request('GET', '/api/v1/activities')
        if status != 200:
            raise RuntimeError('LAB_LIFECYCLE_SNAPSHOT_FAILED')
        normalized = bd.parse_remote_activity_snapshot(raw)
        if len(normalized) != expected_count:
            raise RuntimeError('LAB_LIFECYCLE_COUNT_CONFLICT')
        bd.atomic_private_bytes(inputs / 'snapshot.json', raw)
        bd.atomic_private_bytes(inputs / ('snapshot-' + str(expected_count) + '.json'), raw)
        evidence = {'kind': 'complete_acquisition_history',
                    'target_account_id': binding['target_account_id'],
                    'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
                    'confirmed_by': 'synthetic-lab-owner',
                    'reference': lab.NAME + ':empty-start-plus-exact-owned-seed-history'}
        bd.atomic_private_yaml(inputs / 'history.yaml', evidence)
        return raw

    try:
        # Own the complete prior history in an initially empty disposable account.
        seeds = []
        for symbol in symbols.values():
            marker = 'SYNTHETIC-LAB-BASELINE#' + uuid.uuid4().hex
            seed_markers.add(marker)
            seeds.append({'accountId': binding['target_account_id'], 'comment': marker,
                          'currency': 'EUR', 'dataSource': 'YAHOO',
                          'date': '2026-08-17T00:00:00.000Z', 'fee': 0.15,
                          'quantity': 100, 'symbol': symbol, 'type': 'BUY', 'unitPrice': 10.25})
        status, raw = request('POST', '/api/v1/import', json.dumps({'activities': seeds}).encode())
        returned = json.loads(raw).get('activities', [])
        if status != 201 or len(returned) != 3:
            raise RuntimeError('LAB_LIFECYCLE_SEED_FAILED')
        for source in seeds:
            rows = [r for r in returned if r.get('comment') == source['comment']]
            if len(rows) != 1:
                raise RuntimeError('LAB_LIFECYCLE_SEED_OWNERSHIP_CONFLICT')
            row = rows[0]
            if any(row.get(k) != source[k] for k in ('accountId', 'currency', 'date', 'type', 'fee', 'quantity', 'unitPrice')):
                raise RuntimeError('LAB_LIFECYCLE_SEED_VALUES_CONFLICT')
            if any(row.get('assetProfile', {}).get(k) != source[k] for k in ('symbol', 'currency', 'dataSource')):
                raise RuntimeError('LAB_LIFECYCLE_SEED_PROFILE_CONFLICT')
        snapshot(3)
        lab.emit('LAB_LIFECYCLE_BASELINE', count=3, owned_synthetic_history=True)

        fixture_root = PROJECT / 'tests/fixtures'
        config = bd.parse_keyed_yaml((fixture_root / 'import-config-synthetic.yaml').read_bytes())
        config['account']['account_key'] = account_key
        config['account']['target_account_id'] = binding['target_account_id']
        for isin, symbol in symbols.items():
            config['mappings'][isin]['symbol'] = symbol
            config['mappings'][isin]['target_security_evidence'] = 'Synthetic mapping onto verified lab EUR Yahoo fixture; not an actual ISIN mapping'
        for entry in config['documents'].values():
            for name in [entry['statement'], *entry['notes']]:
                bd.atomic_private_bytes(inputs / name, (fixture_root / name).read_bytes())
        bd.atomic_private_yaml(inputs / 'prepare.yaml', config)
        bd.atomic_private_yaml(inputs / 'resolutions.yaml', {})
        review_config = {'schema_version': 1, 'prepared': 'prepared.yaml', 'snapshot': 'snapshot.json',
                         'resolutions': 'resolutions.yaml', 'history_evidence': 'history.yaml'}
        bd.atomic_private_yaml(inputs / 'review.yaml', review_config)
        os.chdir(root)
        summary = bd.prepare_local_plan('inputs/prepare.yaml', 'inputs', 1000000, 32)
        if summary['prepared_activities'] != 3 or summary['import_ready'] is not False:
            raise RuntimeError('LAB_LIFECYCLE_PREPARE_FAILED')
        prepared_path = Path('outputs/prepared-' + account_key + '.yaml')
        first_prepared = prepared_path.read_bytes()
        bd.atomic_private_bytes(inputs / 'initial-prepared.yaml', first_prepared)
        prepared = bd.validated_prepared_review(first_prepared)
        source_markers.update(prepared['activities'])
        bd.atomic_private_bytes(inputs / 'prepared.yaml', first_prepared)
        summary = bd.review_local_snapshot('inputs/review.yaml', 'inputs', 1000000)
        if summary['new_activities'] != 3 or summary['holdings_shortfalls'] or summary['import_ready'] is not False:
            raise RuntimeError('LAB_LIFECYCLE_INITIAL_REVIEW_FAILED')
        # Trusted fixture controller captures once; this pin is not human approval.
        report_raw = Path('outputs/review-' + account_key + '.yaml').read_bytes()
        config_raw = bd.read_local_bytes(inputs / 'review.yaml', inputs, 1000000)
        captured_config = bd.review_capture_configuration(config_raw)
        captures = {k: bd.read_local_bytes(inputs / captured_config[k], inputs, 1000000)
                    for k in ('prepared', 'snapshot', 'resolutions', 'history_evidence')}
        report_pin = hashlib.sha256(report_raw).hexdigest()
        report = bd.validate_frozen_review(report_raw, report_pin, config_raw, captures, 1000000)
        if report['holdings']['shortages'] or len(report['adoption']['new']) != 3:
            raise RuntimeError('LAB_LIFECYCLE_FROZEN_REVIEW_BLOCKED')
        prepared = bd.validated_prepared_review(captures['prepared'])
        frozen = bd.private_directory(inputs / 'frozen-review')
        bd.atomic_private_bytes(frozen / 'config.yaml', config_raw)
        bd.atomic_private_bytes(frozen / 'review.yaml', report_raw)
        for role, raw in captures.items():
            bd.atomic_private_bytes(frozen / (role + '.bytes'), raw)
        bd.atomic_private_yaml(frozen / 'pin.yaml', {'schema_version': 1, 'review_sha256': report_pin,
                                                   'authority': 'owned_fixture_controller_not_human_approval'})
        bd.atomic_private_bytes(inputs / 'initial-review.yaml', report_raw)
        wire = report['wire']
        reviewed = {'body': wire['body_utf8'].encode(), 'sha256': wire['sha256'], 'import_ready': False}
        if len(bd.reviewed_wire_rows(reviewed)) != 3:
            raise RuntimeError('LAB_LIFECYCLE_WIRE_FAILED')
        dispatch_root = inputs / 'dispatch'
        dispatch_root.mkdir(mode=0o700)
        attempts = 0
        target = hashlib.sha256(binding['target_account_id'].encode()).hexdigest()
        lab.emit('LAB_LIFECYCLE_REVIEW', prepared=3, new=3, holdings_shortfalls=0, dispatch_mode='single_event')
        expected_wires = [bd.build_wire_payload({marker: prepared['activities'][marker]})
                          for marker in bd.reviewed_wire_rows(reviewed)]
        def dispatch_request(method, path, body):
            nonlocal attempts
            if method == 'POST':
                ordinal = attempts
                if ordinal >= len(expected_wires) or body != expected_wires[ordinal]['body']:
                    raise RuntimeError('LAB_LIFECYCLE_WIRE_CONFLICT')
                single = expected_wires[ordinal]
                prefix = dispatch_root / ('event-' + str(ordinal))
                bd.atomic_private_bytes(prefix.with_suffix('.wire.json'), body)
                retained = bd.read_keyed_yaml(Path('state/writes-' + target + '.yaml'), 'state', 1000000)
                if retained['intents'][single['sha256']]['state'] != 'uncertain':
                    raise RuntimeError('LAB_LIFECYCLE_INTENT_NOT_FENCED')
                attempts += 1
                lab.emit('LAB_LIFECYCLE_SOURCE_POST_ATTEMPT', ordinal=ordinal, source_posts=attempts,
                         uncertain_before_dispatch=True)
            status, response = request(method, path, body)
            if method == 'POST':
                bd.atomic_private_bytes(prefix.with_suffix('.response.json'), response)
            return status, response
        def observe_confirmation(ordinal, single, before, readback):
            prefix = dispatch_root / ('event-' + str(ordinal))
            bd.atomic_private_yaml(prefix.with_suffix('.provenance.yaml'), {
                'schema_version': 1, 'ordinal': ordinal, 'wire_sha256': single['sha256'],
                'proposal_batch_sha256': reviewed['sha256'],
                'baseline_sha256': hashlib.sha256(before).hexdigest()})
            bd.atomic_private_bytes(prefix.with_suffix('.readback.json'), readback)
            bd.atomic_private_bytes(inputs / ('snapshot-' + str(4 + ordinal) + '.json'), readback)
            lab.emit('LAB_LIFECYCLE_SINGLE_ACCEPTED', ordinal=ordinal, accepted=1,
                     full_readback_count=4 + ordinal, exact_body=True, positively_resolved=True)
        prepare_raw = bd.read_local_bytes(inputs / 'prepare.yaml', inputs, 1000000)
        documents, document_paths = bd.capture_preparation_sources(prepare_raw, inputs, 1000000, 32)
        declaration = {'schema_version': 1,
            'artifact_kind': 'operator_execution_declaration_not_authenticated_approval',
            'review_sha256': report_pin, 'prepare_config': 'prepare.yaml',
            'prepare_config_sha256': hashlib.sha256(prepare_raw).hexdigest(),
            'allowed_origin': 'https://owned-fixture.invalid', **binding,
            'snapshot_sha256': hashlib.sha256(captures['snapshot']).hexdigest(),
            'destination_version': '3.81.0', 'display_timezone': 'Europe/Paris',
            'confirmations': {name: {'confirmed': True, 'confirmed_by': 'owned synthetic fixture controller',
                'reference': 'newly owned disposable fixture, not real operator authorization'}
                for name in ('source_acceptance', 'destination_validation', 'security_review',
                             'recovery_procedure', 'exclusive_access', 'write_authorization')}}
        declaration_raw = bd.yaml.safe_dump(declaration, sort_keys=False).encode()
        application_bundle = {'declaration': declaration_raw,
            'declaration_sha256': hashlib.sha256(declaration_raw).hexdigest(),
            'review': report_raw, 'review_sha256': report_pin, 'config': config_raw,
            'captures': captures, 'prepare_config': prepare_raw, 'documents': documents}
        result = bd.dispatch_qualified_application('state', 'outputs', application_bundle,
            1000000, 32, dispatch_request, observe_confirmation,
            input_paths=[inputs / 'prepare.yaml', inputs / 'review.yaml',
                         *[inputs / captured_config[k] for k in captures], *document_paths])
        archives = list(Path('outputs').glob('application-*'))
        if len(archives) != 1:
            raise RuntimeError('LAB_LIFECYCLE_APPLICATION_ARCHIVE_MISSING')
        manifest = bd.read_keyed_yaml(archives[0] / 'manifest.yaml', archives[0], 1000000)
        archived_roles = {role: bd.read_local_bytes(archives[0] / entry['file'], archives[0], 1000000)
                          for role, entry in manifest['roles'].items()}
        if any(hashlib.sha256(archived_roles[role]).hexdigest() != entry['sha256']
               for role, entry in manifest['roles'].items()):
            raise RuntimeError('LAB_LIFECYCLE_APPLICATION_ARCHIVE_CONFLICT')
        archived_bundle = {'declaration': archived_roles['declaration'],
            'declaration_sha256': manifest['declaration_sha256'], 'review': archived_roles['review'],
            'review_sha256': manifest['review_sha256'], 'config': archived_roles['config'],
            'captures': {k: archived_roles[k] for k in captures},
            'prepare_config': archived_roles['prepare_config'],
            'documents': {alias: {'statement': archived_roles[entry['statement']],
                'notes': [archived_roles[role] for role in entry['notes']]}
                for alias, entry in manifest['documents'].items()}}
        bd.validate_qualified_application(archived_bundle, 1000000, 32)
        lab.emit('LAB_LIFECYCLE_APPLICATION_ARCHIVE', complete=True, cold_replay=True,
                 authority='synthetic_fixture_not_production')
        if result['accepted_events'] != 3 or result['import_ready'] is not False:
            raise RuntimeError('LAB_LIFECYCLE_ACCEPTANCE_FAILED')
        journal = bd.read_keyed_yaml(Path('state/writes-' + target + '.yaml'), 'state', 1000000)
        bd.validate_write_journal(journal)
        if attempts != 3 or len(journal['intents']) != 3 or any(i['state'] != 'confirmed' for i in journal['intents'].values()):
            raise RuntimeError('LAB_LIFECYCLE_SINGLE_JOURNALS_CONFLICT')
        # Refresh the saved full snapshot AND its matching history assertion together.
        snapshot(6)
        lab.emit('LAB_LIFECYCLE_ACCEPTED', accepted=3, source_posts=3, confirmed_intents=3,
                 full_readback_count=6, exact_single_bodies=True, positively_resolved=True)

        bd.prepare_local_plan('inputs/prepare.yaml', 'inputs', 1000000, 32)
        if prepared_path.read_bytes() != first_prepared:
            raise RuntimeError('LAB_LIFECYCLE_IDENTITIES_CHANGED')
        summary = bd.review_local_snapshot('inputs/review.yaml', 'inputs', 1000000)
        report = bd.parse_keyed_yaml(Path('outputs/review-' + account_key + '.yaml').read_bytes())
        if summary['new_activities'] or summary['owned_activities'] != 3 or report['wire'] is not None:
            raise RuntimeError('LAB_LIFECYCLE_REPEAT_CONFLICT')
        if summary['holdings_shortfalls'] or summary['import_ready'] is not False:
            raise RuntimeError('LAB_LIFECYCLE_REPEAT_READINESS_CONFLICT')
        bd.atomic_private_bytes(inputs / 'repeat-prepared.yaml', prepared_path.read_bytes())
        bd.atomic_private_bytes(inputs / 'repeat-review.yaml', Path('outputs/review-' + account_key + '.yaml').read_bytes())
        repeat_raw = Path('outputs/review-' + account_key + '.yaml').read_bytes()
        repeat_captures = {k: bd.read_local_bytes(inputs / captured_config[k], inputs, 1000000) for k in captures}
        repeat_declaration = dict(declaration)
        repeat_declaration['review_sha256'] = hashlib.sha256(repeat_raw).hexdigest()
        repeat_declaration['snapshot_sha256'] = hashlib.sha256(repeat_captures['snapshot']).hexdigest()
        repeat_declaration_raw = bd.yaml.safe_dump(repeat_declaration, sort_keys=False).encode()
        repeat_bundle = {**application_bundle, 'review': repeat_raw,
            'review_sha256': repeat_declaration['review_sha256'], 'captures': repeat_captures,
            'declaration': repeat_declaration_raw,
            'declaration_sha256': hashlib.sha256(repeat_declaration_raw).hexdigest()}
        repeated = bd.dispatch_qualified_application('state', 'outputs', repeat_bundle, 1000000, 32, None)
        if repeated['accepted_events'] != 0 or len(list(Path('outputs').glob('application-*'))) != 1:
            raise RuntimeError('LAB_LIFECYCLE_APPLICATION_REPEAT_CONFLICT')
        lab.emit('LAB_LIFECYCLE_REPEAT', new=0, owned=3, wire_absent=True, second_post_sent=False, identities_unchanged=True)
    finally:
        os.chdir(PROJECT)
        current = lab.all_activities()
        for row in current:
            if row.get('accountId') != binding['target_account_id'] or row.get('comment') not in seed_markers | source_markers:
                raise RuntimeError('LAB_LIFECYCLE_CLEANUP_OWNERSHIP_CONFLICT')
            status, _ = lab.api('DELETE', '/api/v1/activities/' + row['id'])
            if status not in (200, 204):
                raise RuntimeError('LAB_LIFECYCLE_DELETE_FAILED')
        snapshot(0)
        if lab.all_activities():
            raise RuntimeError('LAB_LIFECYCLE_ROLLBACK_NOT_EMPTY')
        lab.emit('LAB_LIFECYCLE_ROLLBACK', deleted=len(current), remaining=0, journals_preserved=True)


if __name__ == '__main__':
    sys.exit(main())

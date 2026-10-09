import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

PATH = Path(__file__).resolve().parents[1] / 'scripts/disposable_acceptance.py'
spec = importlib.util.spec_from_file_location('owned_lab_test', PATH)
lab = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lab
spec.loader.exec_module(lab)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    previous = {key: os.environ.get(key) for key in (*lab.ENV_KEYS, 'LAB_GHOST_TOKEN', 'LAB_GHOST_ACCESS_TOKEN')}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(lab, 'RUN', {'root': tmp_path, 'resources': [], 'events': [], 'creation_uncertain': False})
    monkeypatch.setattr(lab, 'NAME', 'synthetic-lab')
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network or Docker')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(lab.subprocess, 'run', forbidden)
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_opt_in_is_required_before_any_action():
    with pytest.raises(SystemExit) as error:
        lab.main([])
    assert error.value.code == 2
    assert lab.RUN['resources'] == []


def test_docker_uses_only_fixed_daemon_private_config_and_allowed_environment(monkeypatch, tmp_path):
    monkeypatch.setenv('DOCKER_HOST', 'tcp://production.invalid:2376')
    monkeypatch.setenv('DOCKER_CONFIG', '/private/registry')
    monkeypatch.setenv('HTTP_PROXY', 'http://proxy.invalid')
    monkeypatch.setenv('GHOST_TOKEN', 'SYNTHETIC-INHERITED-SECRET')
    monkeypatch.setenv('POSTGRES_PASSWORD', 'SYNTHETIC-GENERATED-LAB')
    captured = {}
    def fake(command, **kwargs):
        captured.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0, stdout='ok', stderr='')
    monkeypatch.setattr(lab.subprocess, 'run', fake)
    assert lab.docker('info', env_keys=('POSTGRES_PASSWORD', 'GHOST_TOKEN')) == 'ok'
    assert captured['command'][:5] == ['/usr/bin/docker', '--config', str(tmp_path / 'docker-config'), '--host', 'unix:///var/run/docker.sock']
    assert captured['env'] == {'PATH': '/usr/local/bin:/usr/bin:/bin', 'POSTGRES_PASSWORD': 'SYNTHETIC-GENERATED-LAB'}
    assert captured['timeout'] == 90 and 'shell' not in captured


@pytest.mark.parametrize('failure', ['returncode', 'timeout'])
def test_docker_error_is_fixed_and_single_shot(monkeypatch, failure):
    calls = []
    def fake(command, **kwargs):
        calls.append(command)
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 90, stderr='private environment')
        return SimpleNamespace(returncode=1, stdout='', stderr='private error with credential')
    monkeypatch.setattr(lab.subprocess, 'run', fake)
    with pytest.raises(RuntimeError, match='^LAB_DOCKER_(FAILED|TIMEOUT)$'):
        lab.docker('run')
    assert len(calls) == 1


def test_authoritative_empty_list_is_distinct_from_daemon_failure(monkeypatch):
    monkeypatch.setattr(lab, 'docker', lambda *a, **k: '')
    assert lab.query_resource('container', 'synthetic-lab-app') is None
    def failure(*args, **kwargs):
        raise RuntimeError('LAB_DOCKER_FAILED')
    monkeypatch.setattr(lab, 'docker', failure)
    with pytest.raises(RuntimeError, match='LAB_DOCKER_FAILED'):
        lab.query_resource('container', 'synthetic-lab-app')


@pytest.mark.parametrize('field', ['id', 'name', 'labels'])
def test_ownership_mismatch_never_grants_cleanup(monkeypatch, field):
    identifier = 'a' * 64
    resource = {'kind': 'container', 'name': 'synthetic-lab-app', 'id': identifier}
    row = {'id': identifier, 'name': '/synthetic-lab-app', 'labels': {'bd.acceptance-lab': lab.NAME}}
    row[field] = {} if field == 'labels' else 'foreign'
    monkeypatch.setattr(lab, 'query_resource', lambda *a: identifier)
    calls = []
    monkeypatch.setattr(lab, 'docker', lambda *args, **kwargs: calls.append(args) or json.dumps(row))
    with pytest.raises(RuntimeError, match='LAB_RESOURCE_OWNER_MISMATCH'):
        lab.owned_resource(resource)
    assert not any('rm' in command for command in calls)


def test_attempt_is_durable_before_timeout_and_unknown_outcome_stays_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(lab, 'query_resource', lambda *a: None)
    def create(*args, **kwargs):
        manifest = lab.bd.parse_keyed_yaml((tmp_path / 'manifest.yaml').read_bytes())
        assert manifest['resources'][0]['name'] == 'synthetic-lab'
        raise RuntimeError('LAB_DOCKER_TIMEOUT')
    monkeypatch.setattr(lab, 'docker', create)
    with pytest.raises(RuntimeError, match='LAB_DOCKER_TIMEOUT'):
        lab.create_resource('network', lab.NAME, ['network', 'create'])
    assert lab.RUN['creation_uncertain'] is True
    monkeypatch.setattr(lab, 'owned_resource', lambda *a: None)
    assert lab.cleanup() == ['LAB_CREATION_OUTCOME_UNCERTAIN']


def test_cleanup_continues_independently_and_final_absence_is_required(monkeypatch):
    lab.RUN['resources'] = [{'kind': 'container', 'name': n, 'id': n} for n in ('first', 'second')]
    calls = []
    def owned(resource):
        if resource['name'] == 'second':
            raise RuntimeError('LAB_RESOURCE_OWNER_MISMATCH')
        return resource
    monkeypatch.setattr(lab, 'owned_resource', owned)
    monkeypatch.setattr(lab, 'docker', lambda *a: calls.append(a) or '')
    monkeypatch.setattr(lab, 'query_resource', lambda kind, name: name if name == 'second' else None)
    assert lab.cleanup() == ['LAB_RESOURCE_CLEANUP_FAILED', 'LAB_RESOURCE_REMAINS']
    assert calls == [('rm', '-f', '-v', 'first')]


@pytest.mark.parametrize('bindings', [None, [], [{'HostIp': '0.0.0.0', 'HostPort': '1234'}],
    [{'HostIp': '127.0.0.1', 'HostPort': '1234'}] * 2, [{'HostIp': '127.0.0.1', 'HostPort': '0'}]])
def test_only_one_owned_loopback_binding_is_accepted(monkeypatch, bindings):
    lab.RUN.update(app={}, image_ids={'app': 'image'}, network={'id': 'network'})
    data = {'running': True, 'image': 'image', 'networks': {lab.NAME: {'NetworkID': 'network'}}, 'ports': {'3333/tcp': bindings}}
    monkeypatch.setattr(lab, 'owned_resource', lambda *a: data)
    with pytest.raises(RuntimeError, match='LAB_APP_BINDING_CONFLICT'):
        lab.validate_app()


@pytest.mark.parametrize('failure', ['redirect', 'encoding', 'oversized', 'timeout'])
def test_direct_http_rejects_unsafe_response_without_retry(monkeypatch, failure):
    monkeypatch.setenv('HTTP_PROXY', 'http://production.invalid')
    monkeypatch.setenv('GHOST_TOKEN', 'SYNTHETIC-PRODUCTION-TOKEN')
    monkeypatch.setenv('LAB_GHOST_TOKEN', 'SYNTHETIC-LAB-TOKEN')
    monkeypatch.setattr(lab, 'validate_app', lambda: 12345)
    calls = []
    def connect(host, port, timeout):
        assert (host, port, timeout) == ('127.0.0.1', 12345, 45)
        def send(method, path, body, headers):
            calls.append((method, path, headers))
            if failure == 'timeout':
                raise TimeoutError('private details')
        response = SimpleNamespace(status=302 if failure == 'redirect' else 201,
            getheader=lambda *a: 'gzip' if failure == 'encoding' else 'identity',
            read=lambda maximum: b'x' * maximum if failure == 'oversized' else b'{}')
        return SimpleNamespace(request=send, getresponse=lambda: response, close=lambda: None)
    monkeypatch.setattr(lab.http.client, 'HTTPConnection', connect)
    with pytest.raises(RuntimeError, match='^LAB_HTTP_'):
        lab.request('POST', '/api/v1/import', b'{}')
    assert len(calls) == 1
    assert calls[0][2]['Authorization'] == 'Bearer SYNTHETIC-LAB-TOKEN'


@pytest.mark.parametrize('path', ['/api/v1/activities/../account', 'https://production.invalid', '/api/v1/activities/not-a-uuid'])
def test_untrusted_deletion_path_is_rejected_before_connection(path):
    with pytest.raises(RuntimeError, match='LAB_API_PATH_REJECTED'):
        lab.request('DELETE', path)


def test_unsafe_work_root_fails_without_docker_and_without_private_path(monkeypatch, tmp_path, capsys):
    project = tmp_path / 'project'
    project.mkdir()
    outside = tmp_path / 'private-target'
    outside.mkdir()
    (project / 'tmp').symlink_to(outside)
    monkeypatch.setattr(lab, 'PROJECT', project)
    assert lab.main(['--run-disposable-lab']) == 1
    output = capsys.readouterr().out
    assert json.loads(output)['errors'] == ['LAB_UNSAFE_WORK_ROOT']
    assert str(outside) not in output


def test_final_report_failure_runs_cleanup_and_never_reports_success(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(lab, 'PROJECT', tmp_path)
    monkeypatch.setattr(lab, 'start_lab', lambda: None)
    monkeypatch.setattr(lab, 'run', lambda *a: None)
    calls = []
    monkeypatch.setattr(lab, 'cleanup', lambda: calls.append('cleanup') or [])
    write = lab.bd.atomic_private_yaml
    def fail_report(path, data):
        if Path(path).name == 'result.yaml':
            raise OSError('private path details')
        return write(path, data)
    monkeypatch.setattr(lab.bd, 'atomic_private_yaml', fail_report)
    assert lab.main(['--run-disposable-lab']) == 1
    assert calls == ['cleanup']
    output = json.loads(capsys.readouterr().out)
    assert output['passed'] is False and output['errors'] == ['LAB_FINAL_REPORT_FAILED']


def test_script_does_not_offer_external_endpoint_or_credentials():
    with pytest.raises(SystemExit):
        lab.main(['--run-disposable-lab', '--endpoint', 'https://production.invalid'])


def test_startup_requires_cached_pins_no_pull_and_version_before_auth(monkeypatch):
    original_stat = Path.stat
    monkeypatch.setattr(Path, 'stat', lambda p, **k: SimpleNamespace(st_mode=stat.S_IFSOCK) if str(p) == '/var/run/docker.sock' else original_stat(p, **k))
    original_file = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda p: True if str(p) == '/usr/bin/docker' else original_file(p))
    monkeypatch.setattr(os, 'access', lambda *a: True)
    calls, creations, requests = [], [], []
    def docker(*args, **kwargs):
        calls.append(args)
        if args[:2] == ('image', 'inspect'):
            return 'sha256:' + 'a' * 64
        if args[0] == 'exec':
            return 'wrong-version'
        return 'server'
    def create(kind, name, args, env_keys=()):
        creations.append((kind, args, env_keys))
        return {'id': 'synthetic-id', 'name': name, 'kind': kind}
    monkeypatch.setattr(lab, 'docker', docker)
    monkeypatch.setattr(lab, 'create_resource', create)
    monkeypatch.setattr(lab, 'request', lambda *a, **k: requests.append(a) or (200, b'{}'))
    with pytest.raises(RuntimeError, match='LAB_APP_VERSION_MISMATCH'):
        lab.start_lab()
    assert {a[2] for a in calls if a[:2] == ('image', 'inspect')} == set(lab.IMAGES.values())
    assert all('--pull=never' in args for kind, args, _ in creations if kind == 'container')
    assert requests == [('GET', '/api/v1/health')]
    assert os.environ['TZ'] == 'Europe/Paris'


@pytest.mark.parametrize('failure', ['none', 'first-intent', 'second-post-timeout', 'frozen-report-tamper'])
def test_complete_synthetic_lifecycle_preserves_stages_and_stops_on_failure(monkeypatch, tmp_path, failure):
    account_id = str(uuid.uuid4())
    monkeypatch.setattr(lab, 'accounts', {'A': account_id})
    rows, posts = [], []
    def request(method, path, body=None, auth=True):
        if method == 'GET':
            return 200, json.dumps({'count': len(rows), 'activities': rows}).encode()
        if method == 'DELETE':
            identifier = path.rsplit('/', 1)[1]
            rows[:] = [row for row in rows if row['id'] != identifier]
            return 204, b''
        assert method == 'POST' and path == '/api/v1/import'
        posts.append(body)
        returned = []
        for sent in json.loads(body)['activities']:
            row = {**sent, 'id': str(uuid.uuid4()), 'account': {'id': account_id, 'tags': []}, 'tags': [],
                   'assetProfile': {k: sent[k] for k in ('symbol', 'dataSource', 'currency')}}
            rows.append(row)
            returned.append(row)
        if failure == 'second-post-timeout' and len(posts) == 3:
            raise TimeoutError('Synthetic lost response after creation')
        return 201, json.dumps({'activities': returned}).encode()
    monkeypatch.setattr(lab, 'request', request)
    if failure == 'frozen-report-tamper':
        original = lab.bd.validate_frozen_review
        def tampered(raw, pin, config, captures, limit):
            report = lab.bd.parse_keyed_yaml(raw)
            report['holdings']['shortages'] = [{'invented': True}]
            changed = lab.bd.yaml.safe_dump(report).encode()
            # Even a freshly matching external pin cannot approve changed semantics.
            return original(changed, lab.hashlib.sha256(changed).hexdigest(), config, captures, limit)
        monkeypatch.setattr(lab.bd, 'validate_frozen_review', tampered)
        with pytest.raises(RuntimeError, match='^FROZEN_REVIEW_CONTENT_CONFLICT$'):
            lab.run(lab)
        assert len(posts) == 1
        assert not list((tmp_path / 'state').glob('writes-*'))
    elif failure == 'first-intent':
        def failure(*args, **kwargs):
            raise OSError('Synthetic persistence failure')
        monkeypatch.setattr(lab.bd, '_persist_write_transition_locked', failure)
        with pytest.raises(RuntimeError, match='LAB_DISPATCH_PERSISTENCE_FAILED'):
            lab.run(lab)
        assert len(posts) == 1  # Seed only; source body never dispatched.
    elif failure == 'second-post-timeout':
        with pytest.raises(RuntimeError, match='LAB_DISPATCH_TRANSPORT_FAILED'):
            lab.run(lab)
        assert len(posts) == 3  # Seed plus two source attempts; no third source event.
        paths = list((tmp_path / 'state').glob('writes-*'))
        journal = lab.bd.parse_keyed_yaml(paths[0].read_bytes())
        assert sorted(i['state'] for i in journal['intents'].values()) == ['confirmed', 'uncertain']
        assert (tmp_path / 'inputs/dispatch/event-0.readback.json').exists()
        assert not (tmp_path / 'inputs/dispatch/event-2.wire.json').exists()
    else:
        lab.run(lab)
        assert len(posts) == 4  # Seed plus three single source POSTs, never a repeat.
        initial = lab.bd.parse_keyed_yaml((tmp_path / 'inputs/initial-review.yaml').read_bytes())
        repeat = lab.bd.parse_keyed_yaml((tmp_path / 'inputs/repeat-review.yaml').read_bytes())
        proposal_rows = json.loads(initial['wire']['body_utf8'])['activities']
        sent_rows = [json.loads(body)['activities'] for body in posts[1:]]
        assert all(len(batch) == 1 for batch in sent_rows)
        assert [batch[0] for batch in sent_rows] == proposal_rows
        for ordinal, body in enumerate(posts[1:]):
            assert (tmp_path / ('inputs/dispatch/event-' + str(ordinal) + '.wire.json')).read_bytes() == body
        history = lab.bd.parse_keyed_yaml((tmp_path / 'inputs/history.yaml').read_bytes())
        # Finally compensation refreshes history to count0; repeat was bound to count6.
        assert history['snapshot_sha256'] == lab.hashlib.sha256((tmp_path / 'inputs/snapshot-0.json').read_bytes()).hexdigest()
        assert repeat['input_sha256']['snapshot'] == lab.hashlib.sha256((tmp_path / 'inputs/snapshot-6.json').read_bytes()).hexdigest()
        assert repeat['wire'] is None and len(repeat['adoption']['owned']) == 3
        frozen = tmp_path / 'inputs/frozen-review'
        config_raw = (frozen / 'config.yaml').read_bytes()
        captures = {k: (frozen / (k + '.bytes')).read_bytes()
                    for k in ('prepared', 'snapshot', 'resolutions', 'history_evidence')}
        pin = lab.bd.parse_keyed_yaml((frozen / 'pin.yaml').read_bytes())['review_sha256']
        replay = lab.bd.validate_frozen_review((frozen / 'review.yaml').read_bytes(), pin, config_raw, captures, 1000000)
        assert replay == initial  # Still valid after compensation overwrites live snapshot/history.
        assert (tmp_path / 'inputs/initial-prepared.yaml').read_bytes() == (tmp_path / 'inputs/repeat-prepared.yaml').read_bytes()
        assert all((tmp_path / ('inputs/snapshot-' + str(n) + '.json')).exists() for n in (0, 3, 6))
        assert not (tmp_path / 'inputs/auth-response.json').exists()
        assert not (lab.PROJECT / 'outputs' / ('review-' + initial['account_key'] + '.yaml')).exists()
    assert rows == []  # Exact owned synthetic compensation on either path.

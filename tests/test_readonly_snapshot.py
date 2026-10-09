import hashlib
import json
from pathlib import Path
import socket
import ssl
from types import SimpleNamespace

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_adoption import prepared, row


@pytest.fixture(autouse=True)
def isolated_no_sockets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Real sockets forbidden')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def setup(monkeypatch, status=200, raw=None, headers=None):
    Path('inputs').mkdir()
    Path('inputs/snapshot-config.yaml').write_text(yaml.safe_dump({'schema_version': 1, 'allowed_origin': 'https://synthetic.example:8443'}))
    monkeypatch.setenv('GHOST_HOST', 'https://synthetic.example:8443')
    monkeypatch.setenv('GHOST_SESSION_BEARER', 'synthetic.header.signature')
    if raw is None:
        records = [row(a, 'remote-' + str(i), owned=True) for i, a in enumerate(prepared().values())]
        raw = json.dumps({'count': len(records), 'activities': records}).encode()
    headers = headers if headers is not None else {'Content-Type': 'application/json; charset=utf-8'}
    events = []
    def connect(host, port, timeout, context):
        assert host == 'synthetic.example' and port == 8443 and timeout == 10
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        events.append('connect')
        def request(method, path, headers):
            assert method == 'GET' and path == '/api/v1/activities'
            assert headers['Authorization'] == 'Bearer synthetic.header.signature'
            assert headers['Accept-Encoding'] == 'identity'
            events.append('GET')
        def read(size):
            events.append(('read', size))
            return raw[:size]
        response = SimpleNamespace(status=status, read=read, getheader=lambda key, default='': headers.get(key, default))
        return SimpleNamespace(request=request, getresponse=lambda: response, close=lambda: events.append('close'))
    monkeypatch.setattr(bd.http.client, 'HTTPSConnection', connect)
    return events, raw


def run(max_bytes=100000):
    return bd.acquire_readonly_snapshot('inputs/snapshot-config.yaml', 'inputs', max_bytes, 10)


def test_one_get_no_auth_exchange_exact_raw_private_file(monkeypatch, capsys):
    events, raw = setup(monkeypatch)
    result = run()
    path = Path('outputs/ghostfolio-snapshot-' + hashlib.sha256(raw).hexdigest() + '.json')
    assert path.read_bytes() == raw and path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert events == ['connect', 'GET', ('read', 100001), 'close']
    assert result['snapshot_activities'] == 3 and result['import_ready'] is False
    assert capsys.readouterr().out == ''
    assert not Path('state').exists()


@pytest.mark.parametrize('origin', [
    'http://synthetic.example', 'https://user:password@synthetic.example',
    'https://synthetic.example/', 'https://synthetic.example/path',
    'https://synthetic.example?x=1', 'https://synthetic.example#x',
    'https://synthetic.example?', 'https://synthetic.example#',
    'https://synthetic.example:0', 'https://synthetic.example:65536',
    'https://synthetic.example:', 'https://SYNTHETIC.example',
    ' https://synthetic.example', 'https://synthetic.example\n',
    'https://synthetic..example', 'https://-synthetic.example',
    'https://synthetic.example.', 'https://synthetic_example',
    'https://éxample.test', 'https://synthetic.example%2fother', None,
])
def test_unsafe_noncanonical_origins_rejected(origin):
    with pytest.raises(RuntimeError, match='INVALID_GHOST_ORIGIN'):
        bd.validated_ghost_origin(origin)


def test_allowed_origin_mismatch_never_connects(monkeypatch):
    events, _ = setup(monkeypatch)
    monkeypatch.setenv('GHOST_HOST', 'https://another.example')
    with pytest.raises(RuntimeError, match='GHOST_ORIGIN_NOT_ALLOWLISTED'):
        run()
    assert events == []


@pytest.mark.parametrize('bearer', ['', 'security-token', 'a.b.c\r\nInjected: secret', 'a.b.c ', 'a.b.c.d'])
def test_missing_wrong_token_or_header_injection_never_connects(monkeypatch, bearer):
    events, _ = setup(monkeypatch)
    monkeypatch.setenv('GHOST_SESSION_BEARER', bearer)
    with pytest.raises(RuntimeError, match='GHOST_SESSION_BEARER_REQUIRED'):
        run()
    assert events == []


def test_legacy_token_is_not_implicitly_used(monkeypatch):
    events, _ = setup(monkeypatch)
    monkeypatch.delenv('GHOST_SESSION_BEARER')
    monkeypatch.setenv('GHOST_TOKEN', 'secret-legacy-token')
    with pytest.raises(RuntimeError, match='GHOST_SESSION_BEARER_REQUIRED'):
        run()
    assert events == []


@pytest.mark.parametrize('status', [301, 302, 307, 308, 401, 403, 429, 500])
def test_redirect_errors_never_follow_or_retry_or_save(monkeypatch, status):
    events, _ = setup(monkeypatch, status=status)
    with pytest.raises(RuntimeError, match='GHOST_REDIRECT_REJECTED|GHOST_SNAPSHOT_HTTP_REJECTED'):
        run()
    assert events == ['connect', 'GET', 'close']
    assert not Path('outputs').exists()


@pytest.mark.parametrize('raw', [b'{"count":2,"activities":[]}', b'{', b'{"count":0,"count":0,"activities":[]}'])
def test_invalid_partial_json_does_not_create_snapshot(monkeypatch, raw):
    events, _ = setup(monkeypatch, raw=raw)
    with pytest.raises(RuntimeError):
        run()
    assert events[-1] == 'close' and not Path('outputs').exists()


@pytest.mark.parametrize('headers', [{'Content-Type': 'text/html'}, {'Content-Type': 'application/json', 'Content-Encoding': 'gzip'}])
def test_html_or_compressed_response_rejected_without_parsing(monkeypatch, headers):
    events, _ = setup(monkeypatch, headers=headers)
    with pytest.raises(RuntimeError, match='GHOST_SNAPSHOT_CONTENT_TYPE_REJECTED|GHOST_SNAPSHOT_ENCODING_REJECTED'):
        run()
    assert events == ['connect', 'GET', 'close']


def test_size_limit_reads_only_one_extra_byte(monkeypatch):
    events, _ = setup(monkeypatch, raw=b' ' * 100001)
    with pytest.raises(RuntimeError, match='GHOST_SNAPSHOT_TOO_LARGE'):
        run()
    assert events[-2:] == [('read', 100001), 'close']


def test_transport_error_redacted_and_never_retried(monkeypatch, caplog):
    setup(monkeypatch)
    attempts = []
    def failed(*args, **kwargs):
        attempts.append(1)
        raise OSError('secret-credential-private-url')
    monkeypatch.setattr(bd.http.client, 'HTTPSConnection', failed)
    assert bd.main(['snapshot', '--config', 'inputs/snapshot-config.yaml', '--input-root', 'inputs', '--max-bytes', '100000', '--timeout', '10']) == 1
    assert attempts == [1]
    assert 'GHOST_SNAPSHOT_TRANSPORT_FAILED' in caplog.text and 'secret-credential' not in caplog.text


def test_cli_counts_only_readiness_false(monkeypatch, capsys):
    setup(monkeypatch)
    assert bd.main(['snapshot', '--config', 'inputs/snapshot-config.yaml', '--input-root', 'inputs', '--max-bytes', '100000', '--timeout', '10']) == 2
    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert result['snapshot_activities'] == 3 and result['import_ready'] is False
    assert 'synthetic.example' not in stdout and 'signature' not in stdout


@pytest.mark.parametrize('alias', ['direct', 'hardlink'])
def test_allowlist_config_alias_cannot_be_replaced_by_snapshot(monkeypatch, alias):
    events, raw = setup(monkeypatch)
    Path('outputs').mkdir(mode=0o755)
    output = Path('outputs/ghostfolio-snapshot-' + hashlib.sha256(raw).hexdigest() + '.json')
    config = Path('inputs/snapshot-config.yaml')
    if alias == 'direct':
        output.write_bytes(config.read_bytes())
        config = output
    else:
        output.hardlink_to(config)
    originals = {p: (p.read_bytes(), p.stat().st_mode) for p in (config, output)}
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'):
        bd.acquire_readonly_snapshot(config, '.', 100000, 10)
    assert all((p.read_bytes(), p.stat().st_mode) == before for p, before in originals.items())
    assert Path('outputs').stat().st_mode & 0o777 == 0o755
    assert events == ['connect', 'GET', ('read', 100001), 'close']
    assert not Path('state').exists()


def test_collision_cli_logs_only_safe_code_and_preserves_prior_output(monkeypatch, capsys, caplog):
    _, raw = setup(monkeypatch)
    Path('outputs').mkdir()
    output = Path('outputs/ghostfolio-snapshot-' + hashlib.sha256(raw).hexdigest() + '.json')
    output.hardlink_to(Path('inputs/snapshot-config.yaml'))
    before = output.read_bytes()
    assert bd.main(['snapshot', '--config', 'inputs/snapshot-config.yaml', '--input-root', '.',
                    '--max-bytes', '100000', '--timeout', '10']) == 1
    assert output.read_bytes() == before
    assert capsys.readouterr().out == ''
    assert 'OUTPUT_INPUT_COLLISION' in caplog.text
    assert 'synthetic.example' not in caplog.text and 'signature' not in caplog.text

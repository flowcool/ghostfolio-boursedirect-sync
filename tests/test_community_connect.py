"""Public routing and GET-only snapshot boundaries, without sockets or credentials."""
import importlib.util
import json
from pathlib import Path
import sys
import base64
import io
import subprocess
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from test_source_qualification import qualification, ORIGIN
from test_source_account_selection import FORM, ACCOUNT
from test_source_notice_window import calendar

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
spec = importlib.util.spec_from_file_location('community_connect', Path(__file__).resolve().parents[1] / 'scripts/community_connect.py')
community = importlib.util.module_from_spec(spec)
spec.loader.exec_module(community)


def test_first_account_choice_can_wait_without_a_second_connection():
    choices = []
    answers = [None, ACCOUNT]

    def choose(available):
        choices.append(available)
        return answers.pop(0)

    state = qualification.planner(notice_as_of='2026-10-12', choose_account=choose)
    qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', FORM.encode(), 'frame_document')
    assert state['queue'] == [] and state['verified'] == set()
    result = qualification.next_document(state)
    assert result['document']['url'].endswith('ong=5&nc=2')
    assert result['configured_account_verified'] is False
    assert state['account_binding'] == ACCOUNT
    assert choices == [['ACCOUNT_A PEA', 'ACCOUNT_B PEA']] * 2


def test_waiting_selection_never_claims_authenticated_account():
    state = qualification.planner(notice_as_of='2026-10-12', choose_account=lambda available: None)
    qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', FORM.encode(), 'frame_document')
    assert qualification.next_document(state) == {'needs_selection': True, 'accounts_verified': False}
    assert state['verified'] == set()


def test_choice_outside_observed_selector_refuses():
    state = qualification.planner(notice_as_of='2026-10-12', choose_account=lambda available: {
        **ACCOUNT, 'source_account_ref': 'ACCOUNT_C PEA'})
    with pytest.raises(RuntimeError):
        qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', FORM.encode(), 'frame_document')
    assert state['queue'] == []


@pytest.mark.parametrize('source_ref,target,origin', [('ACCOUNT_C PEA', '', 'https://ghost.example'),
    ('', 'different', 'https://ghost.example'), ('', '', 'https://other.example')])
def test_configured_routing_never_overrides_saved_binding(source_ref, target, origin):
    saved = {'schema_version': 1, 'ghostfolio_origin': 'https://ghost.example', 'account': ACCOUNT}
    with pytest.raises(RuntimeError, match='ACCOUNT_BINDING_CONFLICT'):
        community.reconcile_binding(saved, origin, source_ref, target)
    assert saved['account'] == ACCOUNT


def test_repeat_binding_preserves_namespace_and_explicit_route():
    saved = {'schema_version': 1, 'ghostfolio_origin': 'https://ghost.example', 'account': ACCOUNT}
    assert community.reconcile_binding(saved, 'https://ghost.example', '', '') == ACCOUNT
    assert community.reconcile_binding(saved, 'https://ghost.example', ACCOUNT['source_account_ref'], ACCOUNT['target_account_id']) == ACCOUNT


def test_snapshot_exchanges_token_once_and_only_gets_accounts_and_activities():
    calls = []

    def request(method, path, body, headers):
        calls.append((method, path, body, headers))
        if method == 'POST':
            assert json.loads(body) == {'accessToken': 'SYNTHETIC_LONG_LIVED_TOKEN'}
            return b'{"authToken":"SYNTHETIC_SESSION_TOKEN"}'
        assert headers == {'Authorization': 'Bearer SYNTHETIC_SESSION_TOKEN'}
        return b'{"accounts":[{"id":"destination-b","name":"Synthetic destination"}]}' if path.endswith('/account') else b'{"activities":[],"count":0}'

    accounts, _, snapshot = community.ghostfolio_snapshot('https://ghost.example', 'SYNTHETIC_LONG_LIVED_TOKEN', request)
    assert accounts[0]['id'] == ACCOUNT['target_account_id']
    assert snapshot == b'{"activities":[],"count":0}'
    assert [(r[0], r[1]) for r in calls] == [('POST', '/api/v1/auth/anonymous'),
        ('GET', '/api/v1/account'), ('GET', '/api/v1/activities')]


@pytest.mark.parametrize('origin', ['https://user@ghost.example', 'https://ghost.example?x',
    'https://ghost.example#x', 'http://ghost.example', 'https://ghost.example/'])
def test_invalid_origin_refuses_before_any_token_exchange(origin):
    with pytest.raises(RuntimeError):
        community.ghostfolio_snapshot(origin, 'SYNTHETIC_TOKEN', lambda *args: pytest.fail('request dispatched'))


def test_failed_exchange_stops_without_retry_or_get():
    calls = []

    def request(*args):
        calls.append(args)
        raise RuntimeError('SYNTHETIC_TRANSPORT_FAILURE')

    with pytest.raises(RuntimeError):
        community.ghostfolio_snapshot('https://ghost.example', 'SYNTHETIC_TOKEN', request)
    assert len(calls) == 1


@pytest.mark.parametrize('body', [b'{"authToken":"bad\\nheader"}', b'{}', b'{"authToken":"x","authToken":"y"}'])
def test_invalid_session_token_stops_before_get(body):
    calls = []

    def request(*args):
        calls.append(args)
        return body

    with pytest.raises((ValueError, RuntimeError)):
        community.ghostfolio_snapshot('https://ghost.example', 'SYNTHETIC_TOKEN', request)
    assert len(calls) == 1


def test_configured_target_is_selected_without_terminal_and_unknown_target_refuses():
    options = [{'value': 'destination-b', 'label': 'Synthetic'}]
    assert community.choose(options, 'Destination', 'destination-b') == 'destination-b'
    with pytest.raises(RuntimeError, match='CONFIGURED_ACCOUNT_UNAVAILABLE'):
        community.choose(options, 'Destination', 'missing')


@pytest.mark.parametrize('origin', ['http://example.com', 'http://ghostfolio:3333/',
    'http://ghostfolio:80', 'http://user@ghostfolio:3333', 'http://ghostfolio:3333?x',
    'http://ghostfolio:3333#x', 'http://192.168.2.1:3333'])
def test_private_http_exception_never_expands_to_other_origins(origin):
    with pytest.raises(RuntimeError):
        community.ghostfolio_origin(origin)


@pytest.mark.parametrize('peer,status,content_type,passes', [
    ('172.20.0.5', 201, 'application/json', True),
    ('8.8.8.8', 201, 'application/json', False),
    ('127.0.0.1', 201, 'application/json', False),
    ('172.20.0.5', 302, 'application/json', False),
    ('172.20.0.5', 200, 'text/html', False)])
def test_private_transport_checks_peer_before_token_and_accepts_created_exchange(monkeypatch, peer, status, content_type, passes):
    calls = []
    payloads = iter([b'{"authToken":"SYNTHETIC_JWT"}',
        b'{"accounts":[{"id":"destination-b","name":"Synthetic"}]}', b'{"activities":[],"count":0}'])

    def connection(host, port, timeout):
        assert (host, port, timeout) == ('ghostfolio', 3333, 30)
        return SimpleNamespace(connect=lambda: calls.append('connect'),
            sock=SimpleNamespace(getpeername=lambda: (peer, port)),
            request=lambda method, path, **kwargs: calls.append((method, path)),
            getresponse=lambda: SimpleNamespace(status=status if len(calls) == 2 else 200,
                getheader=lambda *args: content_type, read=lambda limit: next(payloads)),
            close=lambda: calls.append('close'))

    monkeypatch.setattr(community.http.client, 'HTTPConnection', connection)
    call = lambda: community.ghostfolio_snapshot('http://ghostfolio:3333', 'SYNTHETIC_TOKEN')
    if passes:
        assert call()[0][0]['id'] == 'destination-b'
        assert len([row for row in calls if isinstance(row, tuple)]) == 3
    else:
        with pytest.raises(RuntimeError, match='GHOSTFOLIO_ACCESS_REFUSED'):
            call()
        assert len([row for row in calls if isinstance(row, tuple)]) == (0 if peer in ('8.8.8.8', '127.0.0.1') else 1)


@pytest.mark.parametrize('signal,passes', [('SOURCE_PROXY_READY', True), ('UNEXPECTED', False), ('', False)])
def test_proxy_readiness_waits_for_owned_signal_and_refuses_missing_or_wrong(signal, passes):
    process = subprocess.Popen([sys.executable, '-c',
        'import time; time.sleep(.05); print(' + repr(signal) + ', flush=True); time.sleep(5)'], stdout=subprocess.PIPE)
    try:
        if passes:
            community.wait_proxy_ready(process, timeout=1)
        else:
            with pytest.raises(RuntimeError, match='SOURCE_PROXY_UNAVAILABLE'):
                community.wait_proxy_ready(process, timeout=1)
    finally:
        process.terminate()
        process.wait(timeout=5)
        process.stdout.close()


@pytest.mark.parametrize('logout', [True, False])
@pytest.mark.parametrize('fault', [None, 'missing_period', 'browser_exit', 'wrong_account'])
def test_public_supervisor_retains_complete_readable_receipts_only_after_logout(tmp_path, monkeypatch, logout, fault):
    """Replay the worker protocol through the real planner and importer receipt reader."""
    run = tmp_path / 'run'
    run.mkdir(mode=0o700)
    saved = tmp_path / 'community-binding.yaml'
    original_path = community.Path
    monkeypatch.setattr(community, 'Path', lambda value: saved if value == '/state/community-binding.yaml' else original_path(value))
    monkeypatch.setenv('GHOSTFOLIO_ORIGIN', 'https://ghost.example')
    process = SimpleNamespace(stdout=io.BytesIO(), stderr=io.BytesIO(), stdin=io.BytesIO(),
        poll=lambda: 0, wait=lambda **kwargs: 0)
    monkeypatch.setattr(community.subprocess, 'Popen', lambda *args, **kwargs: process)
    monkeypatch.setattr(community.selectors, 'DefaultSelector', lambda: SimpleNamespace(register=lambda *args: None, close=lambda: None))
    responses = []
    monkeypatch.setattr(community, 'write_frame', lambda process, value: responses.append(value))

    def frames():
        url = ORIGIN + '/priv/new/avis-operes.php'
        body = FORM.encode()
        while True:
            yield {'action': 'document_begin', 'url': url, 'role': 'frame_document', 'representation': 'inert_dom'}
            yield {'action': 'document_chunk', 'body': base64.b64encode(body).decode()}
            yield {'action': 'document_end'}
            yield {'action': 'next_document'}
            next_row = responses[-1]['result']
            if next_row.get('done'):
                yield {'action': 'complete', 'accounts_verified': True, 'session_logged_out': logout,
                    'browser_exit_verified': fault != 'browser_exit', 'totp_requests': 1, 'documents': next_row['documents']}
                return
            url = next_row['document']['url']
            query = parse_qs(urlsplit(url).query)
            month = int(query.get('month', ['10'])[0])
            if fault == 'missing_period' and month == 7:
                yield {'action': 'next_document'}
                yield {'action': 'complete', 'accounts_verified': True, 'session_logged_out': logout,
                    'browser_exit_verified': True, 'totp_requests': 1, 'documents': responses[-1]['result']['documents']}
                return
            body = calendar(month=month, nc=2, days=())
            if fault == 'wrong_account':
                body = calendar(month=month, nc=1, days=())
            if 'month' not in query:
                body = FORM.replace('value=1 selected', 'value=1').replace('value=2>', 'value=2 selected>').encode() + body

    stream = frames()
    monkeypatch.setattr(community, 'read_frame', lambda *args: next(stream))
    call = lambda: community.acquire(run, '2026-10-12', None, ACCOUNT['source_account_ref'], ACCOUNT['target_account_id'], {},
        select_source=lambda available: ACCOUNT['source_account_ref'])
    if not logout or fault:
        with pytest.raises(RuntimeError):
            call()
        assert not (run / 'qualification.yaml').exists()
        return
    account, documents = call()
    assert documents == {'complete': True, 'monthly_statements': 0, 'contract_notes': 0}
    coverage = community.source.replay.private._read(run / 'qualification.yaml')['notice_coverage']
    assert coverage['complete'] is True
    assert coverage['window'] == {'first_day': '2026-07-15', 'last_day': '2026-10-12', 'days': 90}
    assert coverage['empty_months'] == {'PEA': ['2026-07', '2026-08', '2026-09', '2026-10']}
    retained = community.source.replay.private._read(saved)
    assert retained['account'] == account
    config = {'source_mode': 'notices', 'account': account, 'acquisition_runs': {'current': 'run'}}
    notes, _, _, evidence, _ = community.importer.discover_daily_acquisitions(config, tmp_path, '2026-10-12', community.MAX_BYTES, 16)
    assert notes == {} and evidence['current']['captures'] == 5

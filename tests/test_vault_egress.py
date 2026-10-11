import asyncio
import importlib.util
from pathlib import Path
import socket

import pytest

spec = importlib.util.spec_from_file_location('vault_egress', Path(__file__).parents[1] / 'collector/vault-egress.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.parametrize('authority', ['identity.bitwarden.com:443', 'api.bitwarden.com:443'])
def test_exact_cloud_connect(authority):
    raw = f'CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n'.encode()
    assert proxy.connect_target(raw) == authority.split(':')[0]


@pytest.mark.parametrize('raw', [
    b'GET https://api.bitwarden.com/ HTTP/1.1\r\n\r\n',
    b'CONNECT api.bitwarden.com:80 HTTP/1.1\r\n\r\n',
    b'CONNECT api.bitwarden.com.evil:443 HTTP/1.1\r\n\r\n',
    b'CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n',
    b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\nHost: identity.bitwarden.com:443\r\n\r\n',
    b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\nHost: api.bitwarden.com:443\r\nHost: api.bitwarden.com:443\r\n\r\n',
    b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\nContent-Length: 4\r\n\r\n',
    b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\nUser-Agent: synthetic\x00private\r\n\r\n',
    b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\nUser-Agent: ' + b'x' * 8192 + b'\r\n\r\n',
])
def test_refuse_alternate_destinations_and_ambiguous_headers(raw):
    with pytest.raises(RuntimeError, match='VAULT_PROXY_REQUEST_REJECTED'):
        proxy.connect_target(raw)


def record(ip):
    family = socket.AF_INET6 if ':' in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (ip, 443))


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '100.64.0.1',
                              '0.0.0.0', '224.0.0.1', '::1', 'fe80::1', 'fc00::1',
                              '::ffff:8.8.8.8', '2002:0808:0808::1', '2001::1'])
def test_one_private_or_transition_answer_refuses_entire_resolution(ip):
    with pytest.raises(RuntimeError, match='VAULT_PROXY_RESOLUTION_REJECTED'):
        proxy.public_addresses([record('8.8.8.8'), record(ip)])


def test_resolution_is_bounded_and_deduplicated():
    assert proxy.public_addresses([record('8.8.8.8')] * 2) == [(socket.AF_INET, '8.8.8.8')]
    with pytest.raises(RuntimeError):
        proxy.public_addresses([])


def streams(data):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    output = bytearray()
    closed = []
    async def drain():
        pass
    async def wait_closed():
        pass
    # Simple stream-shaped callbacks; no socket or live shared state.
    from types import SimpleNamespace
    writer = SimpleNamespace(write=output.extend, drain=drain,
                             close=lambda: closed.append(True), wait_closed=wait_closed)
    return reader, writer, output, closed


def test_denied_connect_never_resolves_or_connects_and_closes():
    async def run():
        reader, writer, output, closed = streams(b'CONNECT forbidden.invalid:443 HTTP/1.1\r\n\r\n')
        async def forbidden(host):
            pytest.fail('Rejected request reached networking')
        await proxy.serve_connection(reader, writer, forbidden)
        assert output.startswith(b'HTTP/1.1 403')
        assert b'forbidden.invalid' not in output
        assert closed
    asyncio.run(run())


def test_failed_upstream_refuses_without_error_or_secret_output():
    async def run():
        reader, writer, output, closed = streams(b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\n\r\n')
        async def failed(host):
            raise RuntimeError('synthetic-private-underlying-error')
        await proxy.serve_connection(reader, writer, failed)
        assert output.startswith(b'HTTP/1.1 403')
        assert b'synthetic-private' not in output
        assert closed
    asyncio.run(run())


def test_allowed_tunnel_transfers_bytes_and_closes_both_streams():
    async def run():
        reader, writer, output, closed = streams(b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\n\r\nsynthetic-client-tls')
        remote_reader, remote_writer, remote_output, remote_closed = streams(b'synthetic-server-tls')
        hosts = []
        async def connected(host):
            hosts.append(host)
            return remote_reader, remote_writer
        await proxy.serve_connection(reader, writer, connected)
        assert hosts == ['api.bitwarden.com']
        assert output == b'HTTP/1.1 200 Connection Established\r\n\r\nsynthetic-server-tls'
        assert remote_output == b'synthetic-client-tls'
        assert closed and remote_closed
    asyncio.run(run())


def test_client_half_close_retains_delayed_server_response():
    async def run():
        reader, writer, output, closed = streams(b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\n\r\nrequest')
        _, remote_writer, remote_output, remote_closed = streams(b'')
        remote_reader = asyncio.StreamReader()
        half_closed = asyncio.Event()
        remote_writer.can_write_eof = lambda: True
        remote_writer.write_eof = half_closed.set
        async def connected(host):
            return remote_reader, remote_writer
        async def respond_after_half_close():
            await half_closed.wait()
            await asyncio.sleep(0)
            remote_reader.feed_data(b'delayed-complete-response')
            remote_reader.feed_eof()
        await asyncio.gather(proxy.serve_connection(reader, writer, connected), respond_after_half_close())
        assert output == b'HTTP/1.1 200 Connection Established\r\n\r\ndelayed-complete-response'
        assert remote_output == b'request'
        assert closed and remote_closed
    asyncio.run(run())


def test_connection_limit_closes_without_upstream_or_response(monkeypatch):
    async def run():
        reader, writer, output, closed = streams(b'')
        active = set(range(proxy.CONNECTION_LIMIT))
        async def forbidden(*args, **kwargs):
            pytest.fail('Connection limit reached upstream handling')
        monkeypatch.setattr(proxy, 'serve_connection', forbidden)
        await proxy.accept(reader, writer, active)
        assert closed == [True]
        assert output == b''
        assert len(active) == proxy.CONNECTION_LIMIT
    asyncio.run(run())


@pytest.mark.parametrize('failed', [False, True])
def test_accept_releases_active_slot_after_handling(monkeypatch, failed):
    async def run():
        reader, writer, output, closed = streams(b'')
        active = set()
        async def handled(*args, **kwargs):
            assert active == {asyncio.current_task()}
            if failed:
                raise RuntimeError('synthetic')
        monkeypatch.setattr(proxy, 'serve_connection', handled)
        if failed:
            with pytest.raises(RuntimeError, match='synthetic'):
                await proxy.accept(reader, writer, active)
        else:
            await proxy.accept(reader, writer, active)
        assert active == set()
    asyncio.run(run())

@pytest.mark.parametrize('policy, host', [('vault', 'www.boursedirect.fr'),
                                         ('broker-inspection', 'api.bitwarden.com'),
                                         ('broker-inspection', 'identity.bitwarden.com'),
                                         ('broker-inspection', 'www.boursedirect.fr.evil'),
                                         ('broker-inspection', 'boursedirect.fr')])
def test_fixed_policies_do_not_cross_grant_hosts(policy, host):
    with pytest.raises(RuntimeError, match='VAULT_PROXY_REQUEST_REJECTED'):
        proxy.connect_target(f'CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n'.encode(), policy)


def test_broker_inspection_only_accepts_exact_canonical_tls_destination():
    assert proxy.connect_target(b'CONNECT www.boursedirect.fr:443 HTTP/1.1\r\nHost: www.boursedirect.fr:443\r\n\r\n',
                                'broker-inspection') == 'www.boursedirect.fr'
    with pytest.raises(RuntimeError, match='VAULT_PROXY_POLICY_REJECTED'):
        proxy.connect_target(b'', 'arbitrary')


def test_broker_rejection_never_reaches_upstream():
    async def run():
        reader, writer, output, closed = streams(b'CONNECT api.bitwarden.com:443 HTTP/1.1\r\n\r\n')
        async def forbidden(host):
            pytest.fail('Broker policy reached vault networking')
        await proxy.serve_connection(reader, writer, forbidden, 'broker-inspection')
        assert output.startswith(b'HTTP/1.1 403') and closed
    asyncio.run(run())

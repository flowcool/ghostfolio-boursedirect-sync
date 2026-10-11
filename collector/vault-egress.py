#!/usr/bin/env python3
"""Small CONNECT-only vault boundary; infrastructure owns network isolation."""
import asyncio
import ipaddress
import socket
import sys

POLICIES = {'vault': frozenset(('identity.bitwarden.com', 'api.bitwarden.com')),
            'broker-inspection': frozenset(('www.boursedirect.fr',))}
ALLOWED_HOSTS = POLICIES['vault']
HEADER_LIMIT = 8192
CONNECTION_LIMIT = 32


def connect_target(raw, policy='vault'):
    if policy not in POLICIES:
        raise RuntimeError('VAULT_PROXY_POLICY_REJECTED')
    if len(raw) > HEADER_LIMIT or not raw.endswith(b'\r\n\r\n'):
        raise RuntimeError('VAULT_PROXY_REQUEST_REJECTED')
    try:
        lines = raw.decode('ascii').split('\r\n')
        method, authority, protocol = lines[0].split(' ')
        host, port = authority.split(':')
        if method != 'CONNECT' or protocol != 'HTTP/1.1' or port != '443' or host not in POLICIES[policy]:
            raise ValueError()
        seen = set()
        for line in lines[1:-2]:
            name, value = line.split(':', 1)
            name, value = name.lower(), value.strip()
            if name in seen or name not in ('host', 'connection', 'proxy-connection', 'user-agent'):
                raise ValueError()
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError()
            if name == 'host' and value != authority:
                raise ValueError()
            seen.add(name)
        return host
    except (ValueError, UnicodeError):
        raise RuntimeError('VAULT_PROXY_REQUEST_REJECTED') from None


def public_addresses(records):
    addresses = []
    for family, socktype, protocol, _, address in records:
        ip = ipaddress.ip_address(address[0])
        if (family not in (socket.AF_INET, socket.AF_INET6) or socktype != socket.SOCK_STREAM
                or protocol != socket.IPPROTO_TCP or not ip.is_global or ip.is_multicast
                or (ip.version == 6 and (ip.ipv4_mapped or ip.sixtofour or ip.teredo))):
            raise RuntimeError('VAULT_PROXY_RESOLUTION_REJECTED')
        entry = (family, str(ip))
        if entry not in addresses:
            addresses.append(entry)
    if not addresses or len(addresses) > 32:
        raise RuntimeError('VAULT_PROXY_RESOLUTION_REJECTED')
    return addresses


async def upstream(host):
    records = await asyncio.get_running_loop().getaddrinfo(
        host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    # Resolve once, validate every answer, then connect to a literal address.
    # Never resolve the request hostname again or fall back to another destination.
    family, address = public_addresses(records)[0]
    return await asyncio.open_connection(address, 443, family=family)


async def copy_stream(reader, writer):
    while True:
        data = await asyncio.wait_for(reader.read(65536), 60)
        if not data:
            return
        writer.write(data)
        await asyncio.wait_for(writer.drain(), 15)


async def serve_connection(reader, writer, connect=upstream, policy='vault'):
    remote_writer = None
    established = False
    try:
        raw = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 10)
        host = connect_target(raw, policy)
        remote_reader, remote_writer = await asyncio.wait_for(connect(host), 15)
        writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await asyncio.wait_for(writer.drain(), 15)
        established = True
        tasks = [asyncio.create_task(copy_stream(reader, remote_writer)),
                 asyncio.create_task(copy_stream(remote_reader, writer))]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=120)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        # Do not emit hostnames, headers, TLS bytes or underlying exception text.
        if not established:
            writer.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
    finally:
        for stream in (remote_writer, writer):
            if stream is not None:
                stream.close()
                try:
                    await asyncio.wait_for(stream.wait_closed(), 5)
                except Exception:
                    pass


async def accept(reader, writer, active, policy='vault'):
    if len(active) >= CONNECTION_LIMIT:
        writer.close()
        return
    task = asyncio.current_task()
    active.add(task)
    try:
        await serve_connection(reader, writer, policy=policy)
    finally:
        active.discard(task)


async def run(policy='vault'):
    if policy not in POLICIES:
        raise RuntimeError('VAULT_PROXY_POLICY_REJECTED')
    active = set()

    async def on_accept(reader, writer):
        await accept(reader, writer, active, policy)

    server = await asyncio.start_server(on_accept, '0.0.0.0', 8080, limit=HEADER_LIMIT)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    if sys.argv[1:] not in ([], ['--broker-inspection']):
        raise SystemExit('VAULT_PROXY_POLICY_REJECTED')
    asyncio.run(run('broker-inspection' if sys.argv[1:] else 'vault'))

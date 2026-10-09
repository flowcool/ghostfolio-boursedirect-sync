import hashlib
import json
import socket
import ssl
from types import SimpleNamespace

import pytest
import boursedirect_to_ghostfolio as bd
from test_lab_dispatch import inputs, raw, journal
from test_adoption import prepared


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GHOST_HOST", "https://synthetic.example:8443")
    monkeypatch.setenv("GHOST_SESSION_BEARER", "synthetic.header.signature")
    def forbidden(*args, **kwargs): raise AssertionError("No real sockets")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(bd.http.client, "HTTPSConnection", forbidden)


def factory(max_bytes=100000, timeout=10):
    return bd.make_ghostfolio_request("https://synthetic.example:8443", max_bytes, timeout)


def transport(monkeypatch, status=200, response_raw=b"{}", headers=None, fault=None):
    events = []
    headers = headers if headers is not None else {"Content-Type": "application/json; charset=utf-8"}
    def fail(stage):
        if fault == stage: raise OSError("private token origin body exception")
    def connect(host, port, timeout, context):
        events.append("connect")
        fail("connect")
        assert (host, port, timeout) == ("synthetic.example", 8443, 10)
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        def send(method, path, body, headers):
            events.append((method, path, body, headers))
            fail("send")
        def receive():
            events.append("response")
            fail("response")
            def header(key, default=""):
                fail("header")
                return headers.get(key, default)
            def read(limit):
                events.append(("read", limit))
                fail("read")
                return response_raw[:limit]
            return SimpleNamespace(status=status, getheader=header, read=read)
        def close():
            events.append("close")
            fail("close")
        return SimpleNamespace(request=send, getresponse=receive, close=close)
    monkeypatch.setattr(bd.http.client, "HTTPSConnection", connect)
    return events


def test_factory_no_connection_and_captured_origin_credentials(monkeypatch):
    request = factory()
    monkeypatch.setenv("GHOST_HOST", "https://mutated.invalid")
    monkeypatch.setenv("GHOST_SESSION_BEARER", "mutated.header.signature")
    events = transport(monkeypatch)
    assert request("GET", "/api/v1/activities", None) == (200, b"{}")
    assert events[1][3]["Authorization"] == "Bearer synthetic.header.signature"
    assert events[1][3]["Accept-Encoding"] == "identity"
    assert events[-2:] == [("read", 100001), "close"]


def test_exact_canonical_single_body_and_headers(monkeypatch):
    _, wire, _, _, _ = inputs()
    events = transport(monkeypatch, status=201)
    assert factory()("POST", "/api/v1/import", wire["body"]) == (201, b"{}")
    assert events[1][2] is wire["body"]
    assert events[1][3]["Content-Type"] == "application/json"


@pytest.mark.parametrize("method,path,body", [("DELETE", "/api/v1/activities/x", None),
    ("PUT", "/api/v1/import", b"{}"), ("GET", "/api/v1/activities?x=1", None),
    ("GET", "https://other.invalid/api/v1/activities", None),
    ("GET", "/api/v1/activities", b"{}"), ("POST", "/api/v1/auth/anonymous", b"{}"),
    ("POST", "/api/v1/import", b"{}"), ("POST", "/api/v1/import", "not bytes")])
def test_bad_requests_fail_before_connection(method, path, body):
    with pytest.raises(RuntimeError): factory()(method, path, body)


def test_multi_activity_noncanonical_and_large_numeric_body_fail_preconnection():
    full = bd.build_wire_payload(prepared())["body"]
    for body in (full, full + b" ", b'{"activities":[{"quantity":1e5000}]}'):
        with pytest.raises(RuntimeError): factory()("POST", "/api/v1/import", body)


@pytest.mark.parametrize("limit,timeout", [(True, 10), (0, 10), (-1, 10), (1.0, 10),
    (10000, True), (10000, 0), (10000, 121)])
def test_invalid_limits_reject_before_credential_access(monkeypatch, limit, timeout):
    monkeypatch.delenv("GHOST_SESSION_BEARER")
    with pytest.raises(RuntimeError, match="^INVALID_GHOST_REQUEST_LIMITS$"):
        factory(limit, timeout)


@pytest.mark.parametrize("origin", ["http://synthetic.example", "https://synthetic.example/", "https://user:password@synthetic.example", "https://other.invalid"])
def test_allowlist_and_origin_rejected(origin):
    with pytest.raises(RuntimeError): bd.make_ghostfolio_request(origin, 100000, 10)


@pytest.mark.parametrize("bearer", [None, "", "security-token", "a.b.c\r\nheader: secret", "a.b.c ", "a" * 16385])
def test_credentials_only_environment_session_bearer(monkeypatch, bearer):
    if bearer is None: monkeypatch.delenv("GHOST_SESSION_BEARER")
    else: monkeypatch.setenv("GHOST_SESSION_BEARER", bearer)
    monkeypatch.setenv("GHOST_TOKEN", "legacy-security-secret")
    with pytest.raises(RuntimeError, match="^GHOST_SESSION_BEARER_REQUIRED$"): factory()


@pytest.mark.parametrize("fault", ["connect", "send", "response", "header", "read", "close"])
def test_faults_single_shot_safe_no_chaining(monkeypatch, fault):
    events = transport(monkeypatch, fault=fault)
    code = "GHOST_REQUEST_CLOSE_FAILED" if fault == "close" else "GHOST_REQUEST_TRANSPORT_FAILED"
    with pytest.raises(RuntimeError, match="^" + code + "$") as error:
        factory()("GET", "/api/v1/activities", None)
    assert "private" not in str(error.value) and error.value.__context__ is None
    assert events.count("connect") == 1
    assert events.count("close") == (0 if fault == "connect" else 1)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 429, 500, True, 201])
def test_get_status_redirect_rejection_does_not_read_or_retry(monkeypatch, status):
    events = transport(monkeypatch, status=status)
    with pytest.raises(RuntimeError, match="^GHOST_REQUEST_(REDIRECT|STATUS)_REJECTED$"):
        factory()("GET", "/api/v1/activities", None)
    assert events.count("connect") == 1 and events[-1] == "close"
    assert not any(isinstance(e, tuple) and e[0] == "read" for e in events)


@pytest.mark.parametrize("headers", [{"Content-Type": "text/html"}, {"Content-Type": "application/json", "Content-Encoding": "gzip"}])
def test_response_type_encoding_refused_before_read(monkeypatch, headers):
    events = transport(monkeypatch, headers=headers)
    with pytest.raises(RuntimeError): factory()("GET", "/api/v1/activities", None)
    assert events[-1] == "close" and len(events) == 4


def test_bounded_response_read(monkeypatch):
    events = transport(monkeypatch, response_raw=b"x" * 100001)
    with pytest.raises(RuntimeError, match="^GHOST_REQUEST_RESPONSE_LIMIT_OR_TYPE$"):
        factory()("GET", "/api/v1/activities", None)
    assert events[-2:] == [("read", 100001), "close"]


@pytest.mark.parametrize("lost", [False, True])
def test_actual_core_https_adapter_composition_and_lost_response_fence(monkeypatch, lost):
    _, wire, binding, base, remote = inputs()
    rows, sent = [base], []
    def connect(host, port, timeout, context):
        holder = {}
        def send(method, path, body, headers):
            holder["method"] = method
            if method == "POST":
                assert journal(binding)["intents"][wire["sha256"]]["state"] == "uncertain"
                assert body == wire["body"]
                rows.append(remote)
            sent.append(method)
        def response():
            if lost and holder["method"] == "POST": raise TimeoutError("Private response lost after creation")
            return SimpleNamespace(status=201 if holder["method"] == "POST" else 200,
                getheader=lambda k, default="": "application/json" if k == "Content-Type" else default,
                read=lambda limit: json.dumps({"activities": [remote]}).encode() if holder["method"] == "POST" else raw(rows))
        return SimpleNamespace(request=send, getresponse=response, close=lambda: None)
    monkeypatch.setattr(bd.http.client, "HTTPSConnection", connect)
    request = factory()
    if lost:
        with pytest.raises(RuntimeError, match="^LAB_DISPATCH_TRANSPORT_FAILED$"):
            bd.dispatch_single_lab_intent("state", binding, wire, raw([base]), 100000, request)
        assert sent == ["GET", "POST"] and len(rows) == 2
        assert journal(binding)["intents"][wire["sha256"]]["state"] == "uncertain"
    else:
        result = bd.dispatch_single_lab_intent("state", binding, wire, raw([base]), 100000, request)
        assert result["accepted"] == 1 and sent == ["GET", "POST", "GET"]
        assert journal(binding)["intents"][wire["sha256"]]["state"] == "confirmed"
    before = list(sent)
    with pytest.raises(RuntimeError):
        bd.dispatch_single_lab_intent("state", binding, wire, raw([base]), 100000, request)
    assert sent == before

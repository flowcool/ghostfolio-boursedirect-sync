import hashlib
import json
from pathlib import Path
import socket

import pytest
import boursedirect_to_ghostfolio as bd
from test_frozen_review import bundle


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs): raise AssertionError("No real network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def fixture(**kwargs):
    raw, config, captures = bundle(**kwargs)
    report = bd.parse_keyed_yaml(raw)
    binding = {k: report[k] for k in ("account_key", "target_account_id")}
    store = {"rows": json.loads(captures["snapshot"])["activities"], "calls": [], "observed": []}
    return raw, config, captures, binding, store


def snapshot(store):
    return json.dumps({"count": len(store["rows"]), "activities": store["rows"]}).encode()


def backend(store, failure=False):
    def request(method, path, body):
        store["calls"].append((method, path, body))
        if method == "GET": return 200, snapshot(store)
        sent = json.loads(body)["activities"]
        assert len(sent) == 1 and method == "POST"
        item = sent[0]
        remote = {**item, "id": "created-" + str(len(store["rows"])), "tags": [],
                  "account": {"id": item["accountId"], "tags": []},
                  "assetProfile": {k: item[k] for k in ("symbol", "currency", "dataSource")}}
        store["rows"].append(remote)
        if failure and len(posts(store)) == 2:
            raise TimeoutError("Private synthetic callback detail")
        return 201, json.dumps({"activities": [remote]}).encode()
    return request


def posts(store):
    return [call[2] for call in store["calls"] if call[0] == "POST"]


def journal(binding):
    name = "writes-" + hashlib.sha256(binding["target_account_id"].encode()).hexdigest() + ".yaml"
    return bd.parse_keyed_yaml((Path("sequence-state") / name).read_bytes())


def dispatch(data, request=None, observer=None):
    raw, config, captures, binding, store = data
    if observer is None:
        def observer(ordinal, wire, before, after):
            assert journal(binding)["intents"][wire["sha256"]]["state"] == "confirmed"
            store["observed"].append((ordinal, wire, before, after))
    return bd.dispatch_frozen_lab_review("sequence-state", binding, raw,
        hashlib.sha256(raw).hexdigest(), config, captures, 100000,
        request or backend(store), observer)


def test_exact_chronological_bodies_confirmed_observer_and_baseline_chaining():
    data = fixture()
    result = dispatch(data)
    raw, config, captures, binding, store = data
    expected = json.loads(bd.parse_keyed_yaml(raw)["wire"]["body_utf8"])["activities"]
    assert [json.loads(b)["activities"][0] for b in posts(store)] == expected
    assert [c[0] for c in store["calls"]] == ["GET", "POST", "GET"] * 3
    assert result == {"accepted_events": 3, "readback": snapshot(store), "import_ready": False}
    assert store["observed"][0][2] == captures["snapshot"]
    for previous, following in zip(store["observed"], store["observed"][1:]):
        assert previous[3] == following[2]
    assert len(journal(binding)["intents"]) == 3


@pytest.mark.parametrize("mode", ["binding", "shortfall", "tamper", "future"])
def test_preflight_refusals_have_no_callbacks_or_state(mode):
    data = list(fixture(missing=mode == "shortfall"))
    if mode == "binding": data[3]["target_account_id"] = "other-target"
    if mode == "tamper": data[0] += b"unreviewed: true\n"
    if mode == "future":
        prepared = bd.parse_keyed_yaml(data[2]["prepared"])
        next(iter(prepared["activities"].values()))["operation_date"] = "2099-01-01"
        data[2]["prepared"] = bd.yaml.safe_dump(prepared).encode()
    def forbidden(*args): raise AssertionError("No callbacks before preflight")
    with pytest.raises(RuntimeError):
        dispatch(data, forbidden, forbidden)
    assert not Path("sequence-state").exists()


def test_later_wire_defect_is_rejected_before_first_core_call(monkeypatch):
    data = fixture()
    markers = list(bd.reviewed_wire_rows({"body": bd.parse_keyed_yaml(data[0])["wire"]["body_utf8"].encode(),
        "sha256": bd.parse_keyed_yaml(data[0])["wire"]["sha256"], "import_ready": False}))
    original = bd.build_wire_payload
    def changed(activities):
        wire = original(activities)
        if set(activities) == {markers[1]} and activities[markers[1]].get("import_ready") is False:
            wire["body"] += b" "
            wire["sha256"] = hashlib.sha256(wire["body"]).hexdigest()
        return wire
    monkeypatch.setattr(bd, "build_wire_payload", changed)
    def forbidden(*args, **kwargs): raise AssertionError("All wires preflight before core")
    monkeypatch.setattr(bd, "dispatch_single_lab_intent", forbidden)
    with pytest.raises(RuntimeError): dispatch(data)
    assert not Path("sequence-state").exists()


def test_all_existing_noop_returns_only_captured_readback_without_state(monkeypatch):
    data = fixture(existing=True)
    def forbidden(*args): raise AssertionError("No callback/state for noop")
    monkeypatch.setattr(bd, "private_directory", forbidden)
    assert dispatch(data, forbidden, forbidden) == {"accepted_events": 0, "readback": data[2]["snapshot"], "import_ready": False}
    assert not Path("sequence-state").exists()


@pytest.mark.parametrize("failure", ["observer", "transport", "between-events"])
def test_partial_failure_keeps_durable_state_and_stops(failure):
    data = fixture()
    store, binding = data[4], data[3]
    request = backend(store, failure == "transport")
    def observe(ordinal, wire, before, after):
        store["observed"].append(ordinal)
        assert journal(binding)["intents"][wire["sha256"]]["state"] == "confirmed"
        if failure == "observer": raise OSError("Private synthetic archive path")
        if failure == "between-events": store["rows"][0]["comment"] = "intervening-writer"
    code = {"observer": "LAB_SEQUENCE_OBSERVER_FAILED", "transport": "LAB_DISPATCH_TRANSPORT_FAILED", "between-events": "LAB_DISPATCH_BASELINE_CHANGED"}[failure]
    with pytest.raises(RuntimeError, match="^" + code + "$") as error:
        dispatch(data, request, observe)
    states = sorted(i["state"] for i in journal(binding)["intents"].values())
    assert states == (["confirmed", "uncertain"] if failure == "transport" else ["confirmed"])
    assert len(posts(store)) == (2 if failure == "transport" else 1)
    if failure == "observer": assert error.value.__suppress_context__ is True
    before = len(store["calls"])
    with pytest.raises(RuntimeError): dispatch(data, request, observe)
    assert len(store["calls"]) == before  # Tombstone/account fence before even GET.


def test_observer_mutation_cannot_change_future_wires_binding_or_baseline():
    data = fixture()
    raw, _, captures, binding, store = data
    expected = json.loads(bd.parse_keyed_yaml(raw)["wire"]["body_utf8"])["activities"]
    def observe(ordinal, wire, before, after):
        wire["body"] = b"mutated"
        binding["target_account_id"] = "mutated"
        captures["snapshot"] = b"mutated"
        captures["prepared"] = b"mutated"
    result = dispatch(data, observer=observe)
    assert result["accepted_events"] == 3
    assert [json.loads(b)["activities"][0] for b in posts(store)] == expected

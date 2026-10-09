import copy
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_prepare import setup, run, artifact


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('No sockets')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def bundle():
    config = setup()
    raw = Path('inputs/import-config.yaml').read_bytes()
    docs = {'month-a': {'statement': Path('inputs/statement.html').read_bytes(),
                        'notes': [Path('inputs/buy.html').read_bytes(), Path('inputs/sell.html').read_bytes()]}}
    return config, raw, docs


def dump(value):
    return yaml.safe_dump(value, sort_keys=False).encode()


def test_pure_replay_equals_publisher_and_never_reads_or_writes(monkeypatch):
    config, raw, docs = bundle()
    run()
    saved = artifact().read_bytes()
    def forbidden(*args, **kwargs):
        raise AssertionError('Pure replay must not access files or locks')
    monkeypatch.setattr(bd.os, 'open', forbidden)
    monkeypatch.setattr(bd.fcntl, 'flock', forbidden)
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    computed = bd.compute_prepared_sources(raw, docs, 100000, 32)
    assert computed['artifact'] == yaml.safe_load(saved)
    assert len(computed['snapshots']) == 1
    assert bd.validate_prepared_sources(saved, raw, docs, 100000, 32) == computed['artifact']


@pytest.mark.parametrize('limit', [True, False, 0, -1, 1.0, '100000', None])
@pytest.mark.parametrize('field', ['bytes', 'depth'])
def test_exact_integer_limits(limit, field):
    _, raw, docs = bundle()
    with pytest.raises(RuntimeError, match='INVALID_(SIZE|DEPTH)_LIMIT'):
        bd.compute_prepared_sources(raw, docs, limit if field == 'bytes' else 100000,
                                   limit if field == 'depth' else 32)


@pytest.mark.parametrize('role', ['config', 'statement', 'last_note'])
@pytest.mark.parametrize('bad', ['oversize', 'string', 'bytearray'])
def test_all_raw_bounds_checked_before_html_parsing(role, bad, monkeypatch):
    _, raw, docs = bundle()
    original = raw if role == 'config' else docs['month-a']['statement'] if role == 'statement' else docs['month-a']['notes'][-1]
    value = b'x' * 100001 if bad == 'oversize' else original.decode() if bad == 'string' else bytearray(original)
    if role == 'config':
        raw = value
    elif role == 'statement':
        docs['month-a']['statement'] = value
    else:
        docs['month-a']['notes'][-1] = value
    def forbidden(*args, **kwargs):
        raise AssertionError('Bounds before HTML parse')
    monkeypatch.setattr(bd, 'parse_statement', forbidden)
    monkeypatch.setattr(bd, 'parse_contract_note', forbidden)
    with pytest.raises(RuntimeError, match='PREPARATION_INPUT_LIMIT_EXCEEDED'):
        bd.compute_prepared_sources(raw, docs, 100000, 32)


@pytest.mark.parametrize('change', ['missing_alias', 'extra_alias', 'extra_role', 'missing_role', 'notes_tuple', 'notes_short', 'notes_long'])
def test_capture_schema_and_ordered_multiplicity(change):
    _, raw, docs = bundle()
    capture = docs['month-a']
    if change == 'missing_alias':
        docs.clear()
    elif change == 'extra_alias':
        docs['other'] = copy.deepcopy(capture)
    elif change == 'extra_role':
        capture['unused'] = b''
    elif change == 'missing_role':
        del capture['statement']
    elif change == 'notes_tuple':
        capture['notes'] = tuple(capture['notes'])
    elif change == 'notes_short':
        capture['notes'].pop()
    else:
        capture['notes'].append(capture['notes'][0])
    with pytest.raises(RuntimeError, match='INVALID_PREPARATION_CAPTURES'):
        bd.compute_prepared_sources(raw, docs, 100000, 32)


@pytest.mark.parametrize('change', ['schema_bool', 'extra', 'bad_alias', 'bad_entry', 'bad_account'])
def test_configuration_schema(change):
    config, _, docs = bundle()
    if change == 'schema_bool':
        config['schema_version'] = True
    elif change == 'extra':
        config['unused'] = 'not allowed'
    elif change == 'bad_alias':
        config['documents']['../invalid'] = config['documents'].pop('month-a')
    elif change == 'bad_entry':
        config['documents']['month-a']['notes'] = []
    else:
        config['account']['extra'] = 'not allowed'
    with pytest.raises(RuntimeError):
        bd.compute_prepared_sources(dump(config), docs, 100000, 32)
    assert not Path('state').exists() and not Path('outputs').exists()


@pytest.mark.parametrize('change', ['schema_bool', 'quantity_number', 'fee', 'digest', 'extra', 'blocker', 'activity_missing'])
def test_full_typed_artifact_comparison(change):
    _, raw, docs = bundle()
    expected = bd.compute_prepared_sources(raw, docs, 100000, 32)['artifact']
    observed = copy.deepcopy(expected)
    row = next(iter(observed['activities'].values()))
    if change == 'schema_bool':
        observed['schema_version'] = True
    elif change == 'quantity_number':
        row['quantity'] = int(row['quantity'])
    elif change == 'fee':
        row['fee'] = '999'
    elif change == 'digest':
        observed['source_digests']['month-a']['statement'] = '0' * 64
    elif change == 'extra':
        observed['extra'] = None
    elif change == 'blocker':
        observed['blockers'].reverse()
    else:
        observed['activities'].pop(next(iter(observed['activities'])))
    with pytest.raises(RuntimeError, match='PREPARED_SOURCE_CONTENT_CONFLICT'):
        bd.validate_prepared_sources(dump(observed), raw, docs, 100000, 32)


def test_byte_only_document_change_and_financial_mapping_change_are_detected():
    config, raw, docs = bundle()
    expected = dump(bd.compute_prepared_sources(raw, docs, 100000, 32)['artifact'])
    docs['month-a']['statement'] += b'\n'
    with pytest.raises(RuntimeError, match='PREPARED_SOURCE_CONTENT_CONFLICT'):
        bd.validate_prepared_sources(expected, raw, docs, 100000, 32)
    docs['month-a']['statement'] = docs['month-a']['statement'][:-1]
    for mapping in config['mappings'].values():
        mapping['symbol'] = 'OTHER'
    with pytest.raises(RuntimeError, match='PREPARED_SOURCE_CONTENT_CONFLICT'):
        bd.validate_prepared_sources(expected, dump(config), docs, 100000, 32)


def test_current_evidence_only_change_is_not_historical_provenance():
    config, raw, docs = bundle()
    expected = dump(bd.compute_prepared_sources(raw, docs, 100000, 32)['artifact'])
    for mapping in config['mappings'].values():
        mapping['currency_evidence'] = 'new externally reviewed reference'
        mapping['target_security_evidence'] = 'new externally reviewed identity reference'
    assert bd.validate_prepared_sources(expected, dump(config), docs, 100000, 32) == yaml.safe_load(expected)
    # Caller must pin this *current* config in its declaration; old artifact has no config pin.


def test_publisher_captures_each_config_and_document_once(monkeypatch):
    bundle()
    real = bd.read_local_bytes
    calls = []
    def capture(path, root, limit):
        calls.append(str(path))
        return real(path, root, limit)
    monkeypatch.setattr(bd, 'read_local_bytes', capture)
    run()
    assert calls == ['inputs/import-config.yaml', 'inputs/statement.html', 'inputs/buy.html', 'inputs/sell.html']


def test_note_reordering_preserves_financial_rows_but_changes_ordered_source_hashes():
    _, raw, docs = bundle()
    expected = dump(bd.compute_prepared_sources(raw, docs, 100000, 32)['artifact'])
    docs['month-a']['notes'].reverse()
    with pytest.raises(RuntimeError, match='PREPARED_SOURCE_CONTENT_CONFLICT'):
        bd.validate_prepared_sources(expected, raw, docs, 100000, 32)

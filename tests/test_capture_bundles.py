import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import uuid

from bs4 import BeautifulSoup
import pytest
import yaml
import boursedirect_to_ghostfolio as bd

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline qualification must not connect')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def encoded(value):
    return yaml.safe_dump(value, sort_keys=False).encode()


def values():
    config = yaml.safe_load((FIXTURES / 'import-config-synthetic.yaml').read_bytes())
    statement = (FIXTURES / 'statement-paired-synthetic.html').read_bytes()
    sell = BeautifulSoup((FIXTURES / 'note-multi-sell-synthetic.html').read_bytes(), 'html.parser')
    buy = BeautifulSoup((FIXTURES / 'note-buy-synthetic.html').read_bytes(), 'html.parser')
    def columns(soup):
        ledger = soup.find('table', id='synthetic-note')
        return [c.find('table', recursive=False) for c in bd.cells(bd.direct_rows(ledger)[1])]
    for target, source in zip(columns(sell), columns(buy)):
        for row in bd.direct_rows(source):
            target.append(copy.deepcopy(row))
    account = config['account']['source_account_ref']
    files, entries = {}, {}
    for sequence, (role, period, raw) in enumerate([
            ('statement', '2026-09', statement), ('note', '2026-09-17', str(sell).encode())], 1):
        filename = 'capture-' + str(uuid.uuid4()) + '.html'
        filtered = bd.filter_capture_dom(raw, role, period, account, 100000, 32)
        loader = str(uuid.uuid4())
        ticket = {'account_ref': account, 'role': role, 'period': period,
                  'origin_frame_epoch': str(uuid.uuid4()), 'link_handle': str(uuid.uuid4()),
                  'request_url': 'https://www.boursedirect.fr/priv/synthetic-document',
                  'target_id': str(uuid.uuid4()), 'loader_id': loader,
                  'commit_loader_id': loader, 'load_loader_id': loader, 'sequence': sequence}
        files[filename] = filtered
        entries[filename] = {'role': role, 'period': period, 'sha256': hashlib.sha256(filtered).hexdigest(),
                             'provenance': 'browser_dom_utf8_filtered', 'ticket': ticket}
    manifest = {'schema_version': 1, 'artifact_kind': 'acquisition_bundle', 'status': 'complete',
                'run_id': str(uuid.uuid4()), 'account_key': config['account']['account_key'],
                'source_account_ref': account, 'files': entries}
    return manifest, files, config


def qualify(manifest, files, config):
    return bd.qualify_capture_bundle(encoded(manifest), files, encoded(config), 100000, 32)


def local():
    manifest, files, config = values()
    Path('inputs/bundle/sources').mkdir(parents=True, mode=0o700)
    Path('outputs').mkdir(mode=0o700)
    Path('inputs/config.yaml').write_bytes(encoded(config))
    Path('inputs/bundle/manifest.yaml').write_bytes(encoded(manifest))
    for filename, raw in files.items():
        Path('inputs/bundle/sources', filename).write_bytes(raw)
    return manifest, files, config


def run(output='outputs/proposal'):
    return bd.qualify_local_captures('inputs/bundle/manifest.yaml', 'inputs/config.yaml',
                                     'inputs', output, 100000, 32)


def test_pure_qualification_preserves_inputs_and_requires_no_readiness():
    inputs = values()
    before = copy.deepcopy(inputs)
    result = qualify(*inputs)
    assert inputs == before
    assert result['configuration']['account'] == inputs[2]['account']
    assert result['configuration']['mappings'] == inputs[2]['mappings']
    assert result['report']['prepared_activities'] == 3
    assert result['report']['file_count'] == 2
    assert all(result['report'][k] is False for k in ('import_ready', 'freshness_verified', 'source_authenticity_verified'))


def test_report_minimizes_tickets_without_changing_source_or_proposal():
    manifest, files, config = local()
    sentinel = 'SYNTHETIC_PRIVATE_QUERY_VALUE'
    for entry in manifest['files'].values():
        entry['ticket']['request_url'] += '?session=' + sentinel
    manifest_path = Path('inputs/bundle/manifest.yaml')
    manifest_path.write_bytes(encoded(manifest))
    captured = [manifest_path, Path('inputs/config.yaml'),
                *[Path('inputs/bundle/sources', name) for name in files]]
    before = {path: (path.read_bytes(), path.stat().st_ino) for path in captured}
    run()
    raw = Path('outputs/proposal/qualification.yaml').read_bytes()
    report = yaml.safe_load(raw)
    assert sentinel.encode() not in raw
    assert config['account']['source_account_ref'].encode() not in raw
    assert b'request_url' not in raw and b'ticket:' not in raw
    assert report['manifest_sha256'] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert set(report['files']) == set(files)
    for name, entry in report['files'].items():
        assert set(entry) == {'role', 'period', 'sha256', 'sequence'}
        assert entry['sha256'] == hashlib.sha256(files[name]).hexdigest()
        assert entry['sequence'] == manifest['files'][name]['ticket']['sequence']
        assert entry['role'] == manifest['files'][name]['role']
        assert entry['period'] == manifest['files'][name]['period']
    summary = bd.prepare_local_plan('outputs/proposal/prepare-proposal.yaml', '.', 100000, 32)
    assert summary['prepared_activities'] == 3
    assert {path: (path.read_bytes(), path.stat().st_ino) for path in captured} == before


def test_filter_strips_active_elements_attributes_comments_and_preserves_slots():
    raw = (FIXTURES / 'statement-paired-synthetic.html').read_bytes()
    raw = raw.replace(b'<body>', b'<body onload="TOKEN"><script>TOKEN</script><form><input value="TOKEN"></form><iframe src="TOKEN"></iframe><a href="TOKEN">Print</a>')
    account = 'SYNTHETIC_ACCOUNT_EUR'
    result = bd.filter_capture_dom(raw, 'statement', '2026-09', account, 100000, 32)
    assert b'TOKEN' not in result and b'<script' not in result and b'<a ' not in result
    assert bd.parse_statement(bd.decode_document(result), 32) == bd.parse_statement(bd.decode_document(raw), 32)
    assert bd.filter_capture_dom(result, 'statement', '2026-09', account, 100000, 32) == result


@pytest.mark.parametrize('field,value,error', [
    ('status', 'partial', 'INVALID_COMPLETE_CAPTURE_MANIFEST'),
    ('schema_version', True, 'INVALID_COMPLETE_CAPTURE_MANIFEST'),
    ('artifact_kind', 'raw_http', 'INVALID_COMPLETE_CAPTURE_MANIFEST'),
    ('account_key', str(uuid.uuid4()), 'CAPTURE_ACCOUNT_CONFLICT'),
    ('source_account_ref', 'OTHER', 'CAPTURE_ACCOUNT_CONFLICT'),
    ('run_id', 'not-a-uuid', 'INVALID_IMMUTABLE_ACCOUNT_KEY'),
])
def test_manifest_refusals(field, value, error):
    m, f, c = values(); m[field] = value
    with pytest.raises(RuntimeError, match=error):
        qualify(m, f, c)


@pytest.mark.parametrize('field,value,error', [
    ('role', 'history', 'INVALID_CAPTURE_PERIOD'),
    ('period', '2026-13', 'INVALID_CAPTURE_PERIOD'),
    ('period', '2026-08', 'CAPTURE_PERIOD_CONFLICT'),
    ('sha256', '0' * 64, 'CAPTURE_DIGEST_CONFLICT'),
    ('provenance', 'raw_http', 'CAPTURE_PROVENANCE_REQUIRED'),
])
def test_entry_refusals(field, value, error):
    m, f, c = values(); entry = next(iter(m['files'].values())); entry[field] = value
    if field == 'period': entry['ticket']['period'] = value
    with pytest.raises(RuntimeError, match=error):
        qualify(m, f, c)


@pytest.mark.parametrize('field,value,error', [
    ('account_ref', 'OTHER', 'CAPTURE_TICKET_CONFLICT'),
    ('role', 'note', 'CAPTURE_TICKET_CONFLICT'),
    ('load_loader_id', str(uuid.uuid4()), 'CAPTURE_TICKET_CONFLICT'),
    ('commit_loader_id', str(uuid.uuid4()), 'CAPTURE_TICKET_CONFLICT'),
    ('sequence', True, 'INVALID_CAPTURE_TICKET'),
    ('request_url', 'https://www.boursedirect.fr@evil.test/', 'INVALID_CAPTURE_TICKET_URL'),
    ('request_url', 'https://www.boursedirect.fr/%2e%2e/x', 'INVALID_CAPTURE_TICKET_URL'),
])
def test_ticket_consistency_only(field, value, error):
    m, f, c = values(); next(iter(m['files'].values()))['ticket'][field] = value
    with pytest.raises(RuntimeError, match=error):
        qualify(m, f, c)


def test_duplicate_role_day_and_unreferenced_file_refuse():
    m, f, c = values(); name = next(iter(f)); duplicate = 'capture-' + str(uuid.uuid4()) + '.html'
    m['files'][duplicate] = copy.deepcopy(m['files'][name]); f[duplicate] = f[name]
    with pytest.raises(RuntimeError, match='DUPLICATE_CAPTURE_ROLE_PERIOD'):
        qualify(m, f, c)
    del m['files'][duplicate]
    with pytest.raises(RuntimeError, match='CAPTURE_FILE_INVENTORY_CONFLICT'):
        qualify(m, f, c)


def test_active_dom_with_matching_digest_is_not_filtered_evidence():
    m, f, c = values(); name = next(iter(f)); f[name] = f[name].replace(b'<body>', b'<body><script>hidden</script>')
    m['files'][name]['sha256'] = hashlib.sha256(f[name]).hexdigest()
    with pytest.raises(RuntimeError, match='CAPTURE_NOT_FILTERED_UTF8'):
        qualify(m, f, c)


def test_unmapped_security_blocks_proposal():
    m, f, c = values(); c['mappings'] = {}
    with pytest.raises(RuntimeError, match='SECURITY_MAPPING_MISSING'):
        qualify(m, f, c)


def test_local_publication_private_and_replayable_preserves_sources():
    local()
    before = {p: p.read_bytes() for p in Path('inputs').rglob('*') if p.is_file()}
    result = run()
    assert result['prepared_activities'] == 3
    assert {p: p.read_bytes() for p in before} == before
    proposal = Path('outputs/proposal/prepare-proposal.yaml')
    assert proposal.stat().st_mode & 0o777 == 0o600
    assert proposal.parent.stat().st_mode & 0o777 == 0o700
    config = yaml.safe_load(proposal.read_bytes())
    captured = {alias: {'statement': Path('inputs', doc['statement']).read_bytes(),
                       'notes': [Path('inputs', n).read_bytes() for n in doc['notes']]}
                for alias, doc in config['documents'].items()}
    assert len(bd.compute_prepared_sources(proposal.read_bytes(), captured, 100000, 32)['artifact']['activities']) == 3
    with pytest.raises(RuntimeError, match='CAPTURE_OUTPUT_EXISTS'):
        run()


@pytest.mark.parametrize('kind', ['extra', 'symlink', 'hardlink', 'tree', 'existing'])
def test_local_preflight_preserves_input_bytes_and_inodes(kind):
    local()
    config = Path('inputs/config.yaml'); before = config.read_bytes(); inode = config.stat().st_ino
    if kind == 'extra': Path('inputs/bundle/sources/extra.html').write_text('extra')
    if kind == 'symlink': Path('outputs/proposal').symlink_to(config.resolve())
    if kind == 'hardlink': os.link(config, 'outputs/proposal')
    if kind == 'existing': Path('outputs/proposal').mkdir()
    output = 'inputs/new' if kind == 'tree' else 'outputs/proposal'
    with pytest.raises(RuntimeError): run(output)
    assert config.read_bytes() == before and config.stat().st_ino == inode
    assert not Path('outputs/proposal/qualification.yaml').exists()


def test_cli_counts_only_and_exit_two(capsys):
    local()
    code = bd.main(['qualify-captures', '--manifest', 'inputs/bundle/manifest.yaml',
                    '--config', 'inputs/config.yaml', '--input-root', 'inputs',
                    '--output', 'outputs/proposal', '--max-bytes', '100000', '--max-depth', '32'])
    assert code == 2
    output = capsys.readouterr().out
    assert 'SYNTHETIC_ACCOUNT' not in output and 'https:' not in output
    assert json.loads(output)['import_ready'] is False


@pytest.mark.parametrize('budget', [True, 0, -1, 4194305])
def test_explicit_size_bounds(budget):
    m, f, c = values()
    with pytest.raises(RuntimeError, match='CAPTURE_SIZE_LIMIT'):
        bd.qualify_capture_bundle(encoded(m), f, encoded(c), budget, 32)


def test_wrong_note_day_in_any_group_refuses():
    m, f, c = values()
    name = next(n for n, e in m['files'].items() if e['role'] == 'note')
    f[name] = f[name].replace(b'17/09/2026', b'18/09/2026', 1)
    m['files'][name]['sha256'] = hashlib.sha256(f[name]).hexdigest()
    with pytest.raises(RuntimeError, match='NOTE_MULTIPLE_DATES'):
        qualify(m, f, c)


def test_duplicate_sequence_and_escaped_filename_refuse():
    m, f, c = values()
    for entry in m['files'].values(): entry['ticket']['sequence'] = 1
    with pytest.raises(RuntimeError, match='DUPLICATE_CAPTURE_SEQUENCE'):
        qualify(m, f, c)
    name = next(iter(f)); f['../escape.html'] = f.pop(name)
    m['files']['../escape.html'] = m['files'].pop(name)
    with pytest.raises(RuntimeError, match='INVALID_CAPTURE_FILENAME'):
        qualify(m, f, c)


def test_unreferenced_bundle_entry_and_symlinked_source_refuse():
    m, f, c = local()
    Path('inputs/bundle/unreferenced').write_text('invented')
    with pytest.raises(RuntimeError, match='CAPTURE_FILE_INVENTORY_CONFLICT'): run()
    Path('inputs/bundle/unreferenced').unlink()
    name = next(iter(f)); source = Path('inputs/bundle/sources', name)
    source.unlink(); source.symlink_to(Path('inputs/config.yaml').resolve())
    with pytest.raises(RuntimeError, match='CAPTURE_SYMLINK_PATH'): run()
    assert not Path('outputs/proposal').exists()


def test_write_failure_does_not_publish_completion_and_preserves_inputs(monkeypatch):
    local(); before = Path('inputs/config.yaml').read_bytes()
    original = bd.atomic_private_yaml
    def fail_completion(path, value):
        if Path(path).name == 'qualification.yaml': raise OSError('synthetic publication failure')
        original(path, value)
    monkeypatch.setattr(bd, 'atomic_private_yaml', fail_completion)
    with pytest.raises(OSError): run()
    assert not Path('outputs/proposal/qualification.yaml').exists()
    assert Path('inputs/config.yaml').read_bytes() == before
    with pytest.raises(RuntimeError, match='CAPTURE_OUTPUT_EXISTS'): run()


def test_saved_proposal_can_enter_existing_prepare_with_explicit_common_root():
    local(); run()
    result = bd.prepare_local_plan('outputs/proposal/prepare-proposal.yaml', '.', 100000, 32)
    assert result['prepared_activities'] == 3 and result['import_ready'] is False

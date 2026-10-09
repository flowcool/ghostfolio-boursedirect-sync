import copy
import hashlib
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_frozen_review import bundle as frozen_bundle
from test_frozen_lab_sequence import backend, posts, snapshot


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DRY_RUN', '0')
    monkeypatch.delenv('GHOST_HOST', raising=False)
    monkeypatch.delenv('GHOST_SESSION_BEARER', raising=False)
    def forbidden(*args, **kwargs): raise AssertionError('No real sockets or HTTPS')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(bd.http.client, 'HTTPSConnection', forbidden)


def dump(value): return yaml.safe_dump(value, sort_keys=False).encode()
def sha(raw): return hashlib.sha256(raw).hexdigest()


def fixture(**kwargs):
    report, config, captures = frozen_bundle(**kwargs)
    prepare = Path('inputs/import-config.yaml').read_bytes()
    docs, _ = bd.capture_preparation_sources(prepare, 'inputs', 100000, 32)
    artifact = bd.parse_keyed_yaml(report)
    declaration = {'schema_version': 1,
        'artifact_kind': 'operator_execution_declaration_not_authenticated_approval',
        'review_sha256': sha(report), 'prepare_config': 'import-config.yaml',
        'prepare_config_sha256': sha(prepare), 'allowed_origin': 'https://synthetic.example:8443',
        'account_key': artifact['account_key'], 'target_account_id': artifact['target_account_id'],
        'snapshot_sha256': sha(captures['snapshot']), 'destination_version': '3.81.0',
        'display_timezone': 'Europe/Paris', 'confirmations': {k: {'confirmed': True,
            'confirmed_by': 'owned synthetic fixture', 'reference': 'synthetic fixture record, not real authorization'}
            for k in ('source_acceptance', 'destination_validation', 'security_review',
                      'recovery_procedure', 'exclusive_access', 'write_authorization')}}
    raw = dump(declaration)
    bundle = {'declaration': raw, 'declaration_sha256': sha(raw), 'review': report,
              'review_sha256': sha(report), 'config': config, 'captures': captures,
              'prepare_config': prepare, 'documents': docs}
    Path('inputs/report.yaml').write_bytes(report)
    Path('inputs/execution.yaml').write_bytes(raw)
    store = {'rows': json.loads(captures['snapshot'])['activities'], 'calls': [], 'observed': []}
    return bundle, declaration, store


def dispatch(bundle, store, **kwargs):
    return bd.dispatch_qualified_application('application-state', 'application-outputs', bundle,
                                            100000, 32, kwargs.pop('request', backend(store)), **kwargs)


def cli(bundle, *extra):
    return ['apply', '--config', 'inputs/review.yaml', '--review', 'inputs/report.yaml',
            '--review-sha256', bundle['review_sha256'], '--input-root', 'inputs', '--max-bytes', '100000',
            '--execute', '--execution', 'inputs/execution.yaml', '--execution-sha256', bundle['declaration_sha256'],
            '--max-depth', '32', '--timeout', '10', *extra]


def repin(bundle, declaration):
    bundle['declaration'] = dump(declaration)
    bundle['declaration_sha256'] = sha(bundle['declaration'])
    Path('inputs/execution.yaml').write_bytes(bundle['declaration'])


def retained():
    return {str(p): (p.read_bytes(), p.stat().st_mode & 0o777) for d in ('inputs', 'state', 'outputs')
            for p in Path(d).rglob('*') if p.is_file()}


@pytest.mark.parametrize('change', ['bool_schema', 'extra', 'missing', 'false', 'int_confirmation',
    'extra_confirmation', 'missing_confirmation', 'blank_reference', 'numeric_reviewer', 'bad_pin',
    'stale_report', 'other_account', 'other_target', 'other_snapshot', 'http', 'path_origin',
    'version', 'timezone', 'config_pin', 'absolute_path'])
def test_declaration_refusals_before_callbacks_or_mutations(change, monkeypatch):
    bundle, dec, store = fixture()
    if change == 'bool_schema': dec['schema_version'] = True
    elif change == 'extra': dec['unexpected'] = True
    elif change == 'missing': del dec['allowed_origin']
    elif change == 'false': dec['confirmations']['source_acceptance']['confirmed'] = False
    elif change == 'int_confirmation': dec['confirmations']['write_authorization']['confirmed'] = 1
    elif change == 'extra_confirmation': dec['confirmations']['other'] = dec['confirmations']['source_acceptance']
    elif change == 'missing_confirmation': del dec['confirmations']['security_review']
    elif change == 'blank_reference': dec['confirmations']['recovery_procedure']['reference'] = ' '
    elif change == 'numeric_reviewer': dec['confirmations']['exclusive_access']['confirmed_by'] = 1
    elif change == 'stale_report': dec['review_sha256'] = '0' * 64
    elif change == 'other_account': dec['account_key'] = 'other'
    elif change == 'other_target': dec['target_account_id'] = 'other'
    elif change == 'other_snapshot': dec['snapshot_sha256'] = '0' * 64
    elif change == 'http': dec['allowed_origin'] = 'http://synthetic.example'
    elif change == 'path_origin': dec['allowed_origin'] += '/secret'
    elif change == 'version': dec['destination_version'] = '3.80.2'
    elif change == 'timezone': dec['display_timezone'] = 'UTC'
    elif change == 'config_pin': dec['prepare_config_sha256'] = '0' * 64
    elif change == 'absolute_path': dec['prepare_config'] = '/synthetic.yaml'
    repin(bundle, dec)
    if change == 'bad_pin': bundle['declaration_sha256'] = '0' * 64
    before = retained()
    with pytest.raises(RuntimeError): dispatch(bundle, store)
    def forbidden(*args, **kwargs): raise AssertionError('No credentials/transport before qualification')
    monkeypatch.setattr(bd, 'make_ghostfolio_request', forbidden)
    assert bd.main(cli(bundle)) == 1
    assert store['calls'] == [] and before == retained()
    assert not Path('application-state').exists() and not Path('application-outputs').exists()


def test_source_and_financial_change_fail_even_with_fresh_declaration():
    bundle, dec, store = fixture()
    bundle['documents']['month-a']['statement'] += b'\n'
    repin(bundle, dec)
    with pytest.raises(RuntimeError, match='PREPARED_SOURCE_CONTENT_CONFLICT'):
        dispatch(bundle, store)
    assert store['calls'] == []


def test_evidence_only_change_requires_current_config_pin():
    bundle, dec, store = fixture()
    config = bd.parse_keyed_yaml(bundle['prepare_config'])
    for mapping in config['mappings'].values(): mapping['currency_evidence'] = 'new synthetic review reference'
    bundle['prepare_config'] = dump(config)
    with pytest.raises(RuntimeError, match='APPLICATION_PREPARATION_DIGEST_CONFLICT'):
        dispatch(bundle, store)
    dec['prepare_config_sha256'] = sha(bundle['prepare_config'])
    repin(bundle, dec)
    assert bd.validate_qualified_application(bundle, 100000, 32)['wires']
    assert store['calls'] == []  # No historical immutability claim or automatic permission.


def read_archive(path):
    manifest = bd.parse_keyed_yaml((path / 'manifest.yaml').read_bytes())
    roles = {role: (path / entry['file']).read_bytes() for role, entry in manifest['roles'].items()}
    assert all(sha(roles[role]) == entry['sha256'] for role, entry in manifest['roles'].items())
    docs = {alias: {'statement': roles[entry['statement']], 'notes': [roles[n] for n in entry['notes']]}
            for alias, entry in manifest['documents'].items()}
    return {'declaration': roles['declaration'], 'declaration_sha256': manifest['declaration_sha256'],
            'review': roles['review'], 'review_sha256': manifest['review_sha256'], 'config': roles['config'],
            'captures': {k: roles[k] for k in ('prepared', 'snapshot', 'resolutions', 'history_evidence')},
            'prepare_config': roles['prepare_config'], 'documents': docs}


def test_complete_archive_before_first_callback_and_cold_replay_after_originals_change():
    bundle, _, store = fixture()
    real = backend(store)
    def request(method, path, body):
        archives = list(Path('application-outputs').glob('application-*'))
        assert len(archives) == 1
        assert read_archive(archives[0]) == bundle
        assert bd.validate_qualified_application(read_archive(archives[0]), 100000, 32)['wires']
        return real(method, path, body)
    result = dispatch(bundle, store, request=request)
    assert result == {'accepted_events': 3, 'readback': snapshot(store), 'import_ready': False}
    assert [c[0] for c in store['calls']] == ['GET', 'POST', 'GET'] * 3
    archive = next(Path('application-outputs').glob('application-*'))
    for path in Path('inputs').glob('*'):
        if path.is_file(): path.write_bytes(b'changed originals')
    assert bd.validate_qualified_application(read_archive(archive), 100000, 32)['artifact']['wire']
    assert len(list(archive.glob('event-*.readback.json'))) == 3
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in archive.iterdir())
    assert archive.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize('stage', ['initialization', 'observer', 'second_timeout'])
def test_partial_failures_retain_fences_and_archive(stage, monkeypatch):
    bundle, _, store = fixture()
    real_write = bd.atomic_private_bytes
    def write(path, raw):
        if stage == 'initialization' and Path(path).name == 'snapshot.bytes': raise OSError('private failure')
        if stage == 'observer' and Path(path).name == 'event-0.readback.json': raise OSError('private failure')
        return real_write(path, raw)
    monkeypatch.setattr(bd, 'atomic_private_bytes', write)
    with pytest.raises((OSError, RuntimeError)):
        dispatch(bundle, store, request=backend(store, failure=stage == 'second_timeout'))
    archive = next(Path('application-outputs').glob('application-*'))
    if stage == 'initialization':
        assert store['calls'] == [] and not Path('application-state').exists()
    else:
        assert read_archive(archive) == bundle
        journal = bd.parse_keyed_yaml(next(Path('application-state').glob('writes-*.yaml')).read_bytes())
        states = [v['state'] for v in journal['intents'].values()]
        assert states.count('confirmed') == 1
        assert len(posts(store)) == (2 if stage == 'second_timeout' else 1)
        if stage == 'second_timeout':
            assert states.count('uncertain') == 1
            assert (archive / 'event-0.readback.json').exists()
            previous_calls = list(store['calls'])
            with pytest.raises(RuntimeError): dispatch(bundle, store)
            assert previous_calls == store['calls']


def test_noop_no_callbacks_credentials_archive_state():
    bundle, _, store = fixture(existing=True)
    result = bd.dispatch_qualified_application('application-state', 'application-outputs', bundle, 100000, 32, None)
    assert result['accepted_events'] == 0 and result['readback'] == bundle['captures']['snapshot']
    assert not Path('application-state').exists() and not Path('application-outputs').exists()
    assert bd.main(cli(bundle)) == 2


def fake_https(monkeypatch, store, failure=False):
    request = backend(store, failure)
    def connection(host, port, timeout, context):
        assert host == 'synthetic.example' and port == 8443 and timeout == 10
        assert context.check_hostname
        response = {}
        def send(method, path, body, headers):
            assert headers['Authorization'] == 'Bearer synthetic.header.signature'
            response['status'], response['raw'] = request(method, path, body)
        return SimpleNamespace(request=send, close=lambda: None, getresponse=lambda: SimpleNamespace(
            status=response['status'], getheader=lambda name, default='': {'Content-Type': 'application/json'}.get(name, default),
            read=lambda limit: response['raw'][:limit]))
    monkeypatch.setattr(bd.http.client, 'HTTPSConnection', connection)
    monkeypatch.setenv('GHOST_HOST', 'https://synthetic.example:8443')
    monkeypatch.setenv('GHOST_SESSION_BEARER', 'synthetic.header.signature')


def test_public_cli_mock_https_happy_exact_three_confirmations(monkeypatch, capsys):
    bundle, _, store = fixture()
    fake_https(monkeypatch, store)
    assert bd.main(cli(bundle)) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result['dry_run'] is False and result['accepted_events'] == 3 and result['import_ready'] is False
    assert len(posts(store)) == 3
    assert 'synthetic.example' not in output and 'FR000' not in output and 'signature' not in output
    assert len(list(Path('outputs').glob('application-*'))) == 1


def test_public_timeout_after_creation_is_fenced_without_retry(monkeypatch):
    bundle, _, store = fixture()
    fake_https(monkeypatch, store, failure=True)
    assert bd.main(cli(bundle)) == 1
    calls = list(store['calls'])
    assert len(posts(store)) == 2
    assert bd.main(cli(bundle)) == 1 and calls == store['calls']


@pytest.mark.parametrize('dry_run,execute', [('1', True), ('1', False), ('0', False)])
def test_execution_only_bad_options_ignored_under_preview(dry_run, execute, monkeypatch):
    bundle, _, store = fixture()
    args = cli(bundle)
    if not execute: args.remove('--execute')
    args[args.index('--execution') + 1] = 'unreadable-missing.yaml'
    args[args.index('--max-depth') + 1] = 'not-an-integer'
    args[args.index('--timeout') + 1] = 'not-an-integer'
    monkeypatch.setenv('DRY_RUN', dry_run)
    before = retained()
    assert bd.main(args) == 2 and before == retained() and store['calls'] == []


@pytest.mark.parametrize('state_name', ['target_lock', 'namespace_lock', 'binding', 'journal'])
@pytest.mark.parametrize('role', ['declaration', 'review', 'config', 'prepare_config', 'statement', 'last_note', 'prepared', 'snapshot', 'resolutions', 'history_evidence'])
def test_all_input_hardlinks_against_all_write_destinations_preserved(state_name, role, monkeypatch):
    bundle, _, store = fixture()
    dec = bd.parse_keyed_yaml(bundle['declaration'])
    roles = {'declaration': Path('inputs/execution.yaml'), 'review': Path('inputs/report.yaml'),
             'config': Path('inputs/review.yaml'), 'prepare_config': Path('inputs/import-config.yaml'),
             'statement': Path('inputs/statement.html'), 'last_note': Path('inputs/sell.html')}
    roles.update({k: Path('inputs') / bd.parse_keyed_yaml(bundle['config'])[k]
                  for k in ('prepared', 'snapshot', 'resolutions', 'history_evidence')})
    target = sha(dec['target_account_id'].encode())
    name = {'target_lock': 'prepare-' + target + '.lock', 'namespace_lock': 'account-' + dec['account_key'] + '.lock',
            'binding': 'write-binding-' + dec['account_key'] + '.yaml', 'journal': 'writes-' + target + '.yaml'}[state_name]
    destination = Path('state') / name
    if destination.exists(): destination.unlink()
    destination.hardlink_to(roles[role])
    before = retained()
    before_modes = {d: Path(d).stat().st_mode for d in ('state', 'outputs')}
    assert bd.main(cli(bundle)) == 1
    assert retained() == before and {d: Path(d).stat().st_mode for d in before_modes} == before_modes
    assert not list(Path('outputs').glob('application-*')) and store['calls'] == []


@pytest.mark.parametrize('scope', ['archive_root_symlink', 'archive_ancestor_symlink', 'state_root_symlink', 'state_ancestor_symlink', 'state_file', 'archive_file'])
def test_unsafe_directory_namespace_before_permissions_or_callbacks(scope):
    bundle, _, store = fixture()
    Path('unrelated').mkdir(mode=0o755)
    Path('unrelated/keep').write_bytes(b'private unchanged unrelated')
    state, output = 'application-state', 'application-outputs'
    if scope == 'archive_root_symlink': Path(output).symlink_to(Path('unrelated').resolve())
    elif scope == 'state_root_symlink': Path(state).symlink_to(Path('unrelated').resolve())
    elif scope == 'archive_ancestor_symlink':
        Path('link').symlink_to(Path('unrelated').resolve()); output = 'link/output'
    elif scope == 'state_ancestor_symlink':
        Path('link').symlink_to(Path('unrelated').resolve()); state = 'link/state'
    elif scope == 'state_file': Path(state).write_bytes(b'unchanged')
    else: Path(output).write_bytes(b'unchanged')
    before = retained()
    with pytest.raises(RuntimeError):
        bd.dispatch_qualified_application(state, output, bundle, 100000, 32, backend(store))
    assert store['calls'] == [] and before == retained()
    assert Path('unrelated').stat().st_mode & 0o777 == 0o755
    assert list(Path('unrelated').iterdir()) == [Path('unrelated/keep')]


def test_stale_remote_baseline_keeps_complete_archive_but_sends_no_post():
    bundle, _, store = fixture()
    store['rows'].clear()
    with pytest.raises(RuntimeError, match='LAB_DISPATCH_BASELINE_CHANGED'):
        dispatch(bundle, store)
    assert len(posts(store)) == 0 and len(store['calls']) == 1
    assert read_archive(next(Path('application-outputs').glob('application-*'))) == bundle


def test_financial_shortfall_before_credentials_or_archive(monkeypatch):
    bundle, _, store = fixture(missing=True)
    def forbidden(*args, **kwargs): raise AssertionError('No credential factory')
    monkeypatch.setattr(bd, 'make_ghostfolio_request', forbidden)
    before = retained()
    assert bd.main(cli(bundle)) == 1 and retained() == before
    assert store['calls'] == [] and not list(Path('outputs').glob('application-*'))


def test_execute_export_refused_before_new_input_capture(monkeypatch):
    bundle, _, _ = fixture()
    def forbidden(*args, **kwargs): raise AssertionError('No input capture')
    monkeypatch.setattr(bd, 'capture_local_application', forbidden)
    assert bd.main(cli(bundle, '--export', 'outputs/proposal.json')) == 1


def test_dryrun_override_retains_export_even_with_malformed_execution_options(monkeypatch):
    bundle, _, _ = fixture()
    monkeypatch.setenv('DRY_RUN', '1')
    args = cli(bundle, '--export', 'outputs/proposal.json')
    args[args.index('--timeout') + 1] = 'bad'
    args[args.index('--execution') + 1] = 'missing'
    assert bd.main(args) == 2
    assert Path('outputs/proposal.json').read_bytes() == bd.parse_keyed_yaml(bundle['review'])['wire']['body_utf8'].encode()


def test_public_execution_captures_every_input_once(monkeypatch):
    bundle, _, store = fixture()
    fake_https(monkeypatch, store)
    real, reads = bd.read_local_bytes, []
    def capture(path, root, limit):
        if str(path).startswith('inputs/'):
            reads.append(str(path))
        return real(path, root, limit)
    monkeypatch.setattr(bd, 'read_local_bytes', capture)
    assert bd.main(cli(bundle)) == 0
    assert len(reads) == len(set(reads)) == 11


@pytest.mark.parametrize('kind', ['negative_depth', 'bool_depth', 'negative_bytes', 'bool_bytes', 'extra_bundle', 'missing_bundle', 'oversize_declaration', 'oversize_prepare_config'])
def test_bundle_and_limits_refuse_before_callbacks(kind):
    bundle, _, store = fixture()
    max_bytes, depth = 100000, 32
    if kind == 'negative_depth': depth = -1
    elif kind == 'bool_depth': depth = True
    elif kind == 'negative_bytes': max_bytes = -1
    elif kind == 'bool_bytes': max_bytes = True
    elif kind == 'extra_bundle': bundle['unused'] = b''
    elif kind == 'missing_bundle': del bundle['documents']
    elif kind == 'oversize_declaration': bundle['declaration'] = b'x' * 100001
    else: bundle['prepare_config'] = b'x' * 100001
    with pytest.raises(RuntimeError):
        bd.dispatch_qualified_application('application-state', 'application-outputs', bundle, max_bytes, depth, backend(store))
    assert store['calls'] == [] and not Path('application-state').exists() and not Path('application-outputs').exists()


def test_qualification_is_pure_with_frozen_current_source_bytes(monkeypatch):
    bundle, _, _ = fixture()
    original = copy.deepcopy(bundle)
    def forbidden(*args, **kwargs): raise AssertionError('Pure preflight must not touch filesystem, locks or transport')
    for name in ('read_local_bytes', 'atomic_private_bytes', 'atomic_private_yaml', 'make_ghostfolio_request'):
        monkeypatch.setattr(bd, name, forbidden)
    monkeypatch.setattr(bd.os, 'open', forbidden)
    monkeypatch.setattr(bd.fcntl, 'flock', forbidden)
    assert len(bd.validate_qualified_application(bundle, 100000, 32)['wires']) == 3
    assert bundle == original


def test_public_wrong_origin_refuses_before_archive_or_state_mutation(monkeypatch):
    bundle, _, _ = fixture()
    before = retained()
    monkeypatch.setenv('GHOST_HOST', 'https://other.invalid')
    monkeypatch.setenv('GHOST_SESSION_BEARER', 'synthetic.header.signature')
    assert bd.main(cli(bundle)) == 1 and before == retained()
    assert not list(Path('outputs').glob('application-*'))

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest
import yaml
import boursedirect_to_ghostfolio as bd
from test_contract_notes import paired_statement, note_source
from test_conversion import inputs
from test_identity import ACCOUNT


@pytest.fixture(autouse=True)
def isolated_files_and_no_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Tests must not use network')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


def setup():
    root = Path('inputs')
    root.mkdir(mode=0o700)
    (root / 'statement.html').write_text(paired_statement().replace('windows-1252', 'utf-8'))
    (root / 'buy.html').write_text(note_source())
    (root / 'sell.html').write_text(note_source(True))
    _, _, account, mappings = inputs()
    account['account_key'] = ACCOUNT
    config = {'schema_version': 1, 'account': account, 'mappings': mappings,
              'documents': {'month-a': {'statement': 'statement.html', 'notes': ['buy.html', 'sell.html']}}}
    write(config)
    return config


def write(config):
    Path('inputs/import-config.yaml').write_text(yaml.safe_dump(config, sort_keys=False))


def run():
    return bd.prepare_local_plan('inputs/import-config.yaml', 'inputs', 100000, 32)


def artifact():
    return Path('outputs/prepared-' + ACCOUNT + '.yaml')


def journal(config):
    digest = hashlib.sha256(config['account']['target_account_id'].encode()).hexdigest()
    return Path('state/ledger-' + digest + '.yaml')


def test_end_to_end_preparation_produces_private_keyed_internal_artifact():
    config = setup()
    summary = run()
    assert summary['prepared_activities'] == 3 and summary['statement_periods'] == 1
    assert summary['import_ready'] is False
    saved = yaml.safe_load(artifact().read_text())
    assert saved['artifact_kind'] == 'internal_activity_review_not_api_payload'
    assert len(saved['activities']) == 3
    assert all(k == v['id'] and v['import_ready'] is False for k, v in saved['activities'].items())
    assert all(isinstance(v['quantity'], str) and isinstance(v['unit_price'], str) for v in saved['activities'].values())
    assert saved['source_digests']['month-a']['statement'] == hashlib.sha256(Path('inputs/statement.html').read_bytes()).hexdigest()
    assert yaml.safe_load(journal(config).read_text())['binding'] == config['account']
    assert Path('state').stat().st_mode & 0o777 == 0o700
    assert Path('outputs').stat().st_mode & 0o777 == 0o700
    assert artifact().stat().st_mode & 0o777 == 0o600
    assert journal(config).stat().st_mode & 0o777 == 0o600
    assert not list(Path('outputs').glob('.*'))


def test_repeat_and_file_rename_preserve_exact_ids():
    config = setup()
    run()
    before = yaml.safe_load(artifact().read_text())['activities']
    Path('inputs/statement.html').rename('inputs/renamed.html')
    config['documents']['month-a']['statement'] = 'renamed.html'
    write(config)
    run()
    assert before == yaml.safe_load(artifact().read_text())['activities']


def test_duplicate_period_rejected_before_replacing_review_plan():
    config = setup()
    run()
    saved = artifact().read_bytes()
    config['documents']['another-month'] = copy.deepcopy(config['documents']['month-a'])
    write(config)
    with pytest.raises(RuntimeError, match='DUPLICATE_STATEMENT_PERIOD'):
        run()
    assert artifact().read_bytes() == saved


def test_changed_source_label_blocks_even_if_notes_match():
    config = setup()
    run()
    saved = artifact().read_bytes()
    # A stable original source label is identity data, even if numbers still match.
    p = Path('inputs/statement.html')
    p.write_text(p.read_text().replace('SYNTHETIC ALPHA', 'SYNTHETIC ALPHA CORRECTED'))
    with pytest.raises(RuntimeError, match='STATEMENT_REVISION_CONFLICT'):
        run()
    assert artifact().read_bytes() == saved


def test_migration_required_for_changed_account_namespace_same_target():
    config = setup()
    run()
    saved = artifact().read_bytes()
    config['account']['account_key'] = 'a2c45ef7-0a84-481d-9f4e-0862e44ea26f'
    write(config)
    with pytest.raises(RuntimeError, match='ACCOUNT_BINDING_MIGRATION_REQUIRED'):
        run()
    assert artifact().read_bytes() == saved


def test_target_lock_prevents_concurrent_write():
    config = setup()
    run()
    saved = artifact().read_bytes()
    digest = hashlib.sha256(config['account']['target_account_id'].encode()).hexdigest()
    with open('state/prepare-' + digest + '.lock', 'r+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='PREPARATION_TARGET_LOCKED'):
            run()
    assert artifact().read_bytes() == saved
    assert run()['prepared_activities'] == 3


@pytest.mark.parametrize('content,error', [
    ('account: first\naccount: second\n', 'YAML_DUPLICATE_KEY'),
    ('account: &owned {}\nmapping: *owned\n', 'YAML_ALIAS_NOT_SUPPORTED'),
    ('true: value\n', 'YAML_STRING_KEYS_REQUIRED'),
    ('!!python/object/apply:os.system [echo synthetic]\n', 'INVALID_KEYED_YAML'),
])
def test_unsafe_or_ambiguous_yaml_configuration_rejected(content, error):
    setup()
    Path('inputs/import-config.yaml').write_text(content)
    with pytest.raises(RuntimeError, match='^' + error + '$'):
        run()
    assert not Path('outputs').exists() and not Path('state').exists()


def test_missing_mappings_and_unknown_periods_do_not_replace_artifact():
    config = setup()
    run()
    saved = artifact().read_bytes()
    config['mappings'] = {}
    write(config)
    with pytest.raises(RuntimeError, match='SECURITY_MAPPING_MISSING'):
        run()
    assert artifact().read_bytes() == saved


def test_input_escape_is_rejected_before_output_creation():
    config = setup()
    Path('outside.html').write_text(note_source())
    config['documents']['month-a']['notes'] = ['../outside.html']
    write(config)
    with pytest.raises(RuntimeError, match='INPUT_OUTSIDE_ROOT'):
        run()
    assert not Path('outputs').exists()


def test_symlink_output_cannot_overwrite_unrelated_file():
    setup()
    Path('outputs').mkdir(mode=0o700)
    outside = Path('private-unrelated.yaml')
    outside.write_text('UNRELATED PRIVATE CONTENT')
    artifact().symlink_to(outside.resolve())
    with pytest.raises(RuntimeError, match='SYMLINK_PRIVATE_FILE'):
        run()
    assert outside.read_text() == 'UNRELATED PRIVATE CONTENT'


def test_cli_diagnostics_only_counts_and_blockers(capsys):
    setup()
    status = bd.main(['prepare', '--config', 'inputs/import-config.yaml', '--input-root', 'inputs',
                      '--max-bytes', '100000', '--max-depth', '32'])
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert status == 2 and summary['prepared_activities'] == 3
    assert 'FR000' not in output and 'synthetic-' not in output and '0.45' not in output
    assert summary['blockers'] == ['REMOTE_ADOPTION_UNVERIFIED', 'ISOLATED_API_CONTRACT_UNVERIFIED']


def test_atomic_write_failure_retains_previous_artifact_and_cleans_temp(monkeypatch):
    config = setup()
    run()
    before = artifact().read_bytes()
    real_replace = os.replace
    def replace(source, target):
        if Path(target).parent.name == 'outputs':
            raise OSError('synthetic disk failure')
        return real_replace(source, target)
    monkeypatch.setattr(bd.os, 'replace', replace)
    with pytest.raises(OSError):
        run()
    assert artifact().read_bytes() == before
    assert not list(Path('outputs').glob('.*'))
    assert yaml.safe_load(journal(config).read_text())['binding'] == config['account']


def test_config_rejects_credentials_or_unknown_top_level_fields():
    config = setup()
    config['GHOST_TOKEN'] = 'SYNTHETIC NONSECRET VALUE'
    write(config)
    with pytest.raises(RuntimeError, match='INVALID_PREPARATION_CONFIGURATION'):
        run()


def test_changing_target_cannot_reuse_account_namespace_silently():
    config = setup()
    run()
    saved = artifact().read_bytes()
    config['account']['target_account_id'] = 'different-synthetic-target'
    write(config)
    with pytest.raises(RuntimeError, match='ACCOUNT_BINDING_MIGRATION_REQUIRED'):
        run()
    assert artifact().read_bytes() == saved


def test_unsupported_period_is_not_prepared_even_with_matched_trade_notes():
    setup()
    p = Path('inputs/statement.html')
    p.write_text(p.read_text().replace('VTE CPT SYNTHETIC ALPHA', 'UNKNOWN SYNTHETIC LABEL'))
    with pytest.raises(RuntimeError, match='UNSUPPORTED_OPERATION_PERIOD'):
        run()
    assert not Path('outputs').exists()


def test_public_complete_synthetic_example_runs_in_isolated_workdir():
    import shutil
    fixture_root = Path(__file__).resolve().parent / 'fixtures'
    Path('inputs').mkdir(mode=0o700)
    for name in ['import-config-synthetic.yaml', 'statement-paired-synthetic.html',
                 'note-buy-synthetic.html', 'note-multi-sell-synthetic.html']:
        shutil.copyfile(fixture_root / name, Path('inputs') / name)
    summary = bd.prepare_local_plan('inputs/import-config-synthetic.yaml', 'inputs', 100000, 32)
    assert summary['prepared_activities'] == 3 and summary['import_ready'] is False


@pytest.mark.parametrize('destination', ['artifact', 'ledger', 'binding'])
@pytest.mark.parametrize('source', ['config', 'statement', 'buy', 'sell'])
def test_preparation_publications_cannot_replace_any_captured_input(destination, source):
    config = setup()
    for entry in config['documents'].values():
        entry['statement'] = 'inputs/' + entry['statement']
        entry['notes'] = ['inputs/' + path for path in entry['notes']]
    Path('outputs').mkdir(mode=0o700)
    Path('state').mkdir(mode=0o700)
    destinations = {'artifact': artifact(), 'ledger': journal(config),
                    'binding': Path('state/binding-' + ACCOUNT + '.yaml')}
    target = destinations[destination]
    config_path = Path('inputs/import-config.yaml')
    if source == 'config':
        config_path = target
    else:
        entry = config['documents']['month-a']
        path = Path('inputs/' + source + '.html')
        target.write_bytes(path.read_bytes())
        if source == 'statement':
            entry['statement'] = str(target)
        else:
            entry['notes'][0 if source == 'buy' else 1] = str(target)
    config_path.write_text(yaml.safe_dump(config))
    before = {str(p): p.read_bytes() for d in ('inputs', 'outputs', 'state')
              for p in Path(d).rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match=r'^OUTPUT_INPUT_COLLISION$'):
        bd.prepare_local_plan(config_path, '.', 100000, 32)
    after = {str(p): p.read_bytes() for d in ('inputs', 'outputs', 'state')
             for p in Path(d).rglob('*') if p.is_file()}
    assert before == after


@pytest.mark.parametrize('destination', ['artifact', 'ledger', 'binding'])
def test_preparation_rejects_hardlink_publication_alias_before_state_changes(destination):
    config = setup()
    run()
    targets = {'artifact': artifact(), 'ledger': journal(config),
               'binding': Path('state/binding-' + ACCOUNT + '.yaml')}
    target = targets[destination]
    target.unlink()
    target.hardlink_to(Path('inputs/statement.html'))
    before = {str(p): p.read_bytes() for d in ('inputs', 'outputs', 'state')
              for p in Path(d).rglob('*') if p.is_file()}
    with pytest.raises(RuntimeError, match=r'^OUTPUT_INPUT_COLLISION$'):
        run()
    assert before == {str(p): p.read_bytes() for d in ('inputs', 'outputs', 'state')
                      for p in Path(d).rglob('*') if p.is_file()}

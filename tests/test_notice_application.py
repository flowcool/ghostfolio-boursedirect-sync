import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

import boursedirect_to_ghostfolio as bd
from test_daily_notices import pure_sources
from test_qualified_application import fixture, isolated, dump, sha, dispatch
from test_frozen_lab_sequence import posts


def notice_bundle():
    bundle, declaration, store = fixture()
    account, mappings, notes, captured = pure_sources()
    config = {'schema_version': 1, 'source_mode': 'notices', 'account': account,
              'mappings': mappings, 'as_of': '2026-10-12',
              'notices': {'mixed': {'date': '2026-09-17', 'document': 'notice.html'}}}
    docs = {'mixed': {'notice': captured['mixed']}}
    raw = dump(config)
    artifact = bd.compute_prepared_notices(raw, docs, 100000, 32)['artifact']
    baseline = b'{"count":0,"activities":[]}'
    history = {'kind': 'complete_acquisition_history', 'target_account_id': account['target_account_id'],
               'snapshot_sha256': sha(baseline), 'confirmed_by': 'synthetic owned lab', 'reference': 'empty owned account'}
    bundle['captures'] = {'prepared': dump(artifact), 'snapshot': baseline,
                          'resolutions': b'{}', 'history_evidence': dump(history)}
    review_config = {'schema_version': 3, 'adoption_mode': 'certain_unique', 'as_of': '2026-10-12',
                    'prepared': 'prepared.yaml', 'snapshot': 'snapshot.json',
                    'resolutions': 'resolutions.yaml', 'history_evidence': 'history.yaml'}
    bundle['config'] = dump(review_config)
    bundle['prepare_config'] = raw
    bundle['documents'] = docs
    bundle['review'] = dump(bd.compute_offline_review(bundle['config'], bundle['captures'], 100000))
    bundle['review_sha256'] = sha(bundle['review'])
    declaration.update(account_key=account['account_key'], target_account_id=account['target_account_id'],
                       snapshot_sha256=sha(baseline), prepare_config_sha256=sha(raw), review_sha256=bundle['review_sha256'])
    bundle['declaration'] = dump(declaration)
    bundle['declaration_sha256'] = sha(bundle['declaration'])
    store.update(rows=[], calls=[], observed=[])
    return bundle, store


def test_notice_source_application_reuses_per_event_intents_and_archive():
    bundle, store = notice_bundle()
    result = dispatch(bundle, store)
    assert result['accepted_events'] == 2 and len(posts(store)) == 2
    archives = list(Path('application-outputs').glob('application-*'))
    assert len(archives) == 1
    manifest = yaml.safe_load((archives[0] / 'manifest.yaml').read_bytes())
    assert manifest['documents'] == {'mixed': {'notice': 'source-0-notice'}}
    role = manifest['roles']['source-0-notice']
    assert (archives[0] / role['file']).read_bytes() == bundle['documents']['mixed']['notice']
    assert role['sha256'] == sha(bundle['documents']['mixed']['notice'])


@pytest.mark.parametrize('change', ['whitespace', 'price', 'mapping', 'clock', 'extra_capture'])
def test_notice_source_change_refuses_before_any_request_or_persistence(change):
    bundle, store = notice_bundle()
    if change == 'whitespace':
        bundle['documents']['mixed']['notice'] += b' '
    elif change == 'price':
        bundle['documents']['mixed']['notice'] = bundle['documents']['mixed']['notice'].replace(b'COURS :', b'OTHER :')
    elif change == 'extra_capture':
        bundle['documents']['mixed']['statement'] = b'not a statement'
    else:
        config = yaml.safe_load(bundle['prepare_config'])
        if change == 'mapping': next(iter(config['mappings'].values()))['symbol'] = 'OTHER.PA'
        else: config['as_of'] = '2026-12-16'
        bundle['prepare_config'] = dump(config)
        declaration = yaml.safe_load(bundle['declaration'])
        declaration['prepare_config_sha256'] = sha(bundle['prepare_config'])
        bundle['declaration'] = dump(declaration); bundle['declaration_sha256'] = sha(bundle['declaration'])
    with pytest.raises(RuntimeError):
        dispatch(bundle, store)
    assert store['calls'] == [] and not Path('application-outputs').exists()


def test_local_notice_capture_reads_only_original_notices():
    bundle, _ = notice_bundle()
    Path('inputs/notice.html').write_bytes(bundle['documents']['mixed']['notice'])
    captures, paths = bd.capture_preparation_sources(bundle['prepare_config'], 'inputs', 100000, 32)
    assert captures == bundle['documents'] and paths == [Path('inputs/notice.html')]
    assert bd.validate_prepared_sources(bundle['captures']['prepared'], bundle['prepare_config'], captures, 100000, 32)


def test_present_unsupported_notice_refuses_application_while_preview_remains_diagnostic():
    bundle, _ = notice_bundle()
    bundle['documents']['mixed']['notice'] = bundle['documents']['mixed']['notice'].replace(b'COUPONS', b'UNKNOWN')
    with pytest.raises(RuntimeError, match='^NOTICE_APPLICATION_SOURCE_UNQUALIFIED$'):
        bd.compute_prepared_notices(bundle['prepare_config'], bundle['documents'], 100000, 32)


def test_prepare_cli_publishes_notice_artifact_and_preserves_revision_guard(capsys):
    bundle, _ = notice_bundle()
    Path('inputs/notice.html').write_bytes(bundle['documents']['mixed']['notice'])
    Path('inputs/notices.yaml').write_bytes(bundle['prepare_config'])
    args = ['prepare', '--config', 'inputs/notices.yaml', '--input-root', 'inputs', '--max-bytes', '100000', '--max-depth', '32']
    assert bd.main(args) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary['prepared_activities'] == 2 and summary['statement_periods'] == 0
    output = Path('outputs', 'prepared-' + yaml.safe_load(bundle['prepare_config'])['account']['account_key'] + '.yaml')
    original = output.read_bytes()
    assert bd.validate_prepared_sources(original, bundle['prepare_config'], bundle['documents'], 100000, 32)
    assert bd.main(args) == 2
    capsys.readouterr()
    assert output.read_bytes() == original
    Path('inputs/notice.html').write_bytes(bundle['documents']['mixed']['notice'] + b' ')
    before = {p: p.read_bytes() for d in ('state', 'outputs') for p in Path(d).glob('*')}
    assert bd.main(args) == 1
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_application_cli_can_capture_and_validate_notice_sources(monkeypatch):
    bundle, store = notice_bundle()
    config = yaml.safe_load(bundle['config'])
    for role, reference in config.items():
        if role in bundle['captures']: Path('inputs', reference).write_bytes(bundle['captures'][role])
    Path('inputs/import-config.yaml').write_bytes(bundle['prepare_config'])
    Path('inputs/notice.html').write_bytes(bundle['documents']['mixed']['notice'])
    Path('inputs/review.yaml').write_bytes(bundle['config'])
    Path('inputs/report.yaml').write_bytes(bundle['review'])
    Path('inputs/execution.yaml').write_bytes(bundle['declaration'])
    captured, paths = bd.capture_local_application('inputs/review.yaml', 'inputs/report.yaml', bundle['review_sha256'],
                                                  'inputs/execution.yaml', bundle['declaration_sha256'], 'inputs', 100000, 32)
    assert captured == bundle and Path('inputs/notice.html') in paths
    assert len(bd.validate_qualified_application(captured, 100000, 32)['wires']) == 2


def test_prepare_lock_cannot_alias_an_original_notice():
    bundle, _ = notice_bundle()
    Path('inputs/notice.html').write_bytes(bundle['documents']['mixed']['notice'])
    Path('inputs/notices.yaml').write_bytes(bundle['prepare_config'])
    account = yaml.safe_load(bundle['prepare_config'])['account']
    Path('state').mkdir(exist_ok=True)
    lock = Path('state', 'prepare-' + sha(account['target_account_id'].encode()) + '.lock')
    # fixture() already prepares synthetic statement inputs in this isolated
    # test directory; replace that inactive fixture lock with the collision.
    lock.unlink(missing_ok=True)
    lock.hardlink_to(Path('inputs/notice.html'))
    before = Path('inputs/notice.html').read_bytes()
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'):
        bd.prepare_local_plan('inputs/notices.yaml', 'inputs', 100000, 32)
    assert Path('inputs/notice.html').read_bytes() == before

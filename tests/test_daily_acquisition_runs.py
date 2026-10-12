import hashlib
from pathlib import Path

import pytest
import yaml

import boursedirect_to_ghostfolio as bd
from test_daily_preview import isolated, run, paths, write
from test_daily_current_period import current_setup, saved


def collector_setup():
    config = current_setup()
    root = Path('inputs/run-a'); root.mkdir()
    source_ref = config['account']['source_account_ref']
    sources = [
        ('statement.html', 'monthly_statement', 'releveCompte.php?nc=1&dt=20260930&type=RE'),
        ('buy.html', 'contract_note', 'releveOpe.php?nc=1&type=RO&year=2026&month=09&day=17&trash=/avis.pdf'),
        ('index.html', 'frame_document', 'avis-operes.php?ong=5&nc=1'),
        ('current-1.html', 'contract_note', 'releveOpe.php?nc=1&type=RO&year=2026&month=10&day=1&trash=/avis.pdf'),
        ('current-2.html', 'contract_note', 'releveOpe.php?nc=1&type=RO&year=2026&month=10&day=2&trash=/avis.pdf'),
    ]
    for n, (filename, role, url) in enumerate(sources, 1):
        body = Path('inputs', filename).read_bytes()
        (root / f'document-{n}.html').write_bytes(body)
        meta = {'path': f'document-{n}.html', 'role': role, 'account_wrapper': 'PEA',
                'broker_account_id': source_ref[:-4], 'sha256': hashlib.sha256(body).hexdigest(),
                'url': 'https://www.boursedirect.fr/priv/new/' + url}
        (root / f'document-{n}.yaml').write_text(yaml.safe_dump(meta))
    receipt = {'schema_version': 1, 'state': 'owned_session_closed', 'accounts_verified': True,
               'session_logged_out': True, 'browser_exit_verified': True, 'captures': 5,
               'account_ids': {'PEA': source_ref[:-4]}, 'accounts': {'PEA': '1'}}
    (root / 'qualification.yaml').write_text(yaml.safe_dump(receipt))
    config.pop('documents'); config.pop('current_period')
    config.update(acquisition_runs={'first': 'run-a'}, index_encoding='observed_cp1252_declared_utf8')
    write(config)
    return config


def mutate(path, key, value):
    data = yaml.safe_load(path.read_bytes()); data[key] = value
    path.write_text(yaml.safe_dump(data))


def test_discovers_statement_and_current_notes_preserves_inputs_and_repeats():
    config = collector_setup()
    before = {p: p.read_bytes() for p in Path('inputs').rglob('*') if p.is_file()}
    run(); report = saved(config)
    assert report['last_completed_acquisition_period'] is None  # Synthetic statement also contains unmatched sells.
    assert report['current_period_observations']['offered_note_days'] == ['2026-10-01', '2026-10-02']
    assert report['current_period_observations']['notes']['2026-10-01']['code'] == 'INVALID_NOTE_SECURITY'
    assert report['acquisition_runs']['first']['captures'] == 5
    assert report['import_ready'] is False
    prior = tuple(p.read_bytes() for p in paths(config)); run()
    assert prior == tuple(p.read_bytes() for p in paths(config))
    assert before == {p: p.read_bytes() for p in Path('inputs').rglob('*') if p.is_file()}
    run('2026-10-13')
    assert saved(config)['window']['last_day'] == '2026-10-13'
    assert saved(config)['current_period_through_day_verified'] is False


def copy_run(config):
    root = Path('inputs/run-b'); root.mkdir()
    for p in Path('inputs/run-a').iterdir(): (root / p.name).write_bytes(p.read_bytes())
    config['acquisition_runs']['second'] = 'run-b'; write(config)


def test_identical_captures_deduplicate_across_completed_runs():
    config = collector_setup(); run(); before = saved(config)
    copy_run(config); run(); after = saved(config)
    assert before['current_period_observations'] == after['current_period_observations']
    assert before['exceptions'] == after['exceptions']
    assert len(after['acquisition_runs']) == 2


@pytest.mark.parametrize('number', [1, 2, 3, 4, 5])
def test_conflicting_versions_refuse_and_preserve_existing_state(number):
    config = collector_setup(); run(); prior = tuple(p.read_bytes() for p in paths(config))
    copy_run(config)
    body = Path(f'inputs/run-b/document-{number}.html'); body.write_bytes(body.read_bytes() + b' ')
    mutate(body.with_suffix('.yaml'), 'sha256', hashlib.sha256(body.read_bytes()).hexdigest())
    with pytest.raises(RuntimeError, match='^DAILY_ACQUISITION_CAPTURE_CONFLICT$'): run()
    assert prior == tuple(p.read_bytes() for p in paths(config))


@pytest.mark.parametrize('key,value', [('state','running'), ('accounts_verified',False), ('session_logged_out',False),
    ('browser_exit_verified',False), ('account_ids',{'PEA':'OTHER'}), ('captures',True), ('captures',257)])
def test_unfinished_wrong_account_or_unbounded_run_refuses(key,value):
    config = collector_setup(); mutate(Path('inputs/run-a/qualification.yaml'),key,value)
    with pytest.raises(RuntimeError, match='^DAILY_ACQUISITION_RUN_UNVERIFIED$'): run()
    assert not paths(config)[0].exists()


@pytest.mark.parametrize('key,value,code', [('path','../statement.html','DAILY_ACQUISITION_PATH_CONFLICT'),
    ('sha256','0'*64,'CURRENT_CAPTURE_BINDING_CONFLICT'), ('broker_account_id','OTHER','CURRENT_CAPTURE_BINDING_CONFLICT'),
    ('url','https://evil.invalid/priv/new/releveCompte.php?nc=1&dt=20260930&type=RE','CURRENT_CAPTURE_ORIGIN_CONFLICT'),
    ('url','https://www.boursedirect.fr/priv/new/releveCompte.php?nc=2&dt=20260930&type=RE','DAILY_ACQUISITION_URL_CONFLICT')])
def test_receipt_identity_and_origin_refusals(key,value,code):
    collector_setup(); mutate(Path('inputs/run-a/document-1.yaml'),key,value)
    with pytest.raises(RuntimeError, match='^'+code+'$'): run()


def test_missing_captured_document_does_not_publish_state():
    config = collector_setup(); Path('inputs/run-a/document-5.html').rename('inputs/held.html')
    with pytest.raises(RuntimeError): run()
    assert not paths(config)[0].exists()


def test_hardlinked_run_receipt_is_protected_from_report_publication():
    config = collector_setup(); output = paths(config)[1]; output.parent.mkdir()
    output.hardlink_to(Path('inputs/run-a/qualification.yaml'))
    before = output.read_bytes()
    with pytest.raises(RuntimeError, match='COLLISION'): run()
    assert output.read_bytes() == before and not paths(config)[0].exists()


def test_closed_note_url_month_must_match_original_financial_note():
    collector_setup()
    meta = Path('inputs/run-a/document-2.yaml')
    data = yaml.safe_load(meta.read_bytes()); mutate(meta, 'url', data['url'].replace('month=09', 'month=08'))
    with pytest.raises(RuntimeError, match='^DAILY_ACQUISITION_NOTE_DAY_CONFLICT$'): run()


def test_historical_calendar_is_not_mistaken_for_current_inventory():
    config = collector_setup()
    receipt = Path('inputs/run-a/qualification.yaml'); mutate(receipt, 'captures', 6)
    body = Path('inputs/run-a/document-3.html').read_bytes().replace(b',10,2026)', b',9,2026)')
    Path('inputs/run-a/document-6.html').write_bytes(body)
    meta = yaml.safe_load(Path('inputs/run-a/document-3.yaml').read_bytes())
    meta.update(path='document-6.html', sha256=hashlib.sha256(body).hexdigest(),
                url='https://www.boursedirect.fr/priv/new/avis-operes.php?nc=1&tr=RO&month=9&year=2026&ong=5')
    Path('inputs/run-a/document-6.yaml').write_text(yaml.safe_dump(meta))
    run(); assert saved(config)['current_period_observations']['period'] == '2026-10'


def test_account_bound_bodies_are_read_only_once(monkeypatch):
    collector_setup(); original = bd.read_local_bytes; seen = set()
    def once(path, *args):
        path = str(path)
        if path.endswith('.html'):
            assert path not in seen
            seen.add(path)
        return original(path, *args)
    monkeypatch.setattr(bd, 'read_local_bytes', once)
    run(); assert len(seen) == 5


def test_unrelated_and_other_account_bodies_are_not_read():
    config = collector_setup(); mutate(Path('inputs/run-a/qualification.yaml'), 'captures', 7)
    for n, role, wrapper in [(6, 'authentication', 'PEA'), (7, 'contract_note', 'PEA-PME')]:
        Path(f'inputs/run-a/document-{n}.yaml').write_text(yaml.safe_dump({'role': role, 'account_wrapper': wrapper}))
    run(); assert saved(config)['acquisition_runs']['first']['captures'] == 7


def test_global_receipt_limit_applies_before_second_run_is_processed():
    config = collector_setup(); copy_run(config)
    mutate(Path('inputs/run-b/qualification.yaml'), 'captures', 252)
    with pytest.raises(RuntimeError, match='^DAILY_INPUT_LIMIT_EXCEEDED$'): run()
    assert not paths(config)[0].exists()


def test_closed_note_calendar_day_difference_is_reported_without_redating():
    config = collector_setup()
    meta = Path('inputs/run-a/document-2.yaml')
    data = yaml.safe_load(meta.read_bytes()); mutate(meta, 'url', data['url'].replace('day=17', 'day=18'))
    run()
    differences = saved(config)['acquisition_runs']['first']['note_date_differences']
    assert differences[data['sha256']] == {'calendar_day': '2026-09-18', 'financial_days': ['2026-09-17']}

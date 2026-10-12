import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest
import yaml
from bs4 import BeautifulSoup

import boursedirect_to_ghostfolio as bd
from test_prepare import setup as trade_setup
from test_coupon_cash import statement_html
from test_contract_notes import coupon_source, field
from test_coupon_reconciliation import source, row


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Daily preview must remain offline')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(bd, 'persist_write_transition', forbidden)


def setup(coupon=False):
    if coupon:
        Path('inputs').mkdir()
        _, account, mappings = source()
        note = bd.parse_contract_note(coupon_source(), 32, include_coupons=True)['notes'][0]
        Path('inputs/statement.html').write_text(statement_html().replace('SYNTHETIC_ACCOUNT', account['source_account_ref']).replace('SYNTHETIC GAMMA', note['name']))
        Path('inputs/note.html').write_text(coupon_source())
        config = {'schema_version': 1, 'account': account, 'mappings': mappings,
                  'documents': {'september': {'statement': 'statement.html', 'notes': ['note.html']}}}
    else:
        config = trade_setup()
    config['snapshot'] = 'snapshot.json'
    Path('inputs/snapshot.json').write_text('{"count":0,"activities":[]}')
    write(config)
    return config


def write(config):
    Path('inputs/config.yaml').write_text(yaml.safe_dump(config))


def run(day='2026-10-12'):
    return bd.preview_local_daily('inputs/config.yaml', 'inputs', day, 1000000, 32)


def paths(config):
    digest = hashlib.sha256(config['account']['target_account_id'].encode()).hexdigest()
    return Path('state/daily-' + digest + '.yaml'), Path('outputs/daily-' + config['account']['account_key'] + '.yaml')


def test_closed_matching_period_advances_source_only_not_start_day_or_import_readiness():
    config = setup()
    result = run()
    journal, report = paths(config)
    saved = yaml.safe_load(report.read_text())
    assert saved['window'] == {'days': 90, 'first_day': '2026-07-15', 'last_day': '2026-10-12'}
    assert saved['last_completed_acquisition_period'] == '2026-09'
    assert saved['missing_or_unqualified_closed_periods'] == ['2026-07', '2026-08']
    assert saved['current_period_through_day_verified'] is False and result['import_ready'] is False
    assert saved['exceptions']['2026-09:destination']['status'] == 'unresolved'
    assert journal.stat().st_mode & 0o777 == report.stat().st_mode & 0o777 == 0o600
    before = journal.read_bytes(), report.read_bytes()
    run()
    assert before == (journal.read_bytes(), report.read_bytes())


def test_failed_source_matching_cannot_advance_coverage():
    config = setup()
    config['mappings'].clear()
    write(config)
    run()
    saved = yaml.safe_load(paths(config)[1].read_text())
    assert saved['last_completed_acquisition_period'] is None
    assert saved['exceptions']['2026-09:source']['code'] == 'SECURITY_MAPPING_MISSING'


def test_missing_note_security_quarantines_only_its_period_and_retains_prior_destination_exception():
    config = setup()
    run()
    # A valid earlier statement plus a coupon note lacking ISIN reproduces the
    # actual August boundary without using personal documents in the test suite.
    html = statement_html().replace('SYNTHETIC_ACCOUNT', config['account']['source_account_ref'])
    html = html.replace('17/09/2026', '17/08/2026').replace('31/08/2026', '31/07/2026').replace('30/09/2026', '31/08/2026')
    Path('inputs/august.html').write_text(html)
    note = BeautifulSoup(coupon_source(), 'html.parser')
    field(note, 1, 1).string = ''
    Path('inputs/august-note.html').write_text(str(note))
    config['documents']['august'] = {'statement': 'august.html', 'notes': ['august-note.html']}
    write(config)
    run()
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    assert report['last_completed_acquisition_period'] == '2026-09'
    assert report['exceptions']['2026-08:source']['code'] == 'SKIPPED_NOTE_CONTEXT_CONFLICT'
    assert report['exceptions']['2026-09:destination']['status'] == 'unresolved'
    assert '2026-08' not in report['missing_closed_statement_periods']
    assert '2026-08' in report['unqualified_observed_closed_periods']
    state = bd.parse_keyed_yaml(paths(config)[0].read_bytes())
    assert state['periods']['2026-08']['complete_source_matching'] is False
    assert state['periods']['2026-08']['note_sha256']
    journal, output = paths(config)
    before = journal.read_bytes(), output.read_bytes()
    run()
    assert before == (journal.read_bytes(), output.read_bytes())


def test_failed_note_replay_cannot_resolve_previous_destination_uncertainty():
    config = setup()
    run()
    Path('inputs/buy.html').write_text('<html>no financial note</html>')
    run()
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    assert report['exceptions']['2026-09:destination']['status'] == 'unresolved'
    assert '2026-09:source' in report['exceptions']
    assert report['last_completed_acquisition_period'] is None


def test_verified_saved_catchup_clears_stale_gap_without_expiring_other_months():
    config = setup(coupon=True)
    original = copy.deepcopy(config['mappings'])
    config['documents']['september']['notes'] = ['note.html', 'note.html']
    write(config)
    run()
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    assert '2026-09' in report['missing_or_unqualified_closed_periods']
    config['documents']['september']['notes'] = ['note.html']
    config['mappings'] = original
    write(config)
    run('2027-03-01')
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    assert '2026-09' not in report['missing_or_unqualified_closed_periods']
    assert report['resume_requires_catchup'] and '2026-08' in report['gaps_outside_window']
    assert bd.parse_keyed_yaml(paths(config)[0].read_bytes())['exceptions']['2026-09:source']['status'] == 'resolved_by_saved_evidence'


def test_old_exceptions_and_gaps_survive_window_and_absent_sources():
    config = setup(coupon=True)
    run()
    journal, report = paths(config)
    initial = yaml.safe_load(journal.read_text())
    retained = copy.deepcopy(initial['exceptions'])
    # Pure replay also supports inventory absence; CLI continues requiring a bundle.
    snapshot = Path('inputs/snapshot.json').read_bytes()
    next_state, next_report = bd.compute_daily_preview(config, {}, snapshot, initial, '2027-03-01', 1000000, 32)
    assert next_state['exceptions'] == retained
    assert next_report['exceptions'] and next_report['resume_requires_catchup'] is True
    assert '2026-08' in next_report['gaps_outside_window']
    assert 'DAILY_RESUME_CATCHUP_REQUIRED' in next_report['blockers']
    assert next_report['last_completed_acquisition_period'] == '2026-09'


def test_exact_coupon_replay_resolves_only_observed_exception():
    config = setup(coupon=True)
    run()
    assert run()['unresolved_exceptions'] == 2
    Path('inputs/snapshot.json').write_text(json.dumps({'count': 1, 'activities': [row()]}))
    assert run()['unresolved_exceptions'] == 1
    state = yaml.safe_load(paths(config)[0].read_text())
    assert all(v['status'] == 'resolved_by_saved_evidence' for k,v in state['exceptions'].items() if k.startswith('coupon:'))
    assert state['exceptions']['2026-09:destination']['status'] == 'unresolved'


def test_coupon_report_has_no_yaml_aliases_and_window_excludes_old_events():
    config = setup(coupon=True)
    run()
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    assert len(report['window_source_events']['2026-09']) == 1
    run('2027-03-01')
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    assert report['window_source_events']['2026-09'] == [] and report['exceptions']


def test_distinct_account_cannot_reuse_target_journal_and_other_targets_are_independent():
    config = setup()
    run()
    original = paths(config)[0].read_bytes()
    config['account']['account_key'] = 'aa299b68-5f7e-4717-acce-07802fe3fcdd'
    write(config)
    with pytest.raises(RuntimeError, match='INVALID_DAILY_JOURNAL_OR_BINDING'): run()
    config['account']['target_account_id'] = 'another-target'
    write(config)
    run()
    assert paths(config)[0].exists()
    assert len(list(Path('state').glob('daily-*.yaml'))) == 2
    assert original in [p.read_bytes() for p in Path('state').glob('daily-*.yaml')]


def test_malformed_retained_coverage_cannot_supply_watermark():
    config = setup()
    run()
    journal, _ = paths(config)
    state = bd.parse_keyed_yaml(journal.read_bytes())
    state['periods']['2026-09']['complete_source_matching'] = 'yes'
    journal.write_text(yaml.safe_dump(state))
    with pytest.raises(RuntimeError, match='INVALID_DAILY_JOURNAL_OR_BINDING'): run()


@pytest.mark.parametrize('change', ['revision', 'binding', 'clock', 'current'])
def test_refusals_preserve_prior_journal_and_report(change):
    config = setup(coupon=True)
    run()
    journal, report = paths(config)
    before = journal.read_bytes(), report.read_bytes()
    day = '2026-10-12'
    if change == 'revision':
        p = Path('inputs/statement.html')
        p.write_text(p.read_text().replace('COUPONS ', 'COUPONS REVISED '))
        expected = 'DAILY_SOURCE_REVISION_REVIEW_REQUIRED'
    elif change == 'binding':
        config['account']['source_account_ref'] = 'another-source'
        write(config)
        expected = 'ACCOUNT_BINDING_MIGRATION_REQUIRED'
    elif change == 'clock':
        day, expected = '2026-10-11', 'DAILY_PREVIEW_CLOCK_REVERSED'
    else:
        day, expected = '2026-09-30', 'DAILY_PREVIEW_CLOCK_REVERSED'
    with pytest.raises(RuntimeError, match=expected): run(day)
    assert before == (journal.read_bytes(), report.read_bytes())


def test_current_statement_refuses_before_any_financial_journal():
    config = setup()
    with pytest.raises(RuntimeError, match='DAILY_STATEMENT_NOT_CLOSED'): run('2026-09-30')
    assert not paths(config)[0].exists()


@pytest.mark.parametrize('role', ['target', 'account'])
def test_nonblocking_locks_preserve_evidence(role):
    config = setup()
    run()
    journal, report = paths(config)
    before = journal.read_bytes(), report.read_bytes()
    target = hashlib.sha256(config['account']['target_account_id'].encode()).hexdigest()
    path = 'state/prepare-' + target + '.lock' if role == 'target' else 'state/account-' + config['account']['account_key'] + '.lock'
    with open(path, 'rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='DAILY_ACCOUNT_OR_TARGET_LOCKED'): run()
    assert before == (journal.read_bytes(), report.read_bytes())


@pytest.mark.parametrize('destination', ['journal', 'report', 'binding', 'lock'])
def test_every_mutable_destination_preserves_hardlinked_input(destination):
    config = setup()
    journal, report = paths(config)
    Path('state').mkdir()
    Path('outputs').mkdir()
    target = hashlib.sha256(config['account']['target_account_id'].encode()).hexdigest()
    dest = {'journal': journal, 'report': report,
            'binding': Path('state/binding-' + config['account']['account_key'] + '.yaml'),
            'lock': Path('state/prepare-' + target + '.lock')}[destination]
    os.link('inputs/config.yaml', dest)
    original = Path('inputs/config.yaml').read_bytes()
    with pytest.raises(RuntimeError, match='OUTPUT_INPUT_COLLISION'): run()
    assert dest.read_bytes() == Path('inputs/config.yaml').read_bytes() == original


def test_interrupted_report_publication_can_be_replayed(monkeypatch):
    config = setup()
    original = bd.atomic_private_yaml
    def interrupted(path, value):
        if Path(path).parent == Path('outputs'): raise OSError('synthetic publication failure')
        original(path, value)
    monkeypatch.setattr(bd, 'atomic_private_yaml', interrupted)
    with pytest.raises(OSError): run()
    assert paths(config)[0].exists() and not paths(config)[1].exists()
    monkeypatch.setattr(bd, 'atomic_private_yaml', original)
    run()
    assert paths(config)[1].exists()


def test_cli_exposes_counts_only(capsys):
    config = setup(coupon=True)
    assert bd.main(['daily-preview', '--config', 'inputs/config.yaml', '--input-root', 'inputs',
                   '--as-of', '2026-10-12', '--max-bytes', '1000000', '--max-depth', '32']) == 2
    output = capsys.readouterr().out
    assert json.loads(output)['unresolved_exceptions'] == 2
    assert config['account']['source_account_ref'] not in output


@pytest.mark.parametrize('day', ['2026-02-30', '2026-1-01', '0001-01-01'])
def test_invalid_window_day_refuses(day):
    setup()
    with pytest.raises(RuntimeError, match='INVALID_DAILY_PREVIEW_DAY'): run(day)


def test_cli_default_day_uses_broker_clock_and_keeps_readiness_false(monkeypatch, capsys):
    config = setup()
    monkeypatch.setattr(bd, 'daily_preview_today', lambda: '2026-10-12')
    assert bd.main(['daily-preview', '--config', 'inputs/config.yaml', '--input-root', 'inputs',
                    '--max-bytes', '1000000', '--max-depth', '32']) == 2
    report = yaml.safe_load(paths(config)[1].read_bytes())
    assert report['window']['last_day'] == '2026-10-12' and report['import_ready'] is False
    assert 'false' in capsys.readouterr().out.lower()


def test_cli_explicit_replay_day_does_not_consume_today(monkeypatch):
    config = setup()
    def forbidden(): raise AssertionError('Explicit replay must not use today')
    monkeypatch.setattr(bd, 'daily_preview_today', forbidden)
    assert bd.main(['daily-preview', '--config', 'inputs/config.yaml', '--input-root', 'inputs',
                    '--as-of', '2026-10-13', '--max-bytes', '1000000', '--max-depth', '32']) == 2
    assert yaml.safe_load(paths(config)[1].read_bytes())['window']['last_day'] == '2026-10-13'


@pytest.mark.parametrize('instant', ['2026-07-12T22:30:00+00:00', '2026-01-12T23:30:00+00:00'])
def test_default_day_crosses_midnight_in_broker_summer_and_winter_time(instant):
    from datetime import datetime
    from unittest.mock import patch
    moment = datetime.fromisoformat(instant)
    with patch.object(bd, 'datetime') as clock:
        clock.now.side_effect = lambda zone: moment.astimezone(zone)
        assert bd.daily_preview_today() == instant[:8] + '13'
        assert clock.now.call_args.args[0].key == 'Europe/Paris'


def test_note_account_mismatch_refuses_command_without_publishing_state():
    config = setup(coupon=True)
    note = Path('inputs/note.html')
    note.write_text(note.read_text().replace(config['account']['source_account_ref'], 'OTHER_SOURCE_ACCOUNT'))
    with pytest.raises(RuntimeError, match='^DAILY_SOURCE_ACCOUNT_CONFLICT$'):
        run()
    assert not any(path.exists() for path in paths(config))


def test_skipped_closed_coupon_report_keeps_cash_and_label_hash_without_auxiliary_text():
    config = setup(coupon=True)
    path = Path('inputs/note.html')
    soup = BeautifulSoup(path.read_text(), 'html.parser')
    field(soup, 1, 1).string = ''
    path.write_text(str(soup))
    run()
    report = bd.parse_keyed_yaml(paths(config)[1].read_bytes())
    skipped = report['skipped_source_operations']['2026-09']
    assert len(skipped) == 1 and skipped[0]['credit'] == '1.9'
    assert len(skipped[0]['source_label_sha256']) == 64
    assert 'source_label' not in skipped[0] and 'source_fields' not in skipped[0]
    assert skipped[0]['financial_conversion'] is False and report['import_ready'] is False

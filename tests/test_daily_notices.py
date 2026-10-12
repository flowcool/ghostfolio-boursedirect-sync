import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

import boursedirect_to_ghostfolio as bd
from test_daily_preview import isolated, write
from test_daily_acquisition_runs import collector_setup, mutate
from test_contract_notes import coupon_source, note_source
from test_conversion import inputs
from test_identity import ACCOUNT


def setup_notices():
    config = collector_setup()
    config['source_mode'] = 'notices'
    write(config)
    # The notice path must not even read these source bodies.
    Path('inputs/run-a/document-1.html').unlink()
    Path('inputs/run-a/document-3.html').unlink()
    return config


def run_notices():
    return bd.preview_local_daily('inputs/config.yaml', 'inputs', '2026-10-12', 2000000, 256)


def report(config):
    return yaml.safe_load(Path('outputs', 'daily-notices-' + config['account']['account_key'] + '.yaml').read_bytes())


def pure_sources():
    _, _, account, mappings = inputs()
    account['account_key'] = ACCOUNT
    # Same-day notices are one original document in collector discovery. Pure
    # conversion uses one mixed document assembled from the existing fixtures.
    from bs4 import BeautifulSoup
    from test_contract_notes import vectors
    soup = BeautifulSoup(note_source(), 'html.parser')
    coupon = BeautifulSoup(coupon_source(), 'html.parser')
    for target, rows in zip(vectors(soup), vectors(coupon)):
        for row in rows:
            target[0].parent.append(copy.copy(row))
    captures = {'mixed': str(soup).encode()}
    notes = {'2026-09-17': {'document': 'mixed', 'sha256': hashlib.sha256(captures['mixed']).hexdigest()}}
    return account, mappings, notes, captures


def test_current_and_closed_notices_need_neither_statement_nor_calendar_and_repeat():
    config = setup_notices()
    before = {p: p.read_bytes() for p in Path('inputs').rglob('*') if p.is_file()}
    summary = run_notices()
    result = report(config)
    assert summary['source_activities'] == 2 and summary['skipped_operations'] == 1
    assert {a['operation_date'] for a in result['activities'].values()} == {'2026-09-17', '2026-10-02'}
    assert result['candidate_export'] is not None and not result['import_ready']
    raw = Path('outputs', 'daily-notices-' + config['account']['account_key'] + '.yaml').read_bytes()
    assert run_notices() == summary
    assert raw == Path('outputs', 'daily-notices-' + config['account']['account_key'] + '.yaml').read_bytes()
    assert all(p.read_bytes() == value for p, value in before.items())


def test_independent_dividend_uses_received_cash_date_and_retains_source_fields():
    account, mappings, notes, captures = pure_sources()
    _, result = bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)
    dividend = next(a for a in result['activities'].values() if a['kind'] == 'DIVIDEND')
    assert (dividend['quantity'], dividend['unit_price'], dividend['fee'], dividend['operation_date']) == ('1', '1.9', '0', '2026-09-17')
    fields = result['source_evidence'][dividend['id']]['fields']
    assert fields['gross'] == '2.4' and fields['commission'] == '0.1'
    rows = json.loads(result['candidate_export'])['activities']
    assert next(r for r in rows if r['type'] == 'DIVIDEND')['unitPrice'] == 1.9


def test_legacy_timestamp_and_fee_difference_do_not_suppress_diagnostic_wire():
    account, mappings, notes, captures = pure_sources()
    _, base = bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)
    from test_adoption import row
    from datetime import date
    from decimal import Decimal
    a = next(a for a in base['activities'].values() if a['kind'] == 'BUY')
    internal = {**a, 'operation_date': date.fromisoformat(a['operation_date']), **{k: Decimal(a[k]) for k in ('quantity', 'unit_price', 'fee')}}
    existing = row(internal)
    existing['date'] = '2026-09-17T15:32:00.000Z'
    existing['fee'] += 1
    snapshot = json.dumps({'count': 1, 'activities': [existing]}).encode()
    _, result = bd.compute_notice_preview(account, mappings, notes, captures, snapshot, None, '2026-10-12', 32)
    assert result['candidate_export'] is not None
    assert result['dispositions'][a['id']] == 'EXISTING_CANDIDATE_REVIEW'
    assert 'fee' in next(iter(result['destination_diagnosis']['activities'][a['id']]['candidates'].values()))['different_fields']
    assert a['id'] not in {r['comment'] for r in json.loads(result['new_candidate_export'])['activities']}


def test_changed_notice_refuses_without_replacing_saved_state():
    config = setup_notices(); run_notices()
    previous = {p: p.read_bytes() for d in ('state', 'outputs') for p in Path(d).glob('*')}
    body = Path('inputs/run-a/document-5.html')
    body.write_bytes(body.read_bytes() + b' ')
    mutate(Path('inputs/run-a/document-5.yaml'), 'sha256', hashlib.sha256(body.read_bytes()).hexdigest())
    with pytest.raises(RuntimeError, match='^NOTICE_SOURCE_REVISION$'):
        run_notices()
    assert all(p.read_bytes() == raw for p, raw in previous.items())


@pytest.mark.parametrize('field,value', [('execution_price_currency', 'USD'), ('currency_evidence', ''), ('target_security_evidence', '')])
def test_unverified_mapping_is_visible_and_other_operations_are_not_blocked(field, value):
    account, mappings, notes, captures = pure_sources()
    first = next(iter(mappings)); mappings[first][field] = value
    _, result = bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)
    assert result['exceptions']
    assert not any(a['kind'] == 'BUY' for a in result['activities'].values())


def test_cli_dispatches_notice_mode_without_application(monkeypatch, capsys):
    setup_notices()
    assert bd.main(['daily-preview', '--config', 'inputs/config.yaml', '--input-root', 'inputs', '--as-of', '2026-10-12', '--max-bytes', '2000000', '--max-depth', '256']) == 2
    assert json.loads(capsys.readouterr().out)['source_mode'] == 'notices'


def test_notice_identity_survives_mapping_change_and_is_not_a_monthly_identity():
    account, mappings, notes, captures = pure_sources()
    _, before = bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)
    mappings[next(iter(mappings))]['symbol'] = 'OTHER.PA'
    _, after = bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)
    assert set(before['activities']) == set(after['activities'])
    assert any(a['symbol'] == 'OTHER.PA' for a in after['activities'].values())


@pytest.mark.parametrize('clock,count', [('2026-12-15', 2), ('2026-12-16', 0)])
def test_window_is_inclusive_and_old_notes_are_not_exported(clock, count):
    account, mappings, notes, captures = pure_sources()
    _, result = bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, clock, 32)
    assert len(result['activities']) == count


def test_malformed_present_isin_is_reported_and_never_skipped():
    config = setup_notices()
    path = Path('inputs/run-a/document-5.html')
    from bs4 import BeautifulSoup
    from test_contract_notes import field
    soup = BeautifulSoup(path.read_text(), 'html.parser')
    field(soup, 1, 1).string = 'INVALID_ISIN'
    path.write_text(str(soup))
    mutate(Path('inputs/run-a/document-5.yaml'), 'sha256', hashlib.sha256(path.read_bytes()).hexdigest())
    summary = run_notices()
    assert summary['skipped_operations'] == 1 and summary['source_activities'] == 1
    assert 'INVALID_NOTE_SECURITY' in {v['code'] for v in report(config)['exceptions'].values()}


def test_account_mismatch_refuses_and_no_report_is_written():
    config = setup_notices()
    path = Path('inputs/run-a/document-5.html')
    path.write_bytes(path.read_bytes().replace(config['account']['source_account_ref'].encode(), b'OTHER ACCOUNT'))
    mutate(Path('inputs/run-a/document-5.yaml'), 'sha256', hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(RuntimeError, match='^DAILY_SOURCE_ACCOUNT_CONFLICT$'):
        run_notices()
    assert not Path('outputs').exists()


def test_mapping_collision_refuses_instead_of_merging_different_isins():
    # Coupon mapping collision is checked across independently prepared rows.
    account, mappings, notes, captures = pure_sources()
    from bs4 import BeautifulSoup
    from test_contract_notes import field
    soup = BeautifulSoup(captures['mixed'], 'html.parser')
    field(soup, 10, 1).string = next(k for k in mappings if k != next(iter(mappings)))
    captures['mixed'] = str(soup).encode()
    notes['2026-09-17']['sha256'] = hashlib.sha256(captures['mixed']).hexdigest()
    mapping = mappings[next(iter(mappings))]
    for value in mappings.values():
        value['symbol'] = mapping['symbol']
    with pytest.raises(RuntimeError, match='^SECURITY_MAPPING_AMBIGUOUS$'):
        bd.compute_notice_preview(account, mappings, notes, captures, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)


def test_independent_sales_keep_positive_quantity_explicit_fees_and_exact_prices():
    account, mappings, _, _ = pure_sources()
    raw = note_source(True).encode()
    notes = {'2026-09-17': {'document': 'sales', 'sha256': hashlib.sha256(raw).hexdigest()}}
    _, result = bd.compute_notice_preview(account, mappings, notes, {'sales': raw}, b'{"count":0,"activities":[]}', None, '2026-10-12', 32)
    assert {(a['kind'], a['quantity'], a['unit_price'], a['fee']) for a in result['activities'].values()} == {
        ('SELL', '2', '12', '0.2'), ('SELL', '5', '7', '0.35')}


def test_identical_run_deduplication_and_target_lock_protect_repeat(monkeypatch):
    config = setup_notices()
    import shutil
    shutil.copytree('inputs/run-a', 'inputs/run-b')
    config['acquisition_runs']['second'] = 'run-b'; write(config)
    assert run_notices()['source_activities'] == 2
    import fcntl
    target = hashlib.sha256(config['account']['target_account_id'].encode()).hexdigest()
    with Path('state', 'prepare-' + target + '.lock').open('rb') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='^DAILY_ACCOUNT_OR_TARGET_LOCKED$'):
            run_notices()


def test_notice_output_collision_preserves_input_receipt():
    config = setup_notices()
    Path('outputs').mkdir()
    source = Path('inputs/run-a/qualification.yaml')
    before = source.read_bytes()
    Path('outputs', 'daily-notices-' + config['account']['account_key'] + '.yaml').hardlink_to(source)
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'):
        run_notices()
    assert source.read_bytes() == before

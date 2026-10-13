"""Exact reconciliation from anonymized real financial notice fields, offline."""
import copy
import hashlib
import json
from pathlib import Path
from decimal import Decimal, localcontext

import pytest

import boursedirect_to_ghostfolio as b
from test_buy_simulation import real_buy, MAPPING


ACCOUNT = {'source_account_ref': 'SYNTHETIC001 PEA', 'target_account_id': 'synthetic-destination'}


def proposals(document=None):
    return b.simulate_buy_notice(document or real_buy(), ACCOUNT, MAPPING, occurrences={})


def remote(proposal, marker=True, **changes):
    row = {'id': 'synthetic-activity', 'accountId': proposal['accountId'],
        'account': {'id': proposal['accountId'], 'tags': []}, 'tags': [],
        'type': proposal['type'], 'date': proposal['date'], 'currency': 'EUR',
        'comment': proposal['comment'] if marker else None,
        'quantity': Decimal(proposal['quantity']), 'unitPrice': Decimal(proposal['unitPrice']),
        'fee': Decimal(proposal['fee']), 'assetProfile': {'symbol': proposal['symbol'],
            'currency': 'EUR', 'dataSource': 'YAHOO'}}
    row.update(changes)
    # Numeric strings are never substituted for Ghostfolio's numeric JSON fields.
    raw = json.dumps({'count': 1, 'activities': [row]}, default=lambda n: 'DECIMAL:' + str(n))
    import re
    raw = re.sub(r'"DECIMAL:([-0-9.]+)"', r'\1', raw)
    return b.parse_remote_activity_snapshot(raw.encode(), retain_stored_date=True)[0]


@pytest.fixture(autouse=True)
def isolated_entry_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def day_evidence(rows, civil_day=None):
    """Constructed entry provenance, never inferred from runtime/server timezone."""
    activities = {}
    for row in rows:
        day = civil_day or row['operation_date']
        # Explicitly constructed historical entry capture, not a server-TZ inference.
        context = {'schema_version': 1, 'activity_id': row['remote_id'],
            'account_id': row['target_account_id'], 'stored_date': row['stored_date'],
            'financial_fingerprint': b.activity_financial_fingerprint(row),
            'entered_day': day, 'entry_timezone': 'UTC' if day == row['operation_date'] else 'Europe/Zurich'}
        path = Path(row['remote_id'] + '-entry.yaml')
        b.atomic_private_yaml(path, context)
        activities[row['remote_id']] = {key: context[key] for key in
            ('account_id', 'stored_date', 'financial_fingerprint')}
        activities[row['remote_id']].update(civil_day=day,
            provenance={'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    return {'schema_version': 1, 'activities': activities}


def reconcile(pending, rows, evidence=None):
    return b.reconcile_notice_duplicates(pending, rows, evidence, Path.cwd())



def test_owned_exact_repeat_proposes_nothing_and_has_no_side_effect():
    pending = proposals()
    original = copy.deepcopy(pending)
    assert reconcile(pending, [remote(pending[0])]) == ([], 1)
    assert pending == original


@pytest.mark.parametrize('field,value', [('quantity', 13), ('unitPrice', 9), ('fee', 2),
    ('date', '2019-02-07T00:00:00.000Z'), ('currency', 'USD'), ('isDraft', True)])
def test_changed_owned_identity_fails(field, value):
    pending = proposals()
    with pytest.raises(RuntimeError, match='NOTICE_OWNED_ACTIVITY_CONFLICT'):
        reconcile(pending, [remote(pending[0], **{field: value})])


def test_owned_wrong_account_or_duplicate_identity_fails():
    pending = proposals()
    row = remote(pending[0])
    other = dict(row, target_account_id='other')
    for rows in ([other], [row, dict(row, remote_id='second')]):
        with pytest.raises(RuntimeError, match='NOTICE_IDENTITY_OWNERSHIP_CONFLICT'):
            reconcile(pending, rows)


def test_identity_ignores_mapping_capture_location_and_preserves_occurrences():
    document = real_buy()
    first = proposals(document)[0]
    document['notes'][0].update(name='another label', venue='another venue', slot=999)
    assert proposals(document)[0]['comment'] == first['comment']
    different = b.simulate_buy_notice(document, ACCOUNT,
        {'FR0000000002': {'symbol': 'OTHER.PA', 'currency': 'EUR'}}, occurrences={})[0]
    assert different['comment'] == first['comment']
    document['notes'].append(copy.deepcopy(document['notes'][0]))
    both = proposals(document)
    assert len({p['comment'] for p in both}) == 2
    assert reconcile(both, [remote(both[0])]) == ([both[1]], 1)
    assert reconcile(both, [remote(both[0]), remote(both[1], id='second')]) == ([], 2)
    different_account = b.simulate_buy_notice(document, dict(ACCOUNT, target_account_id='other'), MAPPING, occurrences={})
    assert {p['comment'] for p in both}.isdisjoint(p['comment'] for p in different_account)


def test_pending_duplicate_identity_is_never_silently_collapsed():
    pending = proposals()
    with pytest.raises(RuntimeError, match='NOTICE_PENDING_IDENTITY_CONFLICT'):
        reconcile(pending * 2, [])


def test_manual_exact_match_consumes_once_and_never_changes_comment():
    pending = proposals()
    row = remote(pending[0], marker=False)
    assert reconcile(pending, [row], day_evidence([row])) == ([], 1)
    assert row['comment'] is None


@pytest.mark.parametrize('field,value', [('quantity', 13), ('unitPrice', 9), ('fee', 2),
    ('date', '2019-02-05T23:00:00.000Z'), ('isDraft', True)])
def test_manual_nearby_difference_is_ambiguous(field, value):
    pending = proposals()
    with pytest.raises(RuntimeError, match='NOTICE_MANUAL_OVERLAP_AMBIGUOUS'):
        reconcile(pending, [remote(pending[0], marker=False, **{field: value})])


def test_manual_multiplicity_requires_exact_group_count():
    document = real_buy()
    document['notes'] *= 2
    pending = proposals(document)
    row = remote(pending[0], marker=False)
    with pytest.raises(RuntimeError, match='NOTICE_MANUAL_OVERLAP_AMBIGUOUS'):
        reconcile(pending, [row], day_evidence([row]))
    assert reconcile(pending, [row, dict(row, remote_id='second')],
        day_evidence([row, dict(row, remote_id='second')])) == ([], 2)
    with pytest.raises(RuntimeError, match='NOTICE_MANUAL_OVERLAP_AMBIGUOUS'):
        reconcile(pending[:1], [row, dict(row, remote_id='second')],
            day_evidence([row, dict(row, remote_id='second')]))


def test_other_account_same_financial_fields_does_not_deduplicate_or_fund_sell():
    pending = proposals()
    row = dict(remote(pending[0], marker=False), target_account_id='other')
    assert reconcile(pending, [row]) == (pending, 0)
    sell = dict(pending[0], type='SELL', quantity='1')
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([sell], [row])


def test_insufficient_50_with_10_stops_all_proposals_and_logs_both_quantities(capsys):
    buy = proposals()[0]
    sell = dict(buy, type='SELL', quantity='50')
    baseline = remote(buy, marker=False, quantity=10, date='2018-01-01T00:00:00.000Z')
    later_buy = dict(buy, quantity='100', execution_time='23:59:59')
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([later_buy, sell], [baseline])
    log = json.loads(capsys.readouterr().out)
    assert (log['available'], log['sale'], log['financial_writes'], log['imported']) == ('10', '50', 0, 0)


def test_only_preceding_buys_fund_projection_and_submitted_buys_never_fund_dispatch():
    buy = dict(proposals()[0], quantity='50', execution_time='09:00:00')
    sell = dict(buy, type='SELL', execution_time='10:00:00', comment=buy['comment'] + 'sell')
    assert b.reconcile_notice_holdings([sell, buy], []) == [buy, sell]
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([buy, sell], [], project_buys=False)
    # The readback-confirmed BUY is then available from the baseline itself.
    confirmed = remote(buy)
    assert b.reconcile_notice_holdings([sell], [confirmed], project_buys=False) == [sell]
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([dict(buy, execution_time='11:00:00'), sell], [])


def test_duplicate_and_skipped_buys_cannot_double_fund_sales():
    buy = dict(proposals()[0], quantity='10')
    sell = dict(buy, type='SELL', quantity='15', comment=buy['comment'] + 'sell')
    row = remote(buy)
    pending, duplicates = reconcile([buy, sell], [row])
    assert duplicates == 1 and pending == [sell]
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings(pending, [row])
    document = real_buy()
    document['notes'][0]['vat'] = Decimal('.01')
    assert proposals(document) == []
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.reconcile_notice_holdings([sell], [row])


def test_baseline_uses_net_active_trades_only_and_exact_decimals():
    buy = dict(proposals()[0], quantity='1000000000000000000000000000.0001')
    baseline = remote(buy)
    sale = dict(baseline, remote_id='sale', kind='SELL', quantity=Decimal('1000000000000000000000000000'))
    excluded = dict(baseline, remote_id='draft', active=False)
    dividend = dict(baseline, remote_id='coupon', kind='DIVIDEND')
    sell = dict(buy, type='SELL', quantity='.0001')
    with localcontext() as context:
        context.prec = 4
        assert b.reconcile_notice_holdings([sell], [baseline, sale, excluded, dividend]) == [sell]


@pytest.mark.parametrize('change', [{'financial_context_verified': False}, {'price_currency': 'USD'},
    {'data_source': 'MANUAL'}])
def test_unsupported_target_holdings_refuse(change):
    buy = proposals()[0]
    with pytest.raises(RuntimeError, match='NOTICE_HOLDINGS_CONTEXT_UNVERIFIED'):
        b.reconcile_notice_holdings([buy], [dict(remote(buy), **change)])


@pytest.mark.parametrize('change', [{'data_source': 'MANUAL'}, {'price_currency': 'USD'},
    {'financial_context_verified': False}])
def test_unrelated_holdings_context_does_not_block_a_proposal(change):
    buy = proposals()[0]
    unrelated = dict(remote(buy), symbol='00000000-0000-4000-8000-000000000002', **change)
    assert b.reconcile_notice_holdings([buy], [unrelated]) == [buy]


def test_multiple_isins_cannot_share_one_holdings_symbol():
    buy = proposals()[0]
    with pytest.raises(RuntimeError, match='NOTICE_SYMBOL_ISIN_CONFLICT'):
        b.reconcile_notice_holdings([buy, dict(buy, isin='FR0000000010')], [])


@pytest.mark.parametrize('raw,code', [(b'{"count":1,"activities":[]}', 'REMOTE_ACTIVITY_COUNT_MISMATCH'),
    (b'{"activities":[]}', 'REMOTE_ACTIVITY_COUNT_MISMATCH')])
def test_incomplete_destination_read_refuses(raw, code):
    with pytest.raises(RuntimeError, match=code):
        b.parse_remote_activity_snapshot(raw)


def test_redacted_numeric_destination_refuses():
    with pytest.raises(RuntimeError, match='REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED'):
        remote(proposals()[0], quantity=None)


MANUAL_CASES = json.loads((Path(__file__).parent / 'fixtures' /
    'notice-manual-trades-anonymized-real.json').read_text())


def retained_manual_case(name):
    case = MANUAL_CASES[name]
    document = b.parse_contract_note((Path(__file__).parent / 'fixtures' / case['fixture']).read_text(), 16)
    document['notes'] = document['notes'][:1]
    pending = proposals(document)
    row = remote(pending[0], marker=False, date=case['stored_date'], fee=Decimal(case['destination_fee']))
    return pending, [row], day_evidence([row], pending[0]['date'][:10])


def replay_manual_calendar_day(monkeypatch, name, pending, rows, evidence, status, duplicates=0):
    """Offline replay through the run's status/error boundary, without acquisition."""
    import builtins
    import socket

    def forbidden(*args, **kwargs):
        pytest.fail('financial/network access or confirmation requested during offline reconciliation')

    monkeypatch.setattr(builtins, 'input', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    original = copy.deepcopy((pending, rows, evidence))

    def replay():
        result, count = reconcile(pending, rows, evidence)
        assert (len(result), count) == (0, duplicates)
        print(json.dumps({'code': 'NOTICE_MANUAL_DUPLICATES', 'duplicates': count,
            'proposed': len(result), 'financial_writes': 0, 'imported': 0}))
        return 0

    monkeypatch.setattr(b, 'sync_buy_simulation', replay)
    from contextlib import redirect_stdout
    from io import StringIO
    output = StringIO()
    with redirect_stdout(output):
        actual_status = b.main(['--sync'])
    print(output.getvalue(), end='')
    assert actual_status == status
    diagnostics = [json.loads(line) for line in output.getvalue().splitlines()]
    assert all(item['financial_writes'] == item['imported'] == 0 for item in diagnostics)
    if status:
        if name.startswith('constructed_invalid_evidence_'):
            assert diagnostics[-1]['code'] == 'NOTICE_DAY_CONTEXT_INVALID'
        else:
            assert diagnostics[-1]['code'] == 'NOTICE_MANUAL_OVERLAP_AMBIGUOUS'
            reason = ('unverified_day_provenance' if any(part in name for part in ('unknown', 'stale'))
                else 'multiplicity_conflict' if 'multiplicity' in name
                else 'fee_difference' if 'fee' in name else 'financial_or_day_conflict')
            assert diagnostics[0]['reason'] == reason
    assert (pending, rows, evidence) == original
    print(json.dumps({'scenario': name, 'run_status': status, 'financial_writes': 0,
        'confirmation_requests': 0, 'existing_fields_unchanged': True}))


@pytest.mark.parametrize('name', ['buy_equal', 'sell_equal'])
def test_manual_calendar_day_retained_non_midnight(monkeypatch, name):
    pending, rows, evidence = retained_manual_case(name)
    assert not rows[0]['date_context_verified']
    replay_manual_calendar_day(monkeypatch, name, pending, rows, evidence, 0, duplicates=1)


def test_manual_calendar_day_unknown_provenance_refuses_even_with_server_tz(monkeypatch):
    pending, rows, _ = retained_manual_case('buy_equal')
    monkeypatch.setenv('TZ', 'Europe/Zurich')
    replay_manual_calendar_day(monkeypatch, 'constructed_unknown_provenance', pending, rows,
        {'schema_version': 1, 'activities': {}}, 1)


def test_manual_calendar_day_retained_fee_discrepancy(monkeypatch):
    pending, rows, evidence = retained_manual_case('buy_fee_conflict')
    replay_manual_calendar_day(monkeypatch, 'retained_fee_difference_anonymized', pending, rows, evidence, 1)


@pytest.mark.parametrize('source_count,destination_count', [(2, 1), (1, 2), (2, 2)])
def test_manual_calendar_day_constructed_multiplicity(monkeypatch, source_count, destination_count):
    pending, rows, _ = retained_manual_case('buy_equal')
    pending += [dict(pending[0], comment=pending[0]['comment'][:-1] +
        ('0' if pending[0]['comment'][-1] != '0' else '1'))] if source_count == 2 else []
    rows += [dict(rows[0], remote_id='synthetic-second')] if destination_count == 2 else []
    evidence = day_evidence(rows, pending[0]['date'][:10])
    status = int(source_count != destination_count)
    replay_manual_calendar_day(monkeypatch, f'constructed_multiplicity_{source_count}_{destination_count}',
        pending, rows, evidence, status, duplicates=source_count if not status else 0)


@pytest.mark.parametrize('field,value', [('stored_date', '2019-02-06T15:01:00.000Z'),
    ('fee', Decimal('0.001')), ('target_account_id', 'changed-account')])
def test_manual_calendar_day_stale_entry_evidence_refuses(monkeypatch, field, value):
    pending, rows, evidence = retained_manual_case('buy_equal')
    if field == 'target_account_id':
        evidence['activities'][rows[0]['remote_id']]['account_id'] = value
    else:
        rows[0][field] = value
    replay_manual_calendar_day(monkeypatch, 'constructed_stale_evidence_' + field, pending, rows, evidence, 1)


def test_manual_calendar_day_unknown_far_date_cannot_prove_no_overlap(monkeypatch):
    pending, rows, _ = retained_manual_case('buy_equal')
    rows[0]['operation_date'] = '2000-01-01'
    replay_manual_calendar_day(monkeypatch, 'constructed_unknown_far_day', pending, rows,
        {'schema_version': 1, 'activities': {}}, 1)


def test_manual_calendar_day_exact_plus_conflicting_candidate_refuses(monkeypatch):
    pending, rows, _ = retained_manual_case('buy_equal')
    rows.append(dict(rows[0], remote_id='synthetic-conflict', fee=rows[0]['fee'] + Decimal('.25')))
    replay_manual_calendar_day(monkeypatch, 'constructed_exact_plus_fee_conflict', pending, rows,
        day_evidence(rows, pending[0]['date'][:10]), 1)


@pytest.mark.parametrize('field,value', [('quantity', Decimal('13')), ('unit_price', Decimal('9')),
    ('price_currency', 'USD'), ('data_source', 'MANUAL'), ('active', False)])
def test_manual_calendar_day_exact_financial_context_required(monkeypatch, field, value):
    pending, rows, _ = retained_manual_case('buy_equal')
    rows[0][field] = value
    replay_manual_calendar_day(monkeypatch, 'constructed_context_' + field, pending, rows,
        day_evidence(rows, pending[0]['date'][:10]), 1)


def test_manual_calendar_day_constructed_civil_boundary(monkeypatch):
    pending, rows, _ = retained_manual_case('buy_equal')
    rows[0] = remote(pending[0], marker=False, date='2019-02-05T23:00:00.000Z')
    replay_manual_calendar_day(monkeypatch, 'constructed_civil_boundary', pending, rows,
        day_evidence(rows, '2019-02-06'), 0, duplicates=1)


def test_manual_calendar_day_owned_timestamp_stays_exact_and_source_clock_in_identity():
    pending, rows, evidence = retained_manual_case('buy_equal')
    rows[0]['comment'] = pending[0]['comment']
    with pytest.raises(RuntimeError, match='NOTICE_OWNED_ACTIVITY_CONFLICT'):
        reconcile(pending, rows, evidence)
    assert reconcile(pending, [remote(pending[0])], evidence) == ([], 1)
    document = real_buy()
    original = proposals(document)[0]
    document['notes'][0]['execution_time'] = '11:22:33'
    changed = proposals(document)[0]
    assert original['comment'] != changed['comment'] and changed['execution_time'] == '11:22:33'
    print('constructed_owned_exact: non_midnight_owned_refused exact_owned_duplicate=1 source_clock_retained financial_writes=0')


@pytest.mark.parametrize('mutate', ['schema', 'day', 'missing_provenance'])
def test_manual_calendar_day_malformed_provenance_refuses(monkeypatch, mutate):
    pending, rows, evidence = retained_manual_case('buy_equal')
    entry = evidence['activities'][rows[0]['remote_id']]
    if mutate == 'schema':
        evidence['schema_version'] = True
    elif mutate == 'day':
        entry['civil_day'] = '2019-02-30'
    else:
        del entry['provenance']
    replay_manual_calendar_day(monkeypatch, 'constructed_invalid_evidence_' + mutate,
        pending, rows, evidence, 1)


def test_manual_calendar_day_private_yaml_restart(tmp_path, monkeypatch):
    pending, rows, evidence = retained_manual_case('sell_equal')
    path = tmp_path / 'manual-day-context.yaml'
    b.atomic_private_yaml(path, evidence)
    assert path.stat().st_mode & 0o777 == 0o600
    retained = b.read_keyed_yaml(path, tmp_path, 1024 * 1024)
    replay_manual_calendar_day(monkeypatch, 'constructed_private_yaml_restart', pending, rows, retained, 0, duplicates=1)


def test_manual_calendar_day_midnight_is_not_entry_provenance(monkeypatch):
    pending = proposals()
    rows = [remote(pending[0], marker=False)]
    assert rows[0]['date_context_verified']
    replay_manual_calendar_day(monkeypatch, 'constructed_unknown_midnight_provenance', pending, rows,
        {'schema_version': 1, 'activities': {}}, 1)


def test_manual_calendar_day_conflict_refuses_otherwise_valid_whole_run(monkeypatch):
    pending, rows, evidence = retained_manual_case('buy_fee_conflict')
    unrelated = dict(pending[0], symbol='UNRELATED.PA', isin='FR0000000010',
        comment=pending[0]['comment'][:-1] + ('0' if pending[0]['comment'][-1] != '0' else '1'))
    replay_manual_calendar_day(monkeypatch, 'constructed_whole_run_fee_refusal',
        [unrelated] + pending, rows, evidence, 1)


@pytest.mark.parametrize('order', ['exact_first', 'conflict_first'])
def test_manual_calendar_day_recognized_row_cannot_hide_conflicting_proposal(monkeypatch, order):
    pending, rows, evidence = retained_manual_case('buy_equal')
    conflict = dict(pending[0], fee='2.15', comment=pending[0]['comment'][:-1] +
        ('0' if pending[0]['comment'][-1] != '0' else '1'))
    pending = pending + [conflict] if order == 'exact_first' else [conflict] + pending
    replay_manual_calendar_day(monkeypatch, 'constructed_recognized_row_fee_conflict_' + order,
        pending, rows, evidence, 1)


@pytest.mark.parametrize('variant', ['missing_file', 'hash_mismatch', 'wrong_day', 'wrong_timezone',
    'wrong_activity', 'wrong_account', 'declaration_only'])
def test_manual_calendar_day_unverified_retained_context_refuses(monkeypatch, variant):
    pending, rows, evidence = retained_manual_case('buy_equal')
    entry = evidence['activities'][rows[0]['remote_id']]
    path = Path(entry['provenance']['path'])
    context = b.read_keyed_yaml(path, Path.cwd(), 1024 * 1024)
    if variant == 'missing_file':
        entry['provenance']['path'] = 'missing-entry.yaml'
    elif variant == 'hash_mismatch':
        entry['provenance']['sha256'] = '0' * 64
    elif variant == 'declaration_only':
        entry['provenance'] = 'declared day without retained context'
    else:
        key, value = {'wrong_day': ('entered_day', '2019-02-07'), 'wrong_timezone': ('entry_timezone', 'unknown/zone'),
            'wrong_activity': ('activity_id', 'synthetic-other'), 'wrong_account': ('account_id', 'other')}[variant]
        context[key] = value
        b.atomic_private_yaml(path, context)
        entry['provenance']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    name = 'constructed_invalid_evidence_declaration_only' if variant == 'declaration_only' else 'constructed_unknown_context_' + variant
    replay_manual_calendar_day(monkeypatch, name, pending, rows, evidence, 1)


def test_manual_calendar_day_sync_validates_context_before_broker(tmp_path, monkeypatch):
    """Exercise the real sync entry point; only external acquisition is substituted."""
    import sys
    from types import SimpleNamespace

    pending, rows, evidence = retained_manual_case('buy_equal')
    evidence['schema_version'] = True
    b.atomic_private_yaml(tmp_path / 'manual-day-context.yaml', evidence)
    calls = []

    def broker(*args, **kwargs):
        calls.append('broker')
        pytest.fail('broker reached before invalid day-context refusal')

    acquisition = SimpleNamespace(broker_lock=lambda root: None, broker_login_ready=lambda root: None,
        discovery_receipt=lambda root: None, ghostfolio_origin=lambda origin: None,
        account_binding_path=lambda root, source: root / 'binding.yaml',
        saved_account_binding=lambda *args: None, reconcile_binding=lambda *args: None,
        ghostfolio_snapshot=lambda *args, **kwargs: ([], [], b'{"count":0,"activities":[]}', None),
        choose=lambda *args: None, acquire=broker, wait_proxy_ready=lambda proxy: None,
        close_proxy=lambda proxy: None, MAX_BYTES=1024 * 1024)
    monkeypatch.setitem(sys.modules, 'community_connect', acquisition)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(b, 'buy_simulation_config', lambda: {'source_ref': ACCOUNT['source_account_ref'],
        'target': ACCOUNT['target_account_id'], 'origin': 'https://synthetic.invalid', 'mappings': MAPPING})
    monkeypatch.setattr(b, 'parse_remote_activity_snapshot', lambda *args, **kwargs: rows)
    import subprocess
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: SimpleNamespace())
    for key in list(b.os.environ):
        if key.startswith('BW_') or key == 'GHOST_ACCESS_TOKEN':
            monkeypatch.delenv(key)
    real_path = Path
    monkeypatch.setattr(b, 'Path', lambda value: tmp_path if value == '/state' else real_path(value))
    previous_umask = b.os.umask(0o077)
    try:
        with pytest.raises(RuntimeError, match='NOTICE_DAY_CONTEXT_INVALID'):
            b.sync_buy_simulation()
    finally:
        b.os.umask(previous_umask)
    assert not calls
    print('constructed_real_sync_guard: invalid_context_refused broker_attempts=0 financial_writes=0 confirmation_requests=0')


def test_manual_calendar_day_distinct_exact_financial_groups(monkeypatch):
    pending, rows, _ = retained_manual_case('buy_equal')
    second = dict(pending[0], fee='2.15', comment=pending[0]['comment'][:-1] +
        ('0' if pending[0]['comment'][-1] != '0' else '1'))
    rows.append(dict(rows[0], remote_id='synthetic-second', fee=Decimal('2.15')))
    replay_manual_calendar_day(monkeypatch, 'constructed_distinct_exact_fee_groups', pending + [second],
        rows, day_evidence(rows, pending[0]['date'][:10]), 0, duplicates=2)

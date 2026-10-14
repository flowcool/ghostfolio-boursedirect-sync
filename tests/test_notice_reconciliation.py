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


def day_evidence(rows, civil_day=None, entry_timezone=None):
    """Constructed entry provenance, never inferred from runtime/server timezone."""
    activities = {}
    for row in rows:
        day = civil_day or row['operation_date']
        # Explicitly constructed historical entry capture, not a server-TZ inference.
        context = {'schema_version': 1, 'activity_id': row['remote_id'],
            'account_id': row['target_account_id'], 'stored_date': row['stored_date'],
            'financial_fingerprint': b.activity_financial_fingerprint(row),
            'entered_day': day, 'entry_timezone': entry_timezone or ('UTC' if day == row['operation_date'] else 'Europe/Zurich')}
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
        b.reconcile_notice_holdings([later_buy, sell], [baseline],
            day_context=day_evidence([baseline]), evidence_root=Path.cwd())
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
    assert b.reconcile_notice_holdings([sell], [confirmed], project_buys=False,
        represented={confirmed['remote_id']: buy}) == [sell]
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
    baseline = remote(buy, date='2018-01-01T00:00:00.000Z')
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

    def replay(progress=None):
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
            assert next(item for item in diagnostics if 'reason' in item)['reason'] == reason
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
        'target': ACCOUNT['target_account_id'], 'origin': 'https://synthetic.invalid', 'mappings': MAPPING, 'dry_run': True})
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


@pytest.mark.parametrize('fixture', ['note-sell-anonymized-real.html', 'note-coupon-anonymized-real.html'])
def test_manual_calendar_day_manual_dividend_equivalence_real_sync(tmp_path, monkeypatch, capsys, fixture):
    """Real sync pipeline with anonymized retained notices and isolated acquisition."""
    import builtins
    import re
    import socket
    import subprocess
    import sys
    from types import SimpleNamespace
    from unittest.mock import Mock

    raw = (Path(__file__).parent / 'fixtures' / fixture).read_bytes()
    if 'coupon' in fixture:
        # Labelled constructed chronology: keep retained amounts inside the isolated window.
        raw = raw.replace(b'02/07/2026', b'02/09/2026')
    document = b.parse_contract_note(b.decode_document(raw), 16, include_coupons=True, notice_sync=True)
    pending = proposals(document)
    stored_date = ('2026-09-02T15:00:00.000Z' if 'coupon' in fixture
        else MANUAL_CASES['sell_equal']['stored_date'])
    rows = [remote(proposal, marker=False, id=f'synthetic-trade-{index}', date=stored_date)
        for index, proposal in enumerate(pending)]
    for row in rows:
        if row['kind'] == 'DIVIDEND':
            row['quantity'] = Decimal('2')
            row['unit_price'] /= 2
    evidence = day_evidence(rows, pending[0]['date'][:10])
    b.atomic_private_yaml(tmp_path / 'manual-day-context.yaml', evidence)
    wire_rows = [{'id': row['remote_id'], 'accountId': proposal['accountId'],
        'account': {'id': proposal['accountId'], 'tags': []}, 'tags': [],
        'type': proposal['type'], 'date': stored_date, 'currency': 'EUR', 'comment': None,
        'quantity': row['quantity'], 'unitPrice': row['unit_price'], 'fee': row['fee'],
        'assetProfile': {'symbol': proposal['symbol'], 'currency': 'EUR', 'dataSource': 'YAHOO'}}
        for row, proposal in zip(rows, pending)]
    encoded = json.dumps({'count': len(wire_rows), 'activities': wire_rows},
        default=lambda number: 'DECIMAL:' + str(number))
    snapshot = re.sub(r'"DECIMAL:([-0-9.]+)"', r'\1', encoded).encode()
    original_rows = copy.deepcopy(rows)
    calls = []

    def forbidden(*args, **kwargs):
        pytest.fail('network access or confirmation requested during isolated sync')

    def acquire(run, as_of, account, *args, **kwargs):
        calls.append('isolated_acquisition')
        b.atomic_private_bytes(run / 'notice.html', raw)
        b.atomic_private_yaml(run / 'document-1.yaml', {'role': 'contract_note',
            'path': 'notice.html', 'sha256': hashlib.sha256(raw).hexdigest()})
        coverage = {'complete': True, 'window': {'first_day': '2026-07-16', 'last_day': as_of},
            'expected_months': ['2026-07', '2026-08', '2026-09', '2026-10'],
            'observed_months': {'PEA': ['2026-07', '2026-08', '2026-09', '2026-10']},
            'empty_months': {'PEA': ['2026-07', '2026-08', '2026-10']}}
        b.atomic_private_yaml(run / 'qualification.yaml', {'notice_coverage': coverage,
            'account_binding': account, 'session_logged_out': True, 'browser_exit_verified': True})
        return account, {'complete': True, 'monthly_statements': 0, 'contract_notes': 1}

    acquisition = SimpleNamespace(ROOT=tmp_path, MAX_BYTES=1024 * 1024,
        broker_lock=lambda root: None, broker_login_ready=lambda root: None,
        discovery_receipt=lambda root: None, ghostfolio_origin=lambda origin: None,
        account_binding_path=lambda root, source: root / 'binding.yaml',
        saved_account_binding=lambda *args: None, reconcile_binding=lambda *args: None,
        ghostfolio_snapshot=lambda *args, **kwargs: (
            [{'id': ACCOUNT['target_account_id'], 'name': 'Synthetic account'}], [], snapshot, forbidden),
        choose=lambda *args: None, acquire=acquire, wait_proxy_ready=lambda proxy: None,
        close_proxy=lambda proxy: None)
    monkeypatch.setitem(sys.modules, 'community_connect', acquisition)
    monkeypatch.setattr(sys, 'path', list(sys.path))
    monkeypatch.setattr(b, 'buy_simulation_config', lambda: {'source_ref': ACCOUNT['source_account_ref'],
        'target': ACCOUNT['target_account_id'], 'origin': 'https://synthetic.invalid', 'mappings': MAPPING, 'dry_run': True})
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(builtins, 'input', forbidden)
    for key in list(b.os.environ):
        if key.startswith('BW_') or key == 'GHOST_ACCESS_TOKEN':
            monkeypatch.delenv(key)
    real_path, real_datetime = Path, b.datetime
    monkeypatch.setattr(b, 'Path', lambda value: tmp_path if value == '/state' else real_path(value))
    fixed_datetime = Mock(wraps=real_datetime)
    fixed_datetime.now.return_value = real_datetime.fromisoformat('2026-10-13T12:00:00+00:00')
    monkeypatch.setattr(b, 'datetime', fixed_datetime)
    real_reconcile = b.reconcile_notice_duplicates

    def checked_reconcile(actual_proposals, actual_rows, actual_evidence, actual_root, represented):
        assert actual_evidence == evidence and actual_root == tmp_path
        assert actual_proposals == pending
        # The replay re-encodes an equivalent dividend quantity/price projection.
        assert [{k: v for k, v in row.items() if k != 'stored_activity'} for row in actual_rows] == [
            {k: v for k, v in row.items() if k != 'stored_activity'} for row in original_rows]
        calls.append('reconcile_received_valid_evidence')
        before = copy.deepcopy(actual_rows)
        result = real_reconcile(actual_proposals, actual_rows, actual_evidence, actual_root, represented)
        assert actual_rows == before
        return result

    monkeypatch.setattr(b, 'reconcile_notice_duplicates', checked_reconcile)
    previous_umask = b.os.umask(0o077)
    try:
        assert b.main(['--sync']) == 0
    finally:
        b.os.umask(previous_umask)
    output = capsys.readouterr().out
    print(output, end='')
    diagnostics = [json.loads(line) for line in output.splitlines()]
    assert diagnostics[-1] == {'code': 'NOTICE_SIMULATION_COMPLETED', 'proposed': 0,
        'imported': 0, 'skipped': 0, 'failed_rows': 0, 'duplicates': len(pending),
        'contract_notes': 1, 'financial_writes': 0}
    assert calls == ['isolated_acquisition', 'reconcile_received_valid_evidence']
    artifacts = list((tmp_path / 'runs').glob('*/simulation.yaml'))
    assert len(artifacts) == 1
    saved = b.read_keyed_yaml(artifacts[0], tmp_path, 1024 * 1024)
    assert saved['duplicates'] == len(pending) and saved['proposals'] == []
    assert saved['financial_writes'] == saved['imported'] == 0
    assert b.read_keyed_yaml(tmp_path / 'manual-day-context.yaml', tmp_path, 1024 * 1024) == evidence
    print(f'constructed_real_sync_success: fixture={fixture} valid_context_loaded_and_forwarded '
        f'duplicates={len(pending)} proposed=0 '
        'financial_writes=0 confirmation_requests=0 existing_fields_unchanged=true')


DIVIDEND_CASE = json.loads((Path(__file__).parent / 'fixtures' /
    'notice-manual-dividend-anonymized-real.json').read_text())


def manual_dividend_case():
    """Constructed equality using scaled retained net-credit evidence."""
    proposal = dict(proposals()[0], type='DIVIDEND', quantity='1',
        unitPrice=DIVIDEND_CASE['source_net_credit'], fee='0', execution_time=None)
    row = remote(proposal, marker=False, date='2019-02-06T15:00:00.000Z')
    return [proposal], [row], day_evidence([row], '2019-02-06')


def test_manual_dividend_equivalence_retained_mismatch(monkeypatch):
    pending, _, _ = manual_dividend_case()
    row = remote(pending[0], marker=False, date=DIVIDEND_CASE['stored_date'],
        quantity=Decimal(DIVIDEND_CASE['destination_quantity']),
        unitPrice=Decimal(DIVIDEND_CASE['destination_unit_price']),
        fee=Decimal(DIVIDEND_CASE['destination_fee']))
    # Retained mismatch with explicitly constructed historical day context.
    replay_manual_calendar_day(monkeypatch, 'retained_dividend_mismatch_constructed_day',
        pending, [row], day_evidence([row], '2019-02-02'), 1)


@pytest.mark.parametrize('quantity,price', [('1', '20.9198'), ('2', '10.4599'),
    ('0.1', '209.198')])
def test_manual_dividend_equivalence_equal_total(monkeypatch, quantity, price):
    pending, rows, _ = manual_dividend_case()
    rows[0].update(quantity=Decimal(quantity), unit_price=Decimal(price))
    replay_manual_calendar_day(monkeypatch, 'constructed_dividend_equal_representation_' + quantity,
        pending, rows, day_evidence(rows, '2019-02-06'), 0, duplicates=1)


@pytest.mark.parametrize('field,value', [('fee', Decimal('0.01')), ('price_currency', 'USD'),
    ('data_source', 'MANUAL'), ('unit_price', Decimal('20.9199')),
    ('financial_context_verified', False), ('active', False)])
def test_manual_dividend_equivalence_conflicting_context(monkeypatch, field, value):
    pending, rows, _ = manual_dividend_case()
    rows[0][field] = value
    replay_manual_calendar_day(monkeypatch, 'constructed_dividend_conflict_' + field,
        pending, rows, day_evidence(rows, '2019-02-06'), 1)


def test_manual_dividend_equivalence_unknown_day(monkeypatch):
    pending, rows, _ = manual_dividend_case()
    monkeypatch.setenv('TZ', 'Europe/Zurich')
    rows[0]['operation_date'] = '2000-01-01'
    replay_manual_calendar_day(monkeypatch, 'constructed_dividend_unknown_day', pending, rows,
        {'schema_version': 1, 'activities': {}}, 1)


def test_manual_dividend_equivalence_civil_boundary(monkeypatch):
    pending, rows, _ = manual_dividend_case()
    rows[0] = remote(pending[0], marker=False, date='2019-02-05T23:00:00.000Z')
    replay_manual_calendar_day(monkeypatch, 'constructed_dividend_civil_boundary', pending, rows,
        day_evidence(rows, '2019-02-06'), 0, duplicates=1)


@pytest.mark.parametrize('source_count,destination_count', [(2, 1), (1, 2), (2, 2)])
def test_manual_dividend_equivalence_multiplicity(monkeypatch, source_count, destination_count):
    pending, rows, _ = manual_dividend_case()
    if source_count == 2:
        pending.append(dict(pending[0], quantity='2', unitPrice='10.4599',
            comment=pending[0]['comment'][:-1] + ('0' if pending[0]['comment'][-1] != '0' else '1')))
    if destination_count == 2:
        rows.append(dict(rows[0], remote_id='synthetic-second', quantity=Decimal('0.1'),
            unit_price=Decimal('209.198')))
    status = int(source_count != destination_count)
    replay_manual_calendar_day(monkeypatch,
        f'constructed_dividend_multiplicity_{source_count}_{destination_count}', pending, rows,
        day_evidence(rows, '2019-02-06'), status, duplicates=source_count if not status else 0)


@pytest.mark.parametrize('order', ['exact_first', 'conflict_first'])
def test_manual_dividend_equivalence_exact_cannot_hide_conflict(monkeypatch, order):
    pending, rows, _ = manual_dividend_case()
    rows.append(dict(rows[0], remote_id='synthetic-conflict', fee=Decimal('.01')))
    rows = rows if order == 'exact_first' else list(reversed(rows))
    replay_manual_calendar_day(monkeypatch, 'constructed_dividend_exact_plus_fee_conflict_' + order,
        pending, rows, day_evidence(rows, '2019-02-06'), 1)


@pytest.mark.parametrize('change,code', [({}, None),
    ({'quantity': Decimal('2'), 'unitPrice': Decimal('10.4599')}, 'NOTICE_OWNED_ACTIVITY_CONFLICT'),
    ({'date': '2019-02-06T15:00:00.000Z'}, 'NOTICE_OWNED_ACTIVITY_CONFLICT')])
def test_manual_dividend_equivalence_owned_stays_exact(monkeypatch, change, code):
    pending, _, _ = manual_dividend_case()
    rows = [remote(pending[0], **change)]
    original = copy.deepcopy(rows)
    if code:
        with pytest.raises(RuntimeError, match=code):
            reconcile(pending, rows)
    else:
        replay_manual_calendar_day(monkeypatch, 'constructed_dividend_owned_exact', pending, rows,
            {'schema_version': 1, 'activities': {}}, 0, duplicates=1)
    assert rows == original
    print('constructed_dividend_owned: exact_fields_required=true financial_writes=0 confirmation_requests=0')


def test_manual_dividend_equivalence_other_account_or_instrument_is_not_duplicate():
    pending, rows, _ = manual_dividend_case()
    for changes in ({'target_account_id': 'other'}, {'symbol': 'OTHER.PA'}, {'kind': 'BUY'}):
        unrelated = dict(rows[0], **changes)
        assert reconcile(pending, [unrelated], day_evidence([unrelated])) == (pending, 0)
    print('constructed_dividend_unrelated: duplicates=0 proposed=1 financial_writes=0 confirmation_requests=0')


def test_manual_dividend_equivalence_exact_decimal_product(monkeypatch):
    pending, rows, _ = manual_dividend_case()
    quantity = Decimal('1.123456789012345678901234567890123456789')
    price = Decimal('2.123456789012345678901234567890123456789')
    with localcontext() as context:
        context.prec = 100
        total = quantity * price
    pending[0]['unitPrice'] = str(total)
    rows[0].update(quantity=quantity, unit_price=price)
    with localcontext() as context:
        context.prec = 6
        replay_manual_calendar_day(monkeypatch, 'constructed_dividend_exact_decimal_product', pending,
            rows, day_evidence(rows), 0, duplicates=1)


def retained_dividend_report_case():
    pending, _, _ = manual_dividend_case()
    row = remote(pending[0], marker=False, date=DIVIDEND_CASE['stored_date'],
        quantity=Decimal(DIVIDEND_CASE['destination_quantity']),
        unitPrice=Decimal(DIVIDEND_CASE['destination_unit_price']),
        fee=Decimal(DIVIDEND_CASE['destination_fee']))
    return pending, [row], day_evidence([row], row['operation_date'])


def replay_similar_activity_report(monkeypatch, name, pending, rows, evidence, status, duplicates=0):
    """Replay reconciliation at the shared pre-dispatch boundary, offline."""
    from contextlib import redirect_stdout
    from io import StringIO
    output = StringIO()
    with redirect_stdout(output):
        replay_manual_calendar_day(monkeypatch, name, pending, rows, evidence, status, duplicates)
    print(output.getvalue(), end='')
    diagnostics = [json.loads(line) for line in output.getvalue().splitlines()]
    reports = [item for item in diagnostics if item.get('code') == 'NOTICE_SIMILAR_ACTIVITY']
    if status:
        first_refusal = next(i for i, item in enumerate(diagnostics)
            if item.get('code') == 'NOTICE_MANUAL_OVERLAP_AMBIGUOUS')
        assert all(i < first_refusal for i, item in enumerate(diagnostics)
            if item.get('code') == 'NOTICE_SIMILAR_ACTIVITY')
    return reports


def test_similar_activity_report_retained_dividend_and_constructed_civil_boundary(monkeypatch):
    pending, rows, evidence = retained_dividend_report_case()
    reports = replay_similar_activity_report(monkeypatch, 'retained_dividend_mismatch',
        pending, rows, evidence, 1)
    assert len(reports) == 1
    assert reports[0]['source_total'] == '20.9198'
    assert reports[0]['destination_total'] == '28.416'
    assert reports[0]['total_difference_eur'] == '7.4962'
    # Retained clock/separation; constructed historical entry provenance.
    boundary = DIVIDEND_CASE['civil_boundary_evidence']
    pending[0]['date'] = boundary['source_day'] + 'T00:00:00.000Z'
    rows[0]['stored_date'] = boundary['stored_date']
    rows[0]['operation_date'] = boundary['stored_date'][:10]
    reports = replay_similar_activity_report(monkeypatch, 'constructed_dividend_utc_civil_boundary',
        pending, rows, day_evidence(rows, boundary['civil_day'], boundary['entry_timezone']), 1)
    assert reports[0]['day_gap'] == -3 and reports[0]['day_provenance'] == 'verified'
    assert reports[0]['status'] == 'review_required'
    assert reports[0]['fee_difference_eur'] == '0'


@pytest.mark.parametrize('kind,window', [('BUY', 3), ('SELL', 3), ('DIVIDEND', 4)])
def test_similar_activity_report_inclusive_windows_without_amount_filter(monkeypatch, kind, window):
    from datetime import date, timedelta
    pending = proposals()
    pending[0]['type'] = kind
    source_total = Decimal(pending[0]['quantity']) * Decimal(pending[0]['unitPrice'])
    rows = []
    for i, gap in enumerate((-window - 1, -window, window, window + 1)):
        day = (date.fromisoformat(pending[0]['date'][:10]) + timedelta(days=gap)).isoformat()
        rows.append(remote(pending[0], marker=False, id='synthetic-window-' + str(i),
            date=day + 'T00:00:00.000Z', quantity=Decimal(1),
            unitPrice=source_total + Decimal(i + 1) * 1000, fee=Decimal(i + 1)))
    rows.extend([dict(rows[1], remote_id='other-account', target_account_id='other'),
        dict(rows[1], remote_id='other-instrument', symbol='OTHER.PA'),
        dict(rows[1], remote_id='other-type', kind='FEE')])
    reports = replay_similar_activity_report(monkeypatch, 'constructed_window_fee_' + kind,
        pending, list(reversed(rows)), day_evidence(rows), 1)
    assert [item['day_gap'] for item in reports] == [-window, window]
    assert [item['total_difference_eur'] for item in reports] == ['2000', '3000']
    assert [item['fee_difference_eur'] for item in reports] == ['0.1', '1.1']
    assert all(Decimal(item['total_difference_percent']) > 0 for item in reports)


def test_similar_activity_report_before_after_manual_reconciliation(monkeypatch):
    pending, rows, evidence = retained_dividend_report_case()
    replay_similar_activity_report(monkeypatch, 'retained_dividend_before_reconciliation',
        pending, rows, evidence, 1)
    pending, rows, evidence = manual_dividend_case()
    rows[0].update(quantity=Decimal(2), unit_price=Decimal('10.4599'))
    reports = replay_similar_activity_report(monkeypatch, 'constructed_dividend_after_reconciliation',
        pending, rows, day_evidence(rows), 0, duplicates=1)
    assert reports[0]['status'] == 'automatic_duplicate'
    assert reports[0]['total_difference_eur'] == reports[0]['total_difference_percent'] == '0'
    rows.append(dict(rows[0], remote_id='synthetic-remaining', unit_price=Decimal('10.5')))
    reports = replay_similar_activity_report(monkeypatch, 'constructed_dividend_remaining_conflict',
        pending, rows, day_evidence(rows), 1)
    assert [item['status'] for item in reports] == ['automatic_duplicate', 'review_required']


@pytest.mark.parametrize('mode', ['1', '0'])
def test_similar_activity_report_all_rows_before_refusal(monkeypatch, mode):
    monkeypatch.setenv('DRY_RUN', mode)
    pending, rows, _ = retained_manual_case('buy_equal')
    rows.append(dict(rows[0], remote_id='synthetic-ambiguous'))
    evidence = day_evidence(rows)
    second = dict(pending[0], symbol='SECOND.PA', comment=pending[0]['comment'][:-1] +
        ('0' if pending[0]['comment'][-1] != '0' else '1'))
    pending.append(second)
    rows.append(dict(rows[0], remote_id='synthetic-unknown', symbol='SECOND.PA',
        financial_context_verified=False))
    reports = replay_similar_activity_report(monkeypatch, 'constructed_multiplicity_multirow_mode_' + mode,
        pending, rows, evidence, 1)
    assert len(reports) == 3
    last = reports[-1]
    assert last['day_gap'] == last['destination_day'] == 'unverified'
    assert last['financial_context'] == last['total_difference_eur'] == last['total_difference_percent'] == 'unverified'
    assert all(item['status'] == 'review_required' for item in reports)
    print(json.dumps({'scenario': 'constructed_pre_dispatch_mode_' + mode,
        'boundary': 'reconciliation_only_not_actual_import_acceptance', 'financial_writes': 0}))


def test_similar_activity_report_negative_difference_zero_source_and_owned(monkeypatch):
    pending, rows, _ = manual_dividend_case()
    rows[0]['unit_price'] = Decimal('10.4599')
    reports = replay_similar_activity_report(monkeypatch, 'constructed_dividend_negative_difference',
        pending, rows, day_evidence(rows), 1)
    assert reports[0]['total_difference_eur'] == '-10.4599'
    assert reports[0]['total_difference_percent'] == '-50'
    pending[0]['unitPrice'] = '0'
    reports = replay_similar_activity_report(monkeypatch, 'constructed_dividend_zero_source',
        pending, rows, day_evidence(rows), 1)
    assert reports[0]['total_difference_percent'] == 'unverified'
    pending[0]['unitPrice'] = DIVIDEND_CASE['source_net_credit']
    rows = [remote(pending[0])]
    reports = replay_similar_activity_report(monkeypatch, 'constructed_owned_report',
        pending, rows, {'schema_version': 1, 'activities': {}}, 0, duplicates=1)
    assert reports[0]['status'] == 'automatic_duplicate'


def test_similar_activity_report_represented_other_notice_and_exact_precision(monkeypatch):
    pending, rows, _ = manual_dividend_case()
    second = dict(pending[0], unitPrice='21', comment=pending[0]['comment'][:-1] +
        ('0' if pending[0]['comment'][-1] != '0' else '1'))
    pending.append(second)
    rows.append(remote(second, marker=False, id='synthetic-second'))
    reports = replay_similar_activity_report(monkeypatch, 'constructed_two_represented_notices',
        pending, rows, day_evidence(rows), 0, duplicates=2)
    assert [item['status'] for item in reports] == [
        'automatic_duplicate', 'represented_other_notice', 'automatic_duplicate', 'represented_other_notice']
    quantity = Decimal('1.123456789012345678901234567890123456789')
    price = Decimal('2.123456789012345678901234567890123456789')
    with localcontext() as context:
        context.prec = 100
        total = quantity * price
    pending = [dict(pending[0], unitPrice=str(total))]
    rows = [remote(pending[0], marker=False, quantity=quantity, unitPrice=price)]
    evidence = day_evidence(rows)
    with localcontext() as context:
        context.prec = 6
        reports = replay_similar_activity_report(monkeypatch, 'constructed_report_exact_decimal_product',
            pending, rows, evidence, 0, duplicates=1)
    assert reports[0]['destination_total'] == str(total)
    assert reports[0]['total_difference_eur'] == '0'


def dated_trade(kind, day, quantity, time=None, index=1):
    """Labelled constructed chronology, scaled from the anonymized real BUY."""
    return dict(proposals()[0], type=kind, date=day + 'T00:00:00.000Z',
        quantity=str(quantity), execution_time=time,
        comment=proposals()[0]['comment'].rsplit('#', 1)[0] + '#' + f'{index:064x}')


def replay_chronological_holdings(monkeypatch, name, source, rows, code=None,
                                  project_buys=True, evidence=None):
    """Replay the real reconciliation boundary with writes and prompts forbidden."""
    import builtins
    import socket
    from contextlib import redirect_stdout
    from io import StringIO
    monkeypatch.setattr(builtins, 'input', lambda *a, **k: pytest.fail('confirmation requested'))
    monkeypatch.setattr(socket, 'socket', lambda *a, **k: pytest.fail('financial/network access'))
    original = copy.deepcopy((source, rows))
    represented, output = {}, StringIO()
    with redirect_stdout(output):
        pending, duplicates = b.reconcile_notice_duplicates(source, rows, evidence, Path.cwd(), represented)
        if code:
            with pytest.raises(RuntimeError, match=code):
                b.reconcile_notice_holdings(pending, rows, project_buys, represented, evidence, Path.cwd())
        else:
            b.reconcile_notice_holdings(pending, rows, project_buys, represented, evidence, Path.cwd())
    assert (source, rows) == original
    print(output.getvalue(), end='')
    print(json.dumps({'scenario': name, 'outcome': code or 'passed', 'duplicates': duplicates,
        'financial_writes': 0, 'confirmation_requests': 0}))
    diagnostics = [json.loads(line) for line in output.getvalue().splitlines()]
    return diagnostics, represented


def test_chronological_holdings_later_existing_buy_cannot_fund_sale(monkeypatch):
    sale = dated_trade('SELL', '2026-09-01', 20, '10:00:00')
    purchase = dated_trade('BUY', '2026-09-10', 50)
    rows = [remote(purchase, marker=False)]
    diagnostics, _ = replay_chronological_holdings(monkeypatch, 'constructed_later_existing_buy',
        [sale], rows, 'NOTICE_INSUFFICIENT_HOLDINGS', evidence=day_evidence(rows))
    assert diagnostics[-1]['sale_day'] == '2026-09-01'
    assert diagnostics[-1]['available'] == '0' and diagnostics[-1]['sale'] == '20'


def test_chronological_holdings_old_stock_prior_sale_and_pending_buy(monkeypatch):
    old = dated_trade('BUY', '2019-01-01', 50)
    old_sale = dated_trade('SELL', '2020-01-01', 40)
    rows = [remote(old, marker=False, id='old-buy'), remote(old_sale, marker=False, id='old-sale')]
    purchase = dated_trade('BUY', '2026-09-01', 15, '09:00:00', 2)
    sale = dated_trade('SELL', '2026-09-01', 20, '10:00:00', 3)
    diagnostics, _ = replay_chronological_holdings(monkeypatch, 'constructed_old_stock_and_preceding_purchase',
        [sale, purchase], rows, evidence=day_evidence(rows))
    assert diagnostics[-1]['preceding_day_available'] == '10'
    assert diagnostics[-1]['available'] == '25'


@pytest.mark.parametrize('buy_time,expected', [(None, 'NOTICE_HOLDINGS_ORDER_UNPROVED'),
    ('09:00:00', None), ('10:00:00', 'NOTICE_HOLDINGS_ORDER_UNPROVED'),
    ('11:00:00', 'NOTICE_INSUFFICIENT_HOLDINGS')])
@pytest.mark.parametrize('representation', ['pending', 'owned', 'manual'])
def test_chronological_holdings_same_day_source_order(monkeypatch, buy_time, expected, representation):
    purchase = dated_trade('BUY', '2026-09-01', 50, buy_time, 1)
    sale = dated_trade('SELL', '2026-09-01', 20, '10:00:00', 2)
    rows = [] if representation == 'pending' else [remote(purchase, marker=representation == 'owned',
        date=purchase['date'] if representation == 'owned' else '2026-09-01T08:00:00.000Z')]
    diagnostics, _ = replay_chronological_holdings(monkeypatch,
        f'constructed_same_day_{representation}_{buy_time}', [purchase, sale], rows, expected,
        evidence=day_evidence(rows))
    report = diagnostics[-1]
    assert report['available'] == ('50' if buy_time == '09:00:00' else '0')
    if expected == 'NOTICE_HOLDINGS_ORDER_UNPROVED':
        assert report['dependent_purchases'][0]['missing_evidence'] == 'strict_source_execution_order'


def test_chronological_holdings_prior_stock_covers_all_sales_without_buy_order(monkeypatch):
    old = dated_trade('BUY', '2026-01-01', 40, index=10)
    purchase = dated_trade('BUY', '2026-09-01', 50)
    sale = dated_trade('SELL', '2026-09-01', 20, '10:00:00', 2)
    second = dated_trade('SELL', '2026-09-01', 20, None, 3)
    diagnostics, _ = replay_chronological_holdings(monkeypatch, 'constructed_prior_stock_unknown_same_day_buy',
        [sale, purchase, second], [remote(old)])
    assert all(d['available'] == '20' for d in diagnostics if d['code'] == 'NOTICE_DATED_HOLDINGS')


def test_chronological_holdings_represented_once_and_rejected_buy_not_funding(monkeypatch):
    purchase = dated_trade('BUY', '2026-09-01', 10, '09:00:00')
    sale = dated_trade('SELL', '2026-09-01', 15, '10:00:00', 2)
    rows = [remote(purchase)]
    diagnostics, _ = replay_chronological_holdings(monkeypatch, 'constructed_represented_counted_once',
        [purchase, sale], rows, 'NOTICE_INSUFFICIENT_HOLDINGS')
    assert diagnostics[-1]['available'] == '10'
    purchase['quantity'] = '50'
    replay_chronological_holdings(monkeypatch, 'constructed_rejected_pending_purchase',
        [purchase, sale], [], 'NOTICE_INSUFFICIENT_HOLDINGS', project_buys=False)
    replay_chronological_holdings(monkeypatch, 'constructed_readback_confirmed_purchase',
        [purchase, sale], [remote(purchase)], project_buys=False)


def test_chronological_holdings_manual_clock_and_missing_day_prove_nothing(monkeypatch):
    purchase = dated_trade('BUY', '2026-09-01', 50)
    sale = dated_trade('SELL', '2026-09-01', 20, '10:00:00', 2)
    rows = [remote(purchase, marker=False, date='2026-09-01T08:00:00.000Z')]
    replay_chronological_holdings(monkeypatch, 'constructed_manual_clock_without_source_order',
        [sale], rows, 'NOTICE_HOLDINGS_ORDER_UNPROVED', evidence=day_evidence(rows))
    replay_chronological_holdings(monkeypatch, 'constructed_manual_missing_day',
        [sale], rows, 'NOTICE_HOLDINGS_CONTEXT_UNVERIFIED')


def test_chronological_holdings_equal_manual_rows_preserve_source_time_multiset(monkeypatch):
    first = dated_trade('BUY', '2026-09-01', 10, '09:00:00')
    second = dated_trade('BUY', '2026-09-01', 10, '11:00:00', 2)
    sale = dated_trade('SELL', '2026-09-01', 10, '10:00:00', 3)
    rows = [remote(first, marker=False, id='first'), remote(second, marker=False, id='second')]
    diagnostics, represented = replay_chronological_holdings(monkeypatch, 'constructed_equal_rows_source_time_multiset',
        [first, second, sale], rows, evidence=day_evidence(rows))
    assert diagnostics[-1]['available'] == '10'
    assert sorted(row['execution_time'] for row in represented.values()) == ['09:00:00', '11:00:00']


def test_chronological_holdings_prior_pending_buy_and_future_existing_sale(monkeypatch):
    purchase = dated_trade('BUY', '2026-08-01', 30, index=1)
    sale = dated_trade('SELL', '2026-09-01', 20, index=2)
    future = dated_trade('SELL', '2026-09-10', 30, index=3)
    diagnostics, _ = replay_chronological_holdings(monkeypatch, 'constructed_prior_pending_buy_future_sale',
        [sale, purchase], [remote(future)], 'NOTICE_INSUFFICIENT_HOLDINGS')
    assert diagnostics[0]['available'] == diagnostics[0]['preceding_day_available'] == '30'
    assert diagnostics[-1]['available'] == '10'
    assert diagnostics[-1]['sale_day'] == '2026-09-10'
    assert diagnostics[-1]['sale_origin'] == 'destination'
    replay_chronological_holdings(monkeypatch, 'constructed_prior_rejected_buy_future_sale',
        [sale, purchase], [remote(future)], 'NOTICE_INSUFFICIENT_HOLDINGS', project_buys=False)


def test_chronological_holdings_represented_sale_reserves_stock(monkeypatch):
    old = dated_trade('BUY', '2026-01-01', 30, index=10)
    first = dated_trade('SELL', '2026-09-01', 20, '09:00:00', 1)
    second = dated_trade('SELL', '2026-09-01', 20, '10:00:00', 2)
    diagnostics, _ = replay_chronological_holdings(monkeypatch, 'constructed_represented_sale_reserves_stock',
        [first, second], [remote(old, id='old'), remote(first, id='sale')], 'NOTICE_INSUFFICIENT_HOLDINGS')
    assert diagnostics[-1]['available'] == '10'
    candidate_positions = [i for i, d in enumerate(diagnostics) if d['code'] == 'NOTICE_SIMILAR_ACTIVITY']
    assert candidate_positions and max(candidate_positions) < len(diagnostics) - 1

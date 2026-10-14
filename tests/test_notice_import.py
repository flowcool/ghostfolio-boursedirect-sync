"""Offline import/readback regressions from anonymized real notice fields."""
import copy
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import boursedirect_to_ghostfolio as b
from test_notice_reconciliation import ACCOUNT, proposals


RETAINED_DERIVED_COUNT = json.loads((Path(__file__).parent / 'fixtures' /
    'notice-import-derived-count-anonymized-real.json').read_text())


def row(proposal, remote_id='synthetic-created', **changes):
    value = json.loads(b.notice_wire(proposal), parse_float=Decimal)['activities'][0]
    value.update(id=remote_id, account={'id': value['accountId'], 'tags': []}, tags=[],
        assetProfile={'symbol': value['symbol'], 'dataSource': 'YAHOO', 'currency': 'EUR'})
    value.update(changes)
    return value


def encode(rows, count=None):
    return json.dumps({'activities': rows, 'count': len(rows) if count is None else count},
        default=b.wire_number).encode()


def setup(tmp_path):
    config = {'origin': 'https://ghost.invalid'}
    path, journal = b.notice_write_journal(tmp_path, config, ACCOUNT)
    run = tmp_path / 'synthetic-run'
    run.mkdir()
    return config, path, journal, run


def test_confirmed_exact_response_readback_and_no_default_write(tmp_path, capsys):
    config, path, journal, run = setup(tmp_path)
    pending = proposals()
    calls = []
    def request(method, url, body):
        calls.append((method, url))
        retained = b.parse_keyed_yaml(path.read_bytes())
        assert retained['pending']['body'] == b.notice_wire(pending[0]).decode()
        assert retained['confirmed'] == {}
        value = row(pending[0])
        if method == 'POST':
            value.pop('account')
            value.pop('tags')
        return (201 if method == 'POST' else 200), encode([value])
    result = b.import_notice_proposals(pending, [], path, journal, run, request, {})
    assert result == {'financial_writes': 1, 'imported': 1, 'rejected': 0}
    assert calls == [('POST', '/api/v1/import'), ('GET', '/api/v1/activities')]
    saved = b.notice_write_journal(tmp_path, config, ACCOUNT)[1]
    assert saved['pending'] is None and saved['confirmed'] == {pending[0]['comment']: 'synthetic-created'}
    confirmed = b.parse_remote_activity_snapshot(encode([row(pending[0])]))
    repeat, duplicates = b.reconcile_notice_duplicates(pending, confirmed)
    assert repeat == [] and duplicates == 1
    assert b.import_notice_proposals(repeat, confirmed, path, saved, run,
        lambda *args: pytest.fail('repeat must send no request'), {})['financial_writes'] == 0
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    confirmation = next(line for line in logs if line.get('exact_readback') is True)
    assert set(confirmation) == {'code', 'comment', 'type', 'exact_response',
        'exact_readback', 'financial_writes', 'imported'}
    assert pending[0]['accountId'] not in json.dumps(logs)


@pytest.mark.parametrize('fault', ['timeout', 'redirect', 'server', 'empty', 'wrong_account',
    'wrong_date', 'wrong_symbol', 'wrong_amount', 'draft', 'inactive_readback', 'same_instant_different_date', 'changed_id', 'incomplete', 'lost_readback'])
def test_uncertain_outcomes_block_restart_without_any_replay(tmp_path, fault):
    config, path, journal, run = setup(tmp_path)
    pending = proposals()
    calls = []
    def request(method, url, body):
        calls.append(method)
        if fault == 'timeout' or method == 'GET' and fault == 'lost_readback':
            raise OSError('synthetic transport loss')
        if method == 'POST' and fault in ('redirect', 'server'):
            return (302 if fault == 'redirect' else 500), b'{}'
        value = row(pending[0])
        if method == 'POST':
            changes = {'wrong_account': {'accountId': 'other'}, 'wrong_date': {'date': '2019-02-05T23:00:00.000Z'},
                'wrong_amount': {'quantity': 13}, 'draft': {'isDraft': True}}
            value.update(changes.get(fault, {}))
            if fault == 'wrong_symbol':
                value['assetProfile']['symbol'] = 'OTHER.PA'
            return 201, encode([] if fault == 'empty' else [value])
        if fault == 'same_instant_different_date':
            value['date'] = '2019-02-06T01:00:00+01:00'
        if fault == 'inactive_readback':
            value['isActive'] = False
        if fault == 'changed_id':
            value['id'] = 'different'
        return 200, encode([value], count=2 if fault == 'incomplete' else 1)
    progress = {}
    with pytest.raises(RuntimeError, match='NOTICE_IMPORT_UNCONFIRMED'):
        b.import_notice_proposals(pending, [], path, journal, run, request, progress)
    assert progress == {'financial_writes': 1, 'imported': 0}
    assert calls.count('POST') == 1
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match='NOTICE_WRITE_UNRESOLVED'):
        b.notice_write_journal(tmp_path, config, ACCOUNT)
    assert path.read_bytes() == original


def test_rejected_symbol_does_not_block_other_symbol_or_fund_sell(tmp_path):
    config, path, journal, run = setup(tmp_path)
    buy = dict(proposals()[0], execution_time='09:00:00')
    other = dict(buy, symbol='OTHER.PA', isin='FR0000000010', comment=buy['comment'][:-1] + 'a', execution_time='10:00:00')
    sell = dict(buy, type='SELL', comment=buy['comment'][:-1] + 'b', execution_time='11:00:00')
    accepted, calls = [], []
    def request(method, url, body):
        if method == 'POST':
            sent = json.loads(body)['activities'][0]
            calls.append(sent['symbol'])
            if sent['symbol'] == buy['symbol']:
                return 400, json.dumps({'message': ['activities.0.symbol ("VERIFIED.PA") cannot be resolved by the data source ("YAHOO")']}).encode()
            accepted.append(row(other))
            return 201, encode(accepted)
        return 200, encode(accepted)
    result = b.import_notice_proposals([buy, other, sell], [], path, journal, run, request, {})
    assert result == {'financial_writes': 2, 'imported': 1, 'rejected': 2}
    assert calls == ['VERIFIED.PA', 'OTHER.PA']
    assert b.notice_write_journal(tmp_path, config, ACCOUNT)[1]['pending'] is None


def test_sell_requires_confirmed_buy_and_exact_readback(tmp_path):
    _, path, journal, run = setup(tmp_path)
    buy = dict(proposals()[0], execution_time='09:00:00')
    sell = dict(buy, type='SELL', comment=buy['comment'][:-1] + 'b', execution_time='10:00:00')
    accepted, calls = [], []
    def request(method, url, body):
        if method == 'POST':
            proposal = buy if not accepted else sell
            calls.append(proposal['type'])
            accepted.append(row(proposal, str(len(accepted))))
            return 201, encode([accepted[-1]])
        return 200, encode(accepted)
    assert b.import_notice_proposals([sell, buy], [], path, journal, run, request, {})['imported'] == 2
    assert calls == ['BUY', 'SELL']


def test_all_wire_precision_validated_before_any_post(tmp_path):
    _, path, journal, run = setup(tmp_path)
    pending = proposals()
    bad = dict(pending[0], quantity='9007199254740993', comment=pending[0]['comment'][:-1] + 'a')
    with pytest.raises(RuntimeError, match='WIRE_NUMERIC_PRECISION_LOSS'):
        b.import_notice_proposals(pending + [bad], [], path, journal, run,
            lambda *args: pytest.fail('no POST allowed'), {})
    assert not path.exists()


def test_later_sell_refusal_logs_prior_confirmed_write_counts(tmp_path, capsys):
    _, path, journal, run = setup(tmp_path)
    buy = dict(proposals()[0], execution_time='09:00:00')
    sell = dict(buy, type='SELL', comment=buy['comment'][:-1] + 'b', execution_time='10:00:00')
    calls = []
    def request(method, url, body):
        calls.append(method)
        if method == 'POST':
            return 201, encode([row(buy)])
        # A concurrent represented sale leaves only two shares after BUY readback.
        prior_sale = row(buy, 'synthetic-prior-sale', type='SELL', quantity=10,
            date='2018-01-01T00:00:00.000Z', comment=buy['comment'][:-1] + 'c')
        return 200, encode([row(buy), prior_sale])
    progress = {}
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.import_notice_proposals([buy, sell], [], path, journal, run, request, progress)
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert calls == ['POST', 'GET']
    assert progress == {'financial_writes': 1, 'imported': 1}
    assert logs[-1]['code'] == 'NOTICE_INSUFFICIENT_HOLDINGS'
    assert (logs[-1]['available'], logs[-1]['sale'], logs[-1]['financial_writes'], logs[-1]['imported']) == ('2', '12', 1, 1)


@pytest.mark.parametrize('active', [False, True, None])
def test_inactive_readback_never_confirms_or_funds_sale(active):
    buy = dict(proposals()[0], execution_time='09:00:00')
    sell = dict(buy, type='SELL', execution_time='10:00:00', comment=buy['comment'][:-1] + 'b')
    changes = {} if active is None else {'isActive': active}
    raw = encode([row(buy, **changes)])
    remote = b.parse_remote_activity_snapshot(raw)
    assert remote[0]['active'] is (active is not False)
    if active is False:
        with pytest.raises(RuntimeError, match='NOTICE_OWNED_ACTIVITY_CONFLICT'):
            b.notice_exact_readback(buy, raw, 'synthetic-created')
        with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
            b.reconcile_notice_holdings([sell], remote, project_buys=False,
                represented={'synthetic-created': buy})
    else:
        assert b.notice_exact_readback(buy, raw, 'synthetic-created')[1] == 'synthetic-created'
        assert b.reconcile_notice_holdings([sell], remote, project_buys=False,
            represented={'synthetic-created': buy}) == [sell]
    print(json.dumps({'code': 'OFFLINE_ACTIVE_READBACK_HOLDINGS_PROVEN',
        'isActive': active, 'readback_confirmed': active is not False,
        'sale_funded': active is not False, 'broker_attempts': 0, 'financial_writes': 0}))


@pytest.mark.parametrize('active', [0, 1, 'false', None])
def test_non_boolean_active_flag_refuses_snapshot(active):
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVE_FLAG_INVALID'):
        b.parse_remote_activity_snapshot(encode([row(proposals()[0], isActive=active)]))


@pytest.mark.parametrize('change', ['missing', 'financial', 'stored_date', 'active', 'metadata'])
def test_changed_existing_activity_keeps_write_uncertain(tmp_path, change):
    _, path, journal, run = setup(tmp_path)
    buy = proposals()[0]
    existing = row(buy, 'synthetic-existing', symbol='OTHER.PA', comment='unrelated',
        date='2018-01-01T00:00:00.000Z', note='retained metadata')
    existing['assetProfile']['symbol'] = 'OTHER.PA'
    original = copy.deepcopy(existing)
    remote = b.parse_remote_activity_snapshot(encode([existing]), retain_stored_date=True)
    changed = copy.deepcopy(existing)
    if change == 'financial':
        changed['fee'] = Decimal('9.9')
    elif change == 'stored_date':
        changed['date'] = '2018-01-01T01:00:00+01:00'
    elif change == 'active':
        changed['isActive'] = False
    elif change == 'metadata':
        changed['note'] = 'changed metadata'
    def request(method, url, body):
        return (201, encode([row(buy)])) if method == 'POST' else (
            200, encode([row(buy)] + ([] if change == 'missing' else [changed])))
    progress = {}
    with pytest.raises(RuntimeError, match='NOTICE_IMPORT_UNCONFIRMED'):
        b.import_notice_proposals([buy], remote, path, journal, run, request, progress)
    assert progress == {'financial_writes': 1, 'imported': 0}
    saved = b.parse_keyed_yaml(path.read_bytes())
    assert saved['pending'] is not None and saved['confirmed'] == {}
    assert existing == original


def retained_derived_count_case(proposal):
    observation = RETAINED_DERIVED_COUNT['observation']
    created = RETAINED_DERIVED_COUNT['created_activity']
    proposal = dict(proposal, type=created['type'], date=created['date'],
        quantity=created['quantity'], unitPrice=created['unitPrice'], fee=created['fee'],
        currency=created['currency'])
    existing = []
    for ordinal in range(observation['changed_existing_activities']):
        activity = row(proposal, 'anonymized-existing-' + str(ordinal),
            date=f'2018-01-{ordinal + 1:02d}T00:00:00.000Z', comment='unrelated-' + str(ordinal))
        activity['assetProfile']['activitiesCount'] = observation['activities_count_before']
        existing.append(activity)
    return proposal, existing


def retained_recovery_case(tmp_path):
    """Anonymized copy of the retained partial dividend import evidence shape."""
    config = {'origin': 'https://ghost.invalid'}
    path, journal = b.notice_write_journal(tmp_path, config, ACCOUNT)
    proposal, existing = retained_derived_count_case(proposals()[0])
    recovery = RETAINED_DERIVED_COUNT['recovery']
    created = row(proposal, recovery['remote_id'])
    created['assetProfile']['activitiesCount'] = RETAINED_DERIVED_COUNT['observation']['activities_count_after']
    saved = copy.deepcopy(existing)
    for activity in saved:
        activity['assetProfile']['activitiesCount'] = RETAINED_DERIVED_COUNT['observation']['activities_count_after']
    journal['pending'] = {'body': b.notice_wire(proposal).decode(),
        'run_id': recovery['run_id'], 'ordinal': recovery['ordinal']}
    b.atomic_private_yaml(path, journal)
    runs = b.private_directory(tmp_path / 'runs')
    run = b.private_directory(runs / recovery['run_id'])
    b.atomic_private_bytes(run / 'import-baseline.json', encode(existing))
    b.atomic_private_bytes(run / 'import-response-0.json', encode([created]))
    b.atomic_private_bytes(run / 'import-readback-0.json', encode(saved + [created]))
    remaining_data = recovery['remaining_activity']
    remaining = dict(proposal, type=remaining_data['type'], date=remaining_data['date'],
        symbol=remaining_data['symbol'], quantity=remaining_data['quantity'],
        unitPrice=remaining_data['unitPrice'], fee=remaining_data['fee'],
        currency=remaining_data['currency'], dataSource=remaining_data['dataSource'],
        comment=proposal['comment'][:-1] + ('a' if proposal['comment'][-1] != 'a' else 'b'))
    return config, path, proposal, remaining, saved + [created]


def test_explicit_recovery_proves_pending_without_post_or_broker_request(tmp_path, monkeypatch):
    config, path, proposal, remaining, fresh_rows = retained_recovery_case(tmp_path)
    recovery = RETAINED_DERIVED_COUNT['recovery']
    original = path.read_bytes()
    calls = []
    broker_requests = []

    def broker_request(*args, **kwargs):
        broker_requests.append(True)
        pytest.fail('recovery must not start a broker process')

    monkeypatch.setattr(b.subprocess, 'run', broker_request)
    monkeypatch.setattr(b.subprocess, 'Popen', broker_request)

    def request(method, url, body):
        calls.append((method, url, body))
        return 200, encode(fresh_rows)

    preview = b.recover_notice_write(tmp_path, config, ACCOUNT, recovery['run_id'],
        recovery['ordinal'], request, confirm=False)
    assert preview == {'matched': 1, 'confirmed': False,
        'snapshot_sha256': preview['snapshot_sha256'], 'ghostfolio_gets': 1,
        'financial_writes': 0, 'broker_attempts': 0}
    assert path.read_bytes() == original
    confirmed = b.recover_notice_write(tmp_path, config, ACCOUNT, recovery['run_id'],
        recovery['ordinal'], request, confirm=True)
    assert confirmed['confirmed'] is True
    assert calls == [('GET', '/api/v1/activities', None),
        ('GET', '/api/v1/activities', None)]
    assert broker_requests == []
    journal = b.notice_write_journal(tmp_path, config, ACCOUNT)[1]
    assert journal['pending'] is None
    assert journal['confirmed'] == {proposal['comment']: recovery['remote_id']}
    remote = b.parse_remote_activity_snapshot(encode(fresh_rows), retain_stored_date=True)
    pending, duplicates = b.reconcile_notice_duplicates([proposal, remaining], remote)
    assert pending == [remaining] and duplicates == 1
    print(json.dumps({'code': 'OFFLINE_EXPLICIT_NOTICE_RECOVERY_PROVEN',
        'anonymized_retained_evidence': True, 'preview_journal_unchanged': True,
        'confirmed_exact_remote_id': True, 'first_notice_duplicates': duplicates,
        'remaining_notices': len(pending), 'ghostfolio_gets': len(calls),
        'broker_requests': len(broker_requests), 'financial_writes': 0}))


def test_recovery_transport_is_one_get_with_preobtained_bearer(monkeypatch):
    monkeypatch.setenv('GHOST_SESSION_BEARER', 'synthetic.header.signature')
    events = []

    def connect(host, port, timeout, context):
        assert (host, port, timeout) == ('ghost.invalid', 443, 10)
        assert context.check_hostname is True

        def request(method, path, body=None, headers=None):
            events.append((method, path, body, headers))

        response = SimpleNamespace(status=200,
            getheader=lambda key, default='': {'Content-Type': 'application/json'}.get(key, default),
            read=lambda limit: b'{}')
        return SimpleNamespace(request=request, getresponse=lambda: response,
            close=lambda: events.append('close'))

    monkeypatch.setattr(b.http.client, 'HTTPSConnection', connect)
    request = b.make_notice_recovery_request('https://ghost.invalid', 1000, 10)
    assert request('GET', '/api/v1/activities', None) == (200, b'{}')
    assert events[0][:3] == ('GET', '/api/v1/activities', None)
    assert events[0][3] == {'Authorization': 'Bearer synthetic.header.signature',
        'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    assert events[1] == 'close'
    with pytest.raises(RuntimeError, match='^NOTICE_RECOVERY_REFUSED$'):
        request('POST', '/api/v1/import', b'{}')
    assert len(events) == 2


@pytest.mark.parametrize('fault', ['missing_artifact', 'incomplete', 'changed_persisted',
    'changed_id', 'multiple_match', 'absent_match', 'already_confirmed'])
def test_explicit_recovery_refuses_uncertain_proof_without_changing_journal(tmp_path, fault):
    config, path, proposal, _, fresh_rows = retained_recovery_case(tmp_path)
    recovery = RETAINED_DERIVED_COUNT['recovery']
    if fault == 'missing_artifact':
        (tmp_path / 'runs' / recovery['run_id'] / 'import-response-0.json').unlink()
    elif fault == 'changed_persisted':
        fresh_rows[0]['fee'] = Decimal('1')
    elif fault == 'changed_id':
        fresh_rows[-1]['id'] = 'anonymized-changed-id'
    elif fault == 'multiple_match':
        duplicate = copy.deepcopy(fresh_rows[-1])
        duplicate['id'] = 'anonymized-duplicate-id'
        fresh_rows.append(duplicate)
    elif fault == 'absent_match':
        fresh_rows.pop()
    elif fault == 'already_confirmed':
        journal = b.parse_keyed_yaml(path.read_bytes())
        journal['confirmed'][proposal['comment'][:-1] + 'b'] = recovery['remote_id']
        b.atomic_private_yaml(path, journal)
    before = path.read_bytes()
    calls = []

    def request(method, url, body):
        calls.append((method, url, body))
        count = len(fresh_rows) + (1 if fault == 'incomplete' else 0)
        return 200, encode(fresh_rows, count=count)

    with pytest.raises(RuntimeError, match='^NOTICE_RECOVERY_REFUSED$'):
        b.recover_notice_write(tmp_path, config, ACCOUNT, recovery['run_id'],
            recovery['ordinal'], request, confirm=True)
    assert path.read_bytes() == before
    assert calls == ([] if fault in ('missing_artifact', 'already_confirmed') else
        [('GET', '/api/v1/activities', None)])


@pytest.mark.parametrize('selection', ['run', 'ordinal'])
def test_explicit_recovery_requires_exact_operator_selection_before_get(tmp_path, selection):
    config, path, _, _, fresh_rows = retained_recovery_case(tmp_path)
    recovery = RETAINED_DERIVED_COUNT['recovery']
    run_id = ('89de1225-ae2c-4791-b671-f2c10c4df17a'
        if selection == 'run' else recovery['run_id'])
    ordinal = 1 if selection == 'ordinal' else recovery['ordinal']
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='^NOTICE_RECOVERY_REFUSED$'):
        b.recover_notice_write(tmp_path, config, ACCOUNT, run_id, ordinal,
            lambda *args: pytest.fail('wrong selection sent a GET'), confirm=True)
    assert path.read_bytes() == before


def test_retained_derived_profile_count_does_not_mutate_existing_activity(tmp_path, capsys):
    _, path, journal, run = setup(tmp_path)
    proposal, existing = retained_derived_count_case(proposals()[0])
    original = copy.deepcopy(existing)
    remote = b.parse_remote_activity_snapshot(encode(existing), retain_stored_date=True)
    observation = RETAINED_DERIVED_COUNT['observation']
    def request(method, url, body):
        created = row(proposal)
        created['assetProfile']['activitiesCount'] = observation['activities_count_after']
        if method == 'POST':
            return 201, encode([created])
        readback = copy.deepcopy(existing)
        for activity in readback:
            activity['assetProfile']['activitiesCount'] = observation['activities_count_after']
        return 200, encode(readback + [created])
    result = b.import_notice_proposals([proposal], remote, path, journal, run, request, {})
    assert result == {'financial_writes': 1, 'imported': 1, 'rejected': 0}
    assert existing == original
    saved = b.notice_write_journal(tmp_path, {'origin': 'https://ghost.invalid'}, ACCOUNT)[1]
    assert saved['pending'] is None and saved['confirmed'] == {proposal['comment']: 'synthetic-created'}
    print(json.dumps({'code': 'OFFLINE_DERIVED_ACTIVITY_COUNT_ACCEPTED',
        'anonymized_retained_evidence': True,
        'changed_existing_activities': observation['changed_existing_activities'],
        'activities_count_transition': [observation['activities_count_before'],
            observation['activities_count_after']], 'created_type': proposal['type'],
        'created_quantity': proposal['quantity'], 'created_unit_price': proposal['unitPrice'],
        'created_fee': proposal['fee'], 'existing_inputs_unchanged': existing == original,
        'broker_attempts': 0, 'financial_writes': 0}))


@pytest.mark.parametrize('change', ['missing', 'account', 'date', 'type', 'quantity',
    'unit_price', 'fee', 'currency', 'comment', 'profile_identity', 'integer_to_boolean',
    'integer_to_float'])
def test_retained_persisted_activity_change_keeps_write_uncertain(tmp_path, change):
    config, path, journal, run = setup(tmp_path)
    proposal, existing = retained_derived_count_case(proposals()[0])
    existing[0]['retainedMetadataValue'] = 1
    remote = b.parse_remote_activity_snapshot(encode(existing), retain_stored_date=True)
    observation = RETAINED_DERIVED_COUNT['observation']
    def request(method, url, body):
        created = row(proposal)
        created['assetProfile']['activitiesCount'] = observation['activities_count_after']
        if method == 'POST':
            return 201, encode([created])
        changed = copy.deepcopy(existing)
        for activity in changed:
            activity['assetProfile']['activitiesCount'] = observation['activities_count_after']
        if change == 'missing':
            changed.pop(0)
        elif change == 'account':
            changed[0]['accountId'] = 'other-account'
            changed[0]['account']['id'] = 'other-account'
        elif change == 'date':
            changed[0]['date'] = '2018-02-01T00:00:00.000Z'
        elif change == 'type':
            changed[0]['type'] = 'BUY'
        elif change == 'quantity':
            changed[0]['quantity'] = Decimal('2')
        elif change == 'unit_price':
            changed[0]['unitPrice'] = Decimal('30.24')
        elif change == 'fee':
            changed[0]['fee'] = Decimal('1')
        elif change == 'currency':
            changed[0]['currency'] = 'USD'
        elif change == 'comment':
            changed[0]['comment'] = 'changed-comment'
        elif change == 'profile_identity':
            changed[0]['assetProfile']['symbol'] = 'OTHER.PA'
        elif change == 'integer_to_boolean':
            changed[0]['retainedMetadataValue'] = True
        elif change == 'integer_to_float':
            changed[0]['retainedMetadataValue'] = 1.0
        return 200, encode(changed + [created])
    progress = {}
    with pytest.raises(RuntimeError, match='NOTICE_IMPORT_UNCONFIRMED'):
        b.import_notice_proposals([proposal], remote, path, journal, run, request, progress)
    assert progress == {'financial_writes': 1, 'imported': 0}
    saved = b.parse_keyed_yaml(path.read_bytes())
    assert saved['pending'] is not None and saved['confirmed'] == {}
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match='NOTICE_WRITE_UNRESOLVED'):
        b.notice_write_journal(tmp_path, config, ACCOUNT)
    assert path.read_bytes() == original

"""Offline import/readback regressions from anonymized real notice fields."""
import copy
import json
from decimal import Decimal

import pytest

import boursedirect_to_ghostfolio as b
from test_notice_reconciliation import ACCOUNT, proposals


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
    assert json.loads(capsys.readouterr().out)['exact_readback'] is True


@pytest.mark.parametrize('fault', ['timeout', 'redirect', 'server', 'empty', 'wrong_account',
    'wrong_date', 'wrong_symbol', 'wrong_amount', 'draft', 'changed_id', 'incomplete', 'lost_readback'])
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
            date='2018-01-01T00:00:00.000Z', comment=None)
        return 200, encode([row(buy), prior_sale])
    progress = {}
    with pytest.raises(RuntimeError, match='NOTICE_INSUFFICIENT_HOLDINGS'):
        b.import_notice_proposals([buy, sell], [], path, journal, run, request, progress)
    logs = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert calls == ['POST', 'GET']
    assert progress == {'financial_writes': 1, 'imported': 1}
    assert logs[-1]['code'] == 'NOTICE_INSUFFICIENT_HOLDINGS'
    assert (logs[-1]['available'], logs[-1]['sale'], logs[-1]['financial_writes'], logs[-1]['imported']) == ('2', '12', 1, 1)

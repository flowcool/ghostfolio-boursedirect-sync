import copy
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import socket

import pytest
import yaml

import boursedirect_to_ghostfolio as bd
from test_coupon_cash import inputs, statement_html
from test_contract_notes import coupon_source
from test_identity import ACCOUNT


@pytest.fixture(autouse=True)
def no_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Coupon reconciliation must remain offline')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    for name in ('reconcile_existing_activities', 'verify_chronological_holdings', 'persist_write_transition'):
        monkeypatch.setattr(bd, name, forbidden)


def source():
    statement, docs = inputs()
    reviews = {'september': bd.review_coupon_cash(statement, docs)}
    account = {'account_key': ACCOUNT, 'source_account_ref': statement['account_ref'], 'target_account_id': 'synthetic-target'}
    mappings = {docs[0]['notes'][0]['isin']: {'symbol': 'SYNTH.PA', 'data_source': 'YAHOO', 'target_currency': 'EUR',
                'target_security_evidence': 'synthetic exact-ISIN provider evidence and existing target profile'}}
    return reviews, account, mappings


def row(identifier='remote-one'):
    return {'id': identifier, 'accountId': 'synthetic-target', 'account': {'id': 'synthetic-target', 'tags': []},
            'type': 'DIVIDEND', 'date': '2026-09-17T00:00:00.000Z', 'currency': 'EUR',
            'quantity': 1, 'unitPrice': 1.9, 'fee': 0, 'comment': None, 'tags': [],
            'assetProfile': {'symbol': 'SYNTH.PA', 'dataSource': 'YAHOO', 'currency': 'EUR'}}


def compare(rows, values=None):
    return bd.compare_coupon_snapshot(*(values or source()), json.dumps({'count': len(rows), 'activities': rows}).encode())


def first(report):
    return next(iter(report['observations'].values()))


def test_unique_exact_net_representation_is_observed_automatically_without_mutation_or_wire():
    values = source()
    before = copy.deepcopy(values)
    r = row()
    r['comment'] = 'PRIVATE arbitrary comment'
    report = compare([r], values)
    assert values == before
    assert first(report)['status'] == 'CERTAIN_UNIQUE_NET_REPRESENTATION_OBSERVED'
    assert first(report)['certain_remote_id'] == r['id']
    assert report['remote_evidence'][r['id']]['quantity_price_product'] == '1.9'
    assert r['comment'] not in yaml.safe_dump(report)
    assert report['import_ready'] is False
    assert not {'wire', 'adopted', 'new', 'body', 'coverage_verified'} & set(report)


@pytest.mark.parametrize('field,value', [
    ('date', '2026-09-17T12:00:00Z'), ('date', '2026-09-14T22:00:00Z'),
    ('unitPrice', 2.4), ('fee', 0.01), ('quantity', 3),
    ('currency', 'USD'), ('isDraft', True), ('comment', 'BD#foreign-owner')])
def test_changed_legacy_context_cannot_be_certain_or_rewritten(field, value):
    r = row()
    r[field] = value
    original = copy.deepcopy(r)
    report = compare([r])
    assert first(report)['status'] != 'CERTAIN_UNIQUE_NET_REPRESENTATION_OBSERVED'
    assert 'certain_remote_id' not in first(report) and r == original
    assert r['id'] in first(report)['candidates']


def test_same_cash_with_different_quantity_price_representation_stays_uncertain():
    r = row()
    r.update(quantity=2, unitPrice=0.95)
    report = compare([r])
    candidate = first(report)['candidates'][r['id']]
    assert candidate['same_quantity_price_product'] is True and candidate['product_minus_source_cash'] == '0'
    assert candidate['exact_net_representation'] is False
    assert first(report)['status'] == 'LEGACY_CANDIDATES_REQUIRE_REVIEW'


def test_remote_and_source_multiplicity_quarantine_all_affected_matches_without_greedy_assignment():
    report = compare([row('one'), row('two')])
    assert first(report)['status'] == 'DIVIDEND_MATCH_UNCERTAIN'
    values = source()
    review = values[0]['september']
    review['coupons']['2'] = copy.deepcopy(next(iter(review['coupons'].values())))
    report = compare([row()], values)
    assert all(o['status'] == 'DIVIDEND_MATCH_UNCERTAIN' for o in report['observations'].values())
    review['coupons'] = dict(reversed(list(review['coupons'].items())))
    reverse = compare([row()], values)
    assert reverse == report


def test_missing_mapping_and_absent_candidate_are_not_new_import_classifications():
    values = source()
    values[2].clear()
    report = compare([row()], values)
    assert first(report)['status'] == 'SECURITY_MAPPING_MISSING' and first(report)['candidates'] == {}
    report = compare([])
    assert first(report)['status'] == 'NO_CANDIDATE_IN_SAVED_SNAPSHOT'
    assert report['import_ready'] is False and 'ACQUISITION_HISTORY_UNVERIFIED' in report['blockers']


def test_other_account_or_symbol_never_supplies_identity_evidence():
    foreign = row()
    foreign['accountId'] = foreign['account']['id'] = 'another-target'
    assert not first(compare([foreign]))['candidates']
    foreign = row()
    foreign['assetProfile']['symbol'] = 'OTHER.PA'
    assert not first(compare([foreign]))['candidates']


def test_cross_currency_and_provider_context_are_retained_without_financial_adoption():
    r = row()
    r['assetProfile']['currency'] = 'USD'
    report = compare([r])
    assert r['id'] in first(report)['candidates'] and not first(report)['candidates'][r['id']]['eligible']
    r['assetProfile'].update(currency='EUR', dataSource='MANUAL')
    report = compare([r])
    assert not first(report)['candidates'][r['id']]['exact_net_representation']


def test_nullable_currency_and_equivalent_utc_midnight_offset_follow_existing_snapshot_contract():
    r = row()
    r.update(currency=None, date='2026-09-17T02:00:00+02:00')
    assert first(compare([r]))['status'] == 'CERTAIN_UNIQUE_NET_REPRESENTATION_OBSERVED'


def test_actual_legacy_calendar_and_amount_differences_are_exact_observations():
    r = row()
    r.update(date='2026-09-13T22:00:00Z', quantity=3, unitPrice=0.8)
    report = compare([r])
    candidate = first(report)['candidates'][r['id']]
    assert candidate['utc_day_minus_source_day'] == -4
    assert candidate['product_minus_source_cash'] == '0.5'
    assert report['remote_evidence'][r['id']]['original_timestamp'] == r['date']


def test_incomplete_redacted_duplicate_or_invalid_current_profile_refuses():
    values = source()
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVITY_COUNT_MISMATCH'):
        bd.compare_coupon_snapshot(*values, b'{"count":1,"activities":[]}')
    r = row()
    r['fee'] = None
    with pytest.raises(RuntimeError, match='REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED'): compare([r])
    with pytest.raises(RuntimeError, match='REMOTE_ACTIVITY_ID_DUPLICATE'): compare([row(), row()])
    r = row()
    r['SymbolProfile'] = r['assetProfile']
    r['assetProfile'] = None
    with pytest.raises(RuntimeError, match='REMOTE_ASSET_PROFILE_INVALID'): compare([r])


def test_product_comparison_uses_exact_decimal_even_with_small_ambient_context():
    r = row()
    r.update(quantity=1234567890, unitPrice=1234567890)
    with localcontext() as context:
        context.prec = 6
        report = compare([r])
    assert report['remote_evidence'][r['id']]['quantity_price_product'] == '1524157875019052100'


def test_cli_replays_original_sources_preserves_colliding_inputs_and_reports_safe_counts(tmp_path, capsys):
    reviews, account, mappings = source()
    Path('inputs').mkdir()
    note = bd.parse_contract_note(coupon_source(), 32, include_coupons=True)['notes'][0]
    html = statement_html().replace('SYNTHETIC_ACCOUNT', account['source_account_ref']).replace('SYNTHETIC GAMMA', note['name'])
    Path('inputs/statement.html').write_text(html)
    Path('inputs/note.html').write_text(coupon_source())
    Path('inputs/snapshot.json').write_text(json.dumps({'count': 1, 'activities': [row()]}))
    config = {'schema_version': 1, 'account': account, 'mappings': mappings,
              'documents': {'september': {'statement': 'statement.html', 'notes': ['note.html']}}, 'snapshot': 'snapshot.json'}
    Path('inputs/config.yaml').write_text(yaml.safe_dump(config))
    args = ['reconcile-coupons', '--config', 'inputs/config.yaml', '--input-root', 'inputs',
            '--output', 'outputs/reconciliation.yaml', '--max-bytes', '100000', '--max-depth', '32']
    assert bd.main(args) == 2
    output = capsys.readouterr().out
    assert json.loads(output)['status_counts'] == {'CERTAIN_UNIQUE_NET_REPRESENTATION_OBSERVED': 1}
    for private in ('synthetic-target', account['source_account_ref'], note['isin'], '1.9'): assert private not in output
    previous = Path('outputs/reconciliation.yaml').read_bytes()
    assert bd.main(args) == 2 and Path('outputs/reconciliation.yaml').read_bytes() == previous
    assert Path('outputs/reconciliation.yaml').stat().st_mode & 0o777 == 0o600
    os.link('inputs/config.yaml', 'outputs/collision.yaml')
    original = Path('inputs/config.yaml').read_bytes()
    args[args.index('outputs/reconciliation.yaml')] = 'outputs/collision.yaml'
    assert bd.main(args) == 1
    assert Path('inputs/config.yaml').read_bytes() == original and Path('outputs/reconciliation.yaml').read_bytes() == previous
    assert not list(Path('state').glob('*'))


def test_no_duplicate_period_versions_or_unapproved_review_policy():
    values = source()
    values[0]['another'] = copy.deepcopy(values[0]['september'])
    with pytest.raises(RuntimeError, match='MULTIPLE_STATEMENT_VERSIONS'): compare([], values)
    values = source()
    values[0]['september']['policy']['historic_rewrite'] = True
    with pytest.raises(RuntimeError, match='INVALID_COUPON_RECONCILIATION_SOURCE'): compare([], values)


def test_two_distinct_isins_cannot_silently_bind_to_one_target_security():
    values = source()
    review = values[0]['september']
    review['coupons']['2'] = copy.deepcopy(next(iter(review['coupons'].values())))
    review['coupons']['2']['isin'] = 'BE0003808251'
    values[2]['BE0003808251'] = copy.deepcopy(next(iter(values[2].values())))
    with pytest.raises(RuntimeError, match='SECURITY_MAPPING_AMBIGUOUS'): compare([], values)


def test_unknown_source_period_cannot_lose_its_blocker_at_snapshot_comparison():
    values = source()
    values[0]['september']['blockers'].append('UNSUPPORTED_OPERATION_PERIOD')
    assert 'UNSUPPORTED_OPERATION_PERIOD' in compare([row()], values)['blockers']

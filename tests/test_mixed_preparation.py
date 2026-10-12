import copy
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

import boursedirect_to_ghostfolio as bd
from test_contract_notes import paired_statement, note_source, coupon_source
from test_conversion import inputs, no_network
from test_identity import ACCOUNT
from test_holdings import acquired, check
from test_adoption import row, snapshot


def sources():
    _, _, account, mappings = inputs()
    account['account_key'] = ACCOUNT
    soup = BeautifulSoup(paired_statement(), 'html.parser')
    columns = [bd.direct_rows(c.find('table', recursive=False)) for c in bd.cells(bd.direct_rows(soup.find('table', id='synthetic-ledger'))[1])]
    for column, value in [(0, '17/09/2026'), (1, 'COUPONS SYNTHETIC GAMMA'), (3, '1,90')]:
        bd.cells(columns[column][6])[0].string = value
    bd.cells(columns[3][7])[0].string = '260,35'
    bd.cells(columns[3][10])[0].string = '229,90'
    config = {'schema_version': 1, 'account': account, 'mappings': mappings,
              'documents': {'september': {'statement': 'statement.html', 'notes': ['buy.html', 'sell.html', 'coupon.html']}}}
    documents = {'september': {'statement': str(soup).encode(),
                              'notes': [note_source().encode(), note_source(True).encode(), coupon_source().encode()]}}
    return bd.yaml.safe_dump(config).encode(), documents


def plan():
    config, documents = sources()
    return bd.compute_prepared_sources(config, documents, 1000000, 32)['artifact']


def internal_plan():
    activities = copy.deepcopy(plan()['activities'])
    for a in activities.values():
        for k in ('quantity', 'unit_price', 'fee'):
            a[k] = Decimal(a[k])
        a['operation_date'] = date.fromisoformat(a['operation_date'])
    return activities


def test_mixed_raw_source_replay_and_wire_use_exact_net_cash_and_booking_day():
    config, documents = sources()
    result = bd.compute_prepared_sources(config, documents, 1000000, 32)
    artifact = result['artifact']
    assert len(artifact['activities']) == len(result['snapshots'][0]['events']) == 4
    dividend = next(a for a in artifact['activities'].values() if a['kind'] == 'DIVIDEND')
    assert (dividend['quantity'], dividend['unit_price'], dividend['fee']) == ('1', '1.9', '0')
    assert dividend['source_fields']['quantity'] == '-3' and dividend['source_fields']['gross'] == '2.4'
    assert dividend['operation_date'] == '2026-09-17' and dividend['amount_basis'] == 'net_received'
    assert bd.validate_prepared_sources(bd.yaml.safe_dump(artifact).encode(), config, documents, 1000000, 32) == artifact
    wire = bd.build_wire_payload(artifact['activities'])
    rows = list(bd.reviewed_wire_rows(wire).values())
    assert len(rows) == 4
    dto = next(r for r in rows if r['type'] == 'DIVIDEND')
    assert dto['quantity'] == 1 and dto['unitPrice'] == Decimal('1.9') and dto['fee'] == 0
    assert dto['date'] == '2026-09-17T00:00:00.000Z'
    assert not ({'source_fields', 'isin', 'amount_basis'} & set(dto))


@pytest.mark.parametrize('change,code', [('missing_coupon', 'COUPON_EVIDENCE_MISSING'),
                                        ('duplicate_coupon', 'COUPON_NOTE_MATCHING_NOT_COMPLETE'),
                                        ('trade_mismatch', 'NOTE_MATCHING_NOT_COMPLETE'),
                                        ('unknown', 'UNSUPPORTED_OPERATION_PERIOD')])
def test_mixed_period_refuses_incomplete_or_unsupported_sources(change, code):
    config, documents = sources()
    d = documents['september']
    if change == 'missing_coupon':
        d['notes'][2] = d['notes'][0]
    elif change == 'duplicate_coupon':
        d['notes'][0] = d['notes'][2]
    elif change == 'trade_mismatch':
        d['statement'] = d['statement'].replace(b'Cours : 10', b'Cours : 11')
    else:
        d['notes'][2] = d['notes'][2].replace(b'COUPONS', b'UNKNOWN')
    with pytest.raises(RuntimeError, match='^' + code + '$'):
        bd.compute_prepared_sources(config, documents, 1000000, 32)


@pytest.mark.parametrize('field,value', [('quantity', '3'), ('fee', '0.1')])
def test_dividend_wire_refuses_alternative_cash_representations(field, value):
    p = plan()['activities']
    next(a for a in p.values() if a['kind'] == 'DIVIDEND')[field] = value
    with pytest.raises(RuntimeError, match='^WIRE_DIVIDEND_NET_REPRESENTATION_REQUIRED$'):
        bd.build_wire_payload(p)


def test_dividend_does_not_change_holdings_and_owned_repeat_is_not_new():
    p = internal_plan()
    rows = acquired(p)
    result = check(p, rows)
    dividend = next(a for a in p.values() if a['kind'] == 'DIVIDEND')
    assert result['coverage_verified']
    assert result['ending_quantities'][dividend['symbol']] == '3'
    rows.extend(row(a, 'owned-' + str(i), owned=True) for i, a in enumerate(p.values()))
    adoption = bd.reconcile_existing_activities(p, snapshot(rows), {}, automatic=True)
    assert len(adoption['owned']) == 4 and not adoption['new']


def test_legacy_dividend_amount_or_date_difference_never_becomes_new_or_adopted():
    p = internal_plan()
    d = next(a for a in p.values() if a['kind'] == 'DIVIDEND')
    existing = row(d)
    existing.update(date='2026-09-13T22:00:00.000Z', quantity=3, unitPrice=0.8)
    with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
        bd.reconcile_existing_activities(p, snapshot([existing]), {}, automatic=True)


def test_source_replay_rejects_tampered_dividend_amount():
    config, documents = sources()
    artifact = plan()
    next(a for a in artifact['activities'].values() if a['kind'] == 'DIVIDEND')['unit_price'] = '2.4'
    with pytest.raises(RuntimeError, match='^PREPARED_SOURCE_CONTENT_CONFLICT$'):
        bd.validate_prepared_sources(bd.yaml.safe_dump(artifact).encode(), config, documents, 1000000, 32)


def test_extra_coupon_note_without_statement_coupon_refuses_whole_preparation():
    config, documents = sources()
    documents['september']['statement'] = paired_statement().encode()
    with pytest.raises(RuntimeError, match='^COUPON_EVIDENCE_MISSING$'):
        bd.compute_prepared_sources(config, documents, 1000000, 32)


def test_complete_mixed_daily_period_still_requires_destination_and_application_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    raw, documents = sources()
    config = bd.parse_keyed_yaml(raw)
    Path('inputs').mkdir()
    entry = config['documents']['september']
    Path('inputs', entry['statement']).write_bytes(documents['september']['statement'])
    for filename, body in zip(entry['notes'], documents['september']['notes']):
        Path('inputs', filename).write_bytes(body)
    config['snapshot'] = 'snapshot.json'
    Path('inputs/snapshot.json').write_text('{"count":0,"activities":[]}')
    Path('inputs/config.yaml').write_text(bd.yaml.safe_dump(config))
    summary = bd.preview_local_daily('inputs/config.yaml','inputs','2026-10-12',1000000,32)
    saved = bd.parse_keyed_yaml(next(Path('outputs').glob('daily-*.yaml')).read_bytes())
    journal = bd.parse_keyed_yaml(next(Path('state').glob('daily-*.yaml')).read_bytes())
    assert journal['periods']['2026-09']['complete_source_matching'] is True
    assert '2026-09:source' not in saved['exceptions']
    assert len(saved['trade_observations']['2026-09']['new']) == 4
    assert len(saved['coupon_observations']['observations']) == 1
    assert saved['exceptions']['2026-09:destination']['status'] == 'unresolved'
    assert summary['import_ready'] is False


@pytest.mark.parametrize('change', ['missing_profile', 'different_provider', 'different_currency'])
def test_legacy_dividend_uncertain_profile_cannot_disappear_from_duplicate_guard(change):
    p = internal_plan()
    dividend = next(a for a in p.values() if a['kind'] == 'DIVIDEND')
    existing = row(dividend)
    existing['date'] = '2026-09-13T00:00:00.000Z'
    if change == 'missing_profile':
        existing['assetProfile'] = None
    elif change == 'different_provider':
        existing['assetProfile']['dataSource'] = 'MANUAL'
    else:
        existing['currency'] = 'USD'
    with pytest.raises(RuntimeError, match='^REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED$'):
        bd.reconcile_existing_activities(p, snapshot([existing]), {}, automatic=True)


def test_trade_symbol_collision_cannot_be_hidden_by_last_isin_before_dividend_conversion():
    raw, documents = sources()
    config = bd.parse_keyed_yaml(raw)
    for mapping in config['mappings'].values():
        mapping['symbol'] = 'COLLISION.PA'
    with pytest.raises(RuntimeError, match='^SECURITY_MAPPING_AMBIGUOUS$'):
        bd.compute_prepared_sources(bd.yaml.safe_dump(config).encode(), documents, 1000000, 32)


def test_same_isin_trade_and_dividend_can_share_the_verified_symbol():
    artifact = plan()
    dividend = next(a for a in artifact['activities'].values() if a['kind'] == 'DIVIDEND')
    buy = next(a for a in artifact['activities'].values() if a['kind'] == 'BUY')
    assert dividend['isin'] == buy['isin'] and dividend['symbol'] == buy['symbol']

import copy
import json
from datetime import timedelta
from decimal import Decimal

from bs4 import BeautifulSoup
import pytest

import boursedirect_to_ghostfolio as bd
from test_contract_notes import coupon_source, field, vectors, paired_statement, note_source
from test_conversion import inputs, no_network
from test_identity import update_controls, ACCOUNT


def source():
    statement, documents, account, mappings = inputs()
    account['account_key'] = ACCOUNT
    soup = BeautifulSoup(coupon_source(), 'html.parser')
    field(soup, 1, 0).string = 'DROITS DE GARDE'
    field(soup, 1, 1).string = ''
    field(soup, 1, 2).string = 'CONSERV ETG 2026T3'
    for vector in vectors(soup):
        for row in vector[3:]:
            row.decompose()
    bd.cells(vectors(soup)[2][1])[0].string = '0,97'
    bd.cells(vectors(soup)[3][1])[0].string = ''
    skipped = bd.parse_contract_note(str(soup), 32, include_coupons=True, skip_missing_isin=True)
    statement['events'].append({'slot': 20, 'date': skipped['notes'][0]['date'],
                               'kind': 'UNKNOWN', 'label': 'DROITS DE GARDE CONSERV ETG 2026T3',
                               'debit': Decimal('0.97'), 'credit': Decimal(0)})
    update_controls(statement)
    return statement, documents + [skipped], account, mappings, str(soup)


def test_skip_keeps_cash_controls_and_trade_wire_excludes_the_debit():
    statement, documents, account, mappings, _ = source()
    before = copy.deepcopy((statement, documents))
    records = bd.convert_matched_trades(statement, documents, account, mappings)
    assert len(records) == 3 and all(r['kind'] in ('BUY', 'SELL') for r in records)
    matched = bd.match_missing_isin_skips(statement, documents)
    assert matched['events'][-1]['skip_reason'] == 'SOURCE_ISIN_ABSENT'
    bd.validate_ledger(matched['controls'], matched['events'])
    identity = bd.ledger_identity(matched, account['account_key'])
    assert len(identity['events']) == 4
    identities = {event['source_slot']: event['id'] for event in identity['events']}
    activities = {}
    for record in records:
        marker = identities[record['source_slot']]
        activities[marker] = {**{k: bd.canonical_decimal(v) if isinstance(v, Decimal)
                                else v.isoformat() if hasattr(v, 'isoformat') else v
                                for k, v in record.items()}, 'id': marker}
    wire = bd.build_wire_payload(activities)
    assert len(bd.reviewed_wire_rows(wire)) == 3
    assert before == (statement, documents)


@pytest.mark.parametrize('change', ['amount', 'date', 'label', 'duplicate', 'account'])
def test_skip_needs_unambiguous_account_bound_cash_matching(change):
    statement, documents, account, mappings, _ = source()
    note = documents[-1]['notes'][0]
    if change == 'amount':
        note['debit'] = Decimal('0.98')
    elif change == 'date':
        note['date'] += timedelta(days=1)
    elif change == 'label':
        note['name'] = 'DIFFERENT'
    elif change == 'duplicate':
        documents.append(copy.deepcopy(documents[-1]))
    else:
        documents[-1]['account_ref'] = 'OTHER'
    with pytest.raises(RuntimeError, match='^(SKIPPED_NOTE_MATCHING_NOT_COMPLETE|NOTE_ACCOUNT_MISMATCH)$'):
        bd.convert_matched_trades(statement, documents, account, mappings)


def test_skipping_does_not_bypass_monthly_balance_controls():
    statement, documents, account, mappings, _ = source()
    statement['controls'][-1]['credit'] += Decimal('0.01')
    with pytest.raises(RuntimeError, match='^BALANCE_MISMATCH$'):
        bd.convert_matched_trades(statement, documents, account, mappings)


def test_missing_isin_policy_does_not_hide_present_invalid_isin_or_unknown_security_operation():
    statement, documents, account, mappings, html = source()
    soup = BeautifulSoup(html, 'html.parser')
    field(soup, 1, 1).string = 'FR0000000000'
    with pytest.raises(RuntimeError, match='^INVALID_NOTE_SECURITY$'):
        bd.parse_contract_note(str(soup), 32, include_coupons=True, skip_missing_isin=True)
    field(soup, 1, 1).string = 'FR0000000010'
    unknown = bd.parse_contract_note(str(soup), 32, include_coupons=True, skip_missing_isin=True)
    assert unknown['notes'][0]['kind'] == 'UNKNOWN'
    with pytest.raises(RuntimeError, match='^UNSUPPORTED_OPERATION_PERIOD$'):
        bd.convert_matched_trades(statement, documents[:-1] + [unknown], account, mappings)


def test_saved_source_preparation_replays_skips_without_fee_wire_or_identity_loss():
    _, _, account, mappings, skipped_html = source()
    soup = BeautifulSoup(paired_statement(), 'html.parser')
    ledger = soup.find('table', id='synthetic-ledger')
    columns = [bd.direct_rows(c.find('table', recursive=False)) for c in bd.cells(bd.direct_rows(ledger)[1])]
    for column, value in [(0, '17/09/2026'), (1, 'DROITS DE GARDE CONSERV ETG 2026T3'), (2, '0,97')]:
        bd.cells(columns[column][6])[0].string = value
    bd.cells(columns[2][7])[0].string = '31,42'
    bd.cells(columns[3][10])[0].string = '227,03'
    config = {'schema_version': 1, 'account': account, 'mappings': mappings,
              'documents': {'september': {'statement': 'statement.html', 'notes': ['buy.html', 'sell.html', 'skip.html']}}}
    raw_config = bd.yaml.safe_dump(config).encode()
    captures = {'september': {'statement': str(soup).encode(),
                             'notes': [note_source().encode(), note_source(True).encode(), skipped_html.encode()]}}
    result = bd.compute_prepared_sources(raw_config, captures, 100000, 32)
    assert len(result['snapshots'][0]['events']) == 4
    assert len(result['artifact']['activities']) == 3
    prepared = bd.yaml.safe_dump(result['artifact']).encode()
    assert bd.validate_prepared_sources(prepared, raw_config, captures, 100000, 32) == result['artifact']
    rows = json.loads(bd.build_wire_payload(result['artifact']['activities'])['body'])['activities']
    assert len(rows) == 3 and all(row['type'] in ('BUY', 'SELL') for row in rows)

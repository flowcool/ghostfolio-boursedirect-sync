import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

import boursedirect_to_ghostfolio as bd
from test_contract_notes import note_source, paired_statement
from test_conversion import inputs, no_network
from test_daily_preview import isolated, setup, run, paths


def foreign_sources():
    return (paired_statement().replace('VTE CPT ', 'VENTE ETRANGER '),
            note_source(True).replace('VENTE COMPTANT', 'VENTE ETRANGER'))


def test_foreign_sale_keeps_domestic_arithmetic_and_explicit_currency_boundary():
    statement, notes, account, mappings = inputs()
    expected = bd.convert_matched_trades(statement, notes, account, mappings)
    statement_html, note_html = foreign_sources()
    statement = bd.parse_statement(statement_html, 32)
    notes[1] = bd.parse_contract_note(note_html, 32)
    records = bd.convert_matched_trades(statement, notes, account, mappings)
    assert len(records) == 3
    assert [{k: v for k, v in row.items() if k != 'source_label'} for row in records] == [
        {k: v for k, v in row.items() if k != 'source_label'} for row in expected]
    assert all(row['source_label'].startswith('VENTE ETRANGER ') for row in records[:2])
    assert all(row['price_currency'] is None for row in notes[1]['notes'])
    for mapping in mappings.values():
        mapping.pop('execution_price_currency')
    with pytest.raises(RuntimeError, match='^SECURITY_CURRENCY_CONFLICT$'):
        bd.convert_matched_trades(statement, notes, account, mappings)


def test_foreign_sale_note_still_refuses_bad_net_and_wrong_direction():
    _, html = foreign_sources()
    with pytest.raises(RuntimeError, match='^NOTE_DIRECTION_CONFLICT$'):
        bd.parse_contract_note(html.replace('QUANTITE : -2', 'QUANTITE : +2'), 32)
    with pytest.raises(RuntimeError, match='^NOTE_NET_MISMATCH$'):
        bd.parse_contract_note(html.replace('COURTAGE : +0,20', 'COURTAGE : +0,21'), 32)


def legacy_daily_state():
    config = setup()
    statement = Path('inputs/statement.html')
    statement.write_text(statement.read_text().replace('VTE CPT ', 'VENTE ETRANGER '))
    note = Path('inputs/sell.html')
    note.write_text(note.read_text().replace('VENTE COMPTANT', 'VENTE ETRANGER'))
    run()
    journal_path, report_path = paths(config)
    previous = bd.parse_keyed_yaml(journal_path.read_bytes())
    parsed = bd.parse_statement(statement.read_text(), 32)
    events = []
    for event in parsed['events']:
        values = {k: bd.canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, 'isoformat') else v
                  for k, v in event.items() if k != 'slot'}
        if event['label'].startswith('VENTE ETRANGER '):
            values['kind'] = 'UNKNOWN'
            del values['quantity'], values['unit_price']
        events.append(values)
    controls = [{k: bd.canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, 'isoformat') else v
                 for k, v in c.items() if k != 'slot'} for c in parsed['controls']]
    semantic = {'period': parsed['period'], 'events': sorted(events, key=lambda e: json.dumps(e, sort_keys=True)),
                'controls': controls}
    previous['periods']['2026-09']['financial_sha256'] = hashlib.sha256(
        json.dumps(semantic, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    bd.atomic_private_yaml(journal_path, previous)
    return config, previous, journal_path, report_path


def test_byte_identical_foreign_sale_parser_upgrade_retains_proof_and_repeats_identically():
    config, previous, journal_path, report_path = legacy_daily_state()
    run()
    saved = bd.parse_keyed_yaml(journal_path.read_bytes())
    upgrade = saved['exceptions']['2026-09:foreign_sale_parser_upgrade']
    assert upgrade['status'] == 'resolved_by_saved_evidence'
    assert upgrade['previous_financial_sha256'] == previous['periods']['2026-09']['financial_sha256']
    assert upgrade['financial_sha256'] == saved['periods']['2026-09']['financial_sha256']
    assert upgrade['statement_sha256'] == previous['periods']['2026-09']['statement_sha256']
    assert saved['periods']['2026-09']['complete_source_matching'] is True
    assert bd.parse_keyed_yaml(report_path.read_bytes())['import_ready'] is False
    before = journal_path.read_bytes(), report_path.read_bytes()
    run()
    assert before == (journal_path.read_bytes(), report_path.read_bytes())


@pytest.mark.parametrize('change', ['statement_bytes', 'note_bytes', 'unrelated_hash'])
def test_foreign_sale_upgrade_cannot_bypass_changed_sources_or_other_fingerprint_conflicts(change):
    _, previous, journal_path, report_path = legacy_daily_state()
    if change == 'unrelated_hash':
        previous['periods']['2026-09']['financial_sha256'] = '0' * 64
        bd.atomic_private_yaml(journal_path, previous)
    else:
        source = Path('inputs/statement.html' if change == 'statement_bytes' else 'inputs/sell.html')
        source.write_text(source.read_text() + '<!-- changed original bytes -->')
    before = journal_path.read_bytes(), report_path.read_bytes()
    with pytest.raises(RuntimeError, match='^DAILY_SOURCE_REVISION_REVIEW_REQUIRED$'):
        run()
    assert before == (journal_path.read_bytes(), report_path.read_bytes())


def test_foreign_sale_raw_preparation_replay_produces_the_existing_exact_sell_wire():
    config = setup()
    statement = Path('inputs/statement.html')
    statement.write_text(statement.read_text().replace('VTE CPT ', 'VENTE ETRANGER '))
    note = Path('inputs/sell.html')
    note.write_text(note.read_text().replace('VENTE COMPTANT', 'VENTE ETRANGER'))
    raw = bd.yaml.safe_dump({k: v for k, v in config.items() if k != 'snapshot'}).encode()
    documents, _ = bd.capture_preparation_sources(raw, 'inputs', 100000, 32)
    prepared = bd.compute_prepared_sources(raw, documents, 100000, 32)['artifact']
    replay = bd.validate_prepared_sources(bd.yaml.safe_dump(prepared).encode(), raw, documents, 100000, 32)
    assert replay == prepared
    rows = json.loads(bd.build_wire_payload(prepared['activities'])['body'], parse_float=Decimal)['activities']
    assert len(rows) == 3 and sum(row['type'] == 'SELL' for row in rows) == 2
    expected = {record['symbol']: record for record in bd.convert_matched_trades(*inputs())}
    for row in rows:
        source = expected[row['symbol']]
        assert row['quantity'] == source['quantity']
        assert row['unitPrice'] == source['unit_price']
        assert row['fee'] == source['fee']
        assert row['currency'] == 'EUR' and row['accountId'] == config['account']['target_account_id']

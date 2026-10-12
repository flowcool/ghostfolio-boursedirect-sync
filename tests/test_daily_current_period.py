import hashlib
import json
import os
from pathlib import Path

from bs4 import BeautifulSoup
import pytest
import yaml

import boursedirect_to_ghostfolio as bd
from test_contract_notes import note_source, coupon_source, field, paired_statement
from test_daily_preview import isolated, setup, write, run, paths


def index_html(days=(1, 2), nc=1, month=10, year=2026):
    nav = ''.join(f'<a href="javascript:{name}(\'RO\',{nc},{month},{year})" title="précédent"></a>'
                  for name in ('AnneePrecedente', 'AnneeSuivante', 'MoisPrecedent', 'MoisSuivant'))
    links = ''.join(f'<a href="javascript:ouvrePopup(\'releveOpe.php?nc={nc}&amp;type=RO&amp;year={year}&amp;month={month}&amp;day={day}&amp;trash=/avis.pdf\',\'encours\');">{day:02d}</a>' for day in days)
    empty = '' if days else '<div class="msg texte1T7A">Vous n\'avez pas effectué d\'opération ce mois-ci.</div>'
    return '<html><meta charset="UTF-8"><table><tr><td class="topdatas"><span>' + str(year) + '</span></td></tr><tr><td class="topdatas"><span>Octobre</span></td></tr></table>' + nav + links + empty + '</html>'


def metadata(config, filename, role, url):
    path = Path('inputs') / filename
    receipt = {'role': role, 'account_wrapper': 'PEA', 'broker_account_id': config['account']['source_account_ref'][:-4],
               'path': filename, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'url': url}
    result = filename + '.yaml'
    Path('inputs', result).write_text(yaml.safe_dump(receipt))
    return result


def current_setup(days=(1, 2)):
    config = setup()
    before = config['account']['source_account_ref']
    config['account']['source_account_ref'] += ' PEA'
    for p in Path('inputs').glob('*.html'):
        p.write_text(p.read_text().replace(before, config['account']['source_account_ref']))
    Path('inputs/index.html').write_bytes(index_html(days).encode('cp1252'))
    entry = {'period': '2026-10', 'index': 'index.html', 'index_encoding': 'observed_cp1252_declared_utf8',
             'index_metadata': metadata(config, 'index.html', 'frame_document', 'https://www.boursedirect.fr/priv/new/avis-operes.php?ong=5&nc=1'), 'notes': {}}
    for day in days:
        html = coupon_source() if day == 1 else note_source()
        html = html.replace(before, config['account']['source_account_ref']).replace('17/09/2026', f'{day:02d}/10/2026')
        if day == 1:
            soup = BeautifulSoup(html, 'html.parser'); field(soup, 1, 1).string = ''; html = str(soup)
        name = f'current-{day}.html'; Path('inputs', name).write_text(html)
        entry['notes'][f'2026-10-{day:02d}'] = {'document': name, 'metadata': metadata(config, name, 'contract_note', f'https://www.boursedirect.fr/priv/new/releveOpe.php?nc=1&type=RO&year=2026&month=10&day={day}&trash=/avis.pdf')}
    config['current_period'] = entry; write(config)
    return config


def saved(config):
    return bd.parse_keyed_yaml(paths(config)[1].read_bytes())


def refresh(config, day=None):
    entry = config['current_period']
    doc = entry['notes'][day] if day else {'document': entry['index'], 'metadata': entry['index_metadata']}
    path = Path('inputs', doc['metadata']); meta = yaml.safe_load(path.read_text())
    meta['sha256'] = hashlib.sha256(Path('inputs', doc['document']).read_bytes()).hexdigest()
    path.write_text(yaml.safe_dump(meta))


def test_actual_failure_and_success_notes_are_retained_without_monthly_readiness():
    config = current_setup(); before = {p: p.read_bytes() for p in Path('inputs').iterdir()}
    result = run(); report = saved(config)
    current = report['current_period_observations']
    assert current['offered_note_days'] == ['2026-10-01', '2026-10-02']
    assert current['every_offered_note_retained'] and current['through_day_verified'] is False
    assert current['monthly_cash_controls_verified'] is False and current['import_ready'] is False
    assert current['notes']['2026-10-01']['code'] == 'INVALID_NOTE_SECURITY'
    assert current['notes']['2026-10-01']['notes'] == []
    assert current['notes']['2026-10-02']['notes'][0]['kind'] == 'BUY'
    assert current['notes']['2026-10-02']['notes'][0]['price_currency'] is None
    assert current['notes']['2026-10-02']['code'] == 'CURRENT_NOTE_REQUIRES_CLOSED_STATEMENT'
    assert report['last_completed_acquisition_period'] == '2026-09' and result['import_ready'] is False
    assert sum(k.startswith('current_note:') for k in report['exceptions']) == 2
    assert before == {p: p.read_bytes() for p in Path('inputs').iterdir()}
    state, output = paths(config); previous = state.read_bytes(), output.read_bytes(); run()
    assert previous == (state.read_bytes(), output.read_bytes())
    assert state.stat().st_mode & 0o777 == output.stat().st_mode & 0o777 == 0o600


def test_declared_utf8_profile_does_not_accept_the_misdeclared_calendar():
    config = current_setup(); config['current_period']['index_encoding'] = 'declared'; write(config)
    with pytest.raises(RuntimeError, match='^INVALID_DOCUMENT_ENCODING$'): run()
    assert not paths(config)[0].exists() and not paths(config)[1].exists()


def test_normal_utf8_calendar_uses_the_strict_reader():
    config = current_setup(); Path('inputs/index.html').write_text(index_html())
    refresh(config); config['current_period']['index_encoding'] = 'declared'; write(config)
    run(); assert saved(config)['current_period_observations']['index_encoding'] == 'declared'


def test_observed_encoding_profile_refuses_valid_utf8_instead_of_mojibake():
    config = current_setup(); Path('inputs/index.html').write_text(index_html()); refresh(config)
    with pytest.raises(RuntimeError, match='^CURRENT_INDEX_ENCODING_PROFILE_CONFLICT$'): run()


@pytest.mark.parametrize('prefix', [b'\xef\xbb\xbf', b'\x00', b'\x81'])
def test_observed_encoding_profile_rejects_bom_nul_and_undefined_cp1252_bytes(prefix):
    config = current_setup(); p = Path('inputs/index.html'); p.write_bytes(prefix + p.read_bytes()); refresh(config)
    with pytest.raises(RuntimeError, match='^CURRENT_INDEX_ENCODING_PROFILE_CONFLICT$'): run()


@pytest.mark.parametrize('part', ['index', 'note'])
@pytest.mark.parametrize('key,value', [('sha256', '0' * 64), ('broker_account_id', 'OTHER'), ('account_wrapper', 'PEA-PME'), ('role', 'unrelated')])
def test_changed_hash_account_or_role_refuses_without_replacing_saved_state(part, key, value):
    config = current_setup(); run(); state, output = paths(config); before = state.read_bytes(), output.read_bytes()
    ref = config['current_period']['index_metadata'] if part == 'index' else config['current_period']['notes']['2026-10-02']['metadata']
    path = Path('inputs', ref); meta = yaml.safe_load(path.read_text()); meta[key] = value; path.write_text(yaml.safe_dump(meta))
    with pytest.raises(RuntimeError, match='^CURRENT_CAPTURE_BINDING_CONFLICT$'): run()
    assert before == (state.read_bytes(), output.read_bytes())


@pytest.mark.parametrize('url', ['https://www.boursedirect.fr@evil.invalid/priv/new/avis-operes.php?ong=5&nc=1', 'http://www.boursedirect.fr/priv/new/avis-operes.php?ong=5&nc=1', 'https://www.boursedirect.fr/priv/new/avis-operes.php?ong=5&nc=1#x'])
def test_off_origin_or_fragment_metadata_refuses(url):
    config = current_setup(); p = Path('inputs', config['current_period']['index_metadata'])
    meta = yaml.safe_load(p.read_text()); meta['url'] = url; p.write_text(yaml.safe_dump(meta))
    with pytest.raises(RuntimeError, match='^CURRENT_CAPTURE_ORIGIN_CONFLICT$'): run()


@pytest.mark.parametrize('days', [(1,), (1, 2, 3), (1, 1, 2)])
def test_missing_extra_or_duplicate_offered_note_cannot_claim_inventory_complete(days):
    config = current_setup(); Path('inputs/index.html').write_bytes(index_html(days).encode('cp1252')); refresh(config)
    with pytest.raises(RuntimeError, match='^CURRENT_INDEX_(NOTE_INVENTORY|DAY)_CONFLICT$'): run()


@pytest.mark.parametrize('month,year,nc', [(9, 2026, 1), (10, 2025, 1), (10, 2026, 2)])
def test_calendar_month_year_and_account_slot_are_bound(month, year, nc):
    config = current_setup(); Path('inputs/index.html').write_bytes(index_html(month=month, year=year, nc=nc).encode('cp1252')); refresh(config)
    with pytest.raises(RuntimeError, match='^CURRENT_INDEX_PERIOD_CONFLICT$'): run()


@pytest.mark.parametrize('day', ['2026-10-01', '2026-10-02'])
def test_even_refused_missing_isin_notes_must_have_the_expected_day_and_account(day):
    config = current_setup(); p = Path('inputs', config['current_period']['notes'][day]['document'])
    p.write_text(p.read_text().replace(day[-2:] + '/10/2026', '03/10/2026')); refresh(config, day)
    with pytest.raises(RuntimeError, match='^CURRENT_NOTE_DAY_CONFLICT$'): run()


def test_index_url_and_retained_daily_url_must_match():
    config = current_setup(); p = Path('inputs', config['current_period']['notes']['2026-10-02']['metadata'])
    meta = yaml.safe_load(p.read_text()); meta['url'] = meta['url'].replace('nc=1', 'nc=2'); p.write_text(yaml.safe_dump(meta))
    with pytest.raises(RuntimeError, match='^CURRENT_NOTE_URL_CONFLICT$'): run()


def test_no_operation_message_is_observation_not_through_day_or_history_proof():
    config = current_setup(days=()); run(); current = saved(config)['current_period_observations']
    assert current['offered_note_days'] == [] and current['notes'] == {}
    assert current['through_day_verified'] is False and saved(config)['last_completed_acquisition_period'] == '2026-09'


def test_later_invocation_does_not_expire_current_note_exceptions():
    config = current_setup(); run()
    before = {k: v for k, v in saved(config)['exceptions'].items() if k.startswith('current_note:')}
    del config['current_period']; write(config); run('2027-01-12')
    assert before == {k: v for k, v in saved(config)['exceptions'].items() if k.startswith('current_note:')}


def test_closed_source_dependency_requires_the_exact_retained_note_hash():
    config = current_setup(); run()
    before = saved(config)['exceptions']
    valid_hash = hashlib.sha256(Path('inputs/current-2.html').read_bytes()).hexdigest()
    invalid_hash = hashlib.sha256(Path('inputs/current-1.html').read_bytes()).hexdigest()
    # The complete October ledger matches the saved buy plus both saved sells.
    html = paired_statement().replace('windows-1252', 'utf-8')
    original_account = bd.parse_statement(html, 32)['account_ref']
    html = html.replace(original_account, config['account']['source_account_ref']).replace('17/09/2026', '02/10/2026')
    soup = BeautifulSoup(html, 'html.parser')
    control_cells = [n for n in soup.find_all('td') if not n.find('table') and bd.text(n).startswith('Solde au :')]
    control_cells[0].string = 'Solde au : 30/09/2026'; control_cells[-1].string = 'Solde au : 31/10/2026'
    Path('inputs/october.html').write_text(str(soup))
    sell = note_source(True).replace(original_account, config['account']['source_account_ref']).replace('17/09/2026', '02/10/2026')
    Path('inputs/october-sell.html').write_text(sell)
    config['documents']['october'] = {'statement': 'october.html', 'notes': ['current-2.html', 'october-sell.html']}
    del config['current_period']; write(config); run('2026-11-12')
    journal = bd.parse_keyed_yaml(paths(config)[0].read_bytes())
    assert journal['exceptions']['current_note:' + valid_hash]['status'] == 'resolved_by_saved_evidence'
    assert journal['exceptions']['current_note:' + invalid_hash] == before['current_note:' + invalid_hash]
    assert saved(config)['last_completed_acquisition_period'] == '2026-10'
    assert saved(config)['import_ready'] is False


@pytest.mark.parametrize('day', ['2026-10-01', '2026-10-02'])
def test_source_account_header_cannot_be_replaced_by_the_metadata_assertion(day):
    config = current_setup(); p = Path('inputs', config['current_period']['notes'][day]['document'])
    p.write_text(p.read_text().replace(config['account']['source_account_ref'], 'OTHER PEA')); refresh(config, day)
    with pytest.raises(RuntimeError, match='^DAILY_SOURCE_ACCOUNT_CONFLICT$'): run()


def test_future_current_note_refuses_before_journal_publication():
    config = current_setup(days=(31,))
    with pytest.raises(RuntimeError, match='^CURRENT_NOTE_DAY_CONFLICT$'): run()
    assert not paths(config)[0].exists()


def test_current_cli_stdout_contains_only_counts_and_codes(capsys):
    config = current_setup()
    assert bd.main(['daily-preview', '--config', 'inputs/config.yaml', '--input-root', 'inputs',
                    '--as-of', '2026-10-12', '--max-bytes', '1000000', '--max-depth', '32']) == 2
    output = capsys.readouterr().out; summary = json.loads(output)
    assert summary['unresolved_exceptions'] == 3 and summary['import_ready'] is False
    assert config['account']['source_account_ref'] not in output and 'www.boursedirect.fr' not in output


@pytest.mark.parametrize('reference', ['index', 'index_metadata', 'document', 'metadata'])
def test_every_current_input_is_protected_against_output_hard_link_aliases(reference):
    config = current_setup(); run(); state, output = paths(config)
    entry = config['current_period']; ref = entry[reference] if reference.startswith('index') else entry['notes']['2026-10-02'][reference]
    source = Path('inputs', ref); output.unlink(); os.link(source, output); before = source.read_bytes(), state.read_bytes()
    with pytest.raises(RuntimeError, match='^OUTPUT_INPUT_COLLISION$'): run()
    assert before == (source.read_bytes(), state.read_bytes())


def test_nearby_midday_destination_trade_remains_uncertain_even_with_identical_cash_fields():
    config = current_setup(); source = bd.parse_contract_note(Path('inputs/current-2.html').read_text(), 32)['notes'][0]
    mapping = config['mappings'][source['isin']]
    Path('inputs/snapshot.json').write_text(json.dumps({'count': 1, 'activities': [{'id': 'synthetic-remote', 'accountId': config['account']['target_account_id'],
        'account': {'id': config['account']['target_account_id'], 'isExcluded': False, 'tags': []}, 'date': '2026-10-02T11:32:12.081Z', 'type': 'BUY', 'currency': 'EUR',
        'quantity': float(source['quantity']), 'unitPrice': float(source['unit_price']), 'fee': float(source['brokerage'] + source['vat']), 'comment': None,
        'isExcluded': False, 'tags': [], 'assetProfile': {'symbol': mapping['symbol'], 'dataSource': 'YAHOO', 'currency': 'EUR'}}]}))
    run(); note = saved(config)['current_period_observations']['notes']['2026-10-02']['notes'][0]
    assert note['price_currency'] is None and len(note['destination_candidates']) == 1
    candidate = note['destination_candidates'][0]
    assert candidate['fee_delta_remote_minus_source'] == '0' and candidate['date_context_verified'] is False
    assert candidate['certain_match'] is False and candidate['original_timestamp'] == '2026-10-02T11:32:12.081Z'

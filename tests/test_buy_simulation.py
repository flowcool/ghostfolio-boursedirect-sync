"""Task 1.1 financial regression, from an anonymized retained real BUY notice."""
from pathlib import Path

import pytest

import boursedirect_to_ghostfolio as connector


ACCOUNT = {'source_account_ref': 'SYNTHETIC001 PEA'}
MAPPING = {'FR0000000002': {'symbol': 'VERIFIED.PA', 'currency': 'EUR'}}


def real_buy():
    path = Path(__file__).parent / 'fixtures/note-buy-anonymized-real.html'
    return connector.parse_contract_note(path.read_text(), 16)


def test_real_domestic_buy_retains_row_date_precision_and_brokerage():
    assert connector.simulate_buy_notice(real_buy(), ACCOUNT, MAPPING) == [{
        'type': 'BUY', 'date': '2019-02-06T00:00:00.000Z', 'isin': 'FR0000000002',
        'symbol': 'VERIFIED.PA', 'currency': 'EUR', 'quantity': '12', 'unitPrice': '8.125', 'fee': '1.9'}]


def test_other_account_and_missing_mapping_refuse():
    with pytest.raises(RuntimeError, match='NOTICE_ACCOUNT_MISMATCH'):
        connector.simulate_buy_notice(real_buy(), {'source_account_ref': 'SYNTHETIC002 PEA'}, MAPPING)
    with pytest.raises(RuntimeError, match='EXPLICIT_MAPPING_REQUIRED'):
        connector.simulate_buy_notice(real_buy(), ACCOUNT, {})


def test_vat_and_non_eur_price_skip_and_fail_without_hiding_valid_buy(capsys):
    for field, value in [('vat', connector.Decimal('0.01')), ('price_currency', 'USD')]:
        document = real_buy()
        document['notes'].insert(0, dict(document['notes'][0], **{field: value}))
        failures, skipped = [], []
        assert len(connector.simulate_buy_notice(document, ACCOUNT, MAPPING,
            failures=failures, skipped=skipped)) == 1
        assert len(failures) == len(skipped) == 1
        assert '"level": "error"' in capsys.readouterr().out


@pytest.mark.parametrize('mode,code', [('0', 'IMPORT_NOT_IMPLEMENTED'), ('false', 'IMPORT_NOT_IMPLEMENTED'),
    ('invalid', 'INVALID_DRY_RUN')])
def test_unimplemented_or_invalid_modes_refuse_before_acquisition(monkeypatch, mode, code):
    monkeypatch.setenv('DRY_RUN', mode)
    with pytest.raises(RuntimeError, match=code):
        connector.buy_simulation_config()


@pytest.mark.parametrize('mode', [None, '1', 'true', 'yes', 'on'])
def test_default_and_explicit_simulation_use_sibling_mapping(tmp_path, monkeypatch, mode):
    monkeypatch.delenv('DRY_RUN', raising=False)
    if mode is not None:
        monkeypatch.setenv('DRY_RUN', mode)
    monkeypatch.setenv('CRON', '')
    monkeypatch.setenv('BD_SOURCE_ACCOUNT_REF', ACCOUNT['source_account_ref'])
    monkeypatch.setenv('GHOST_ACCOUNT_ID', 'synthetic-destination')
    mapping = tmp_path / 'mapping.yaml'
    mapping.write_text('FR0000000002: {symbol: VERIFIED.PA, currency: EUR}\n')
    monkeypatch.setenv('MAPPING_FILE', str(mapping))
    assert connector.buy_simulation_config()['mappings'] == MAPPING


def test_schedule_refuses_before_broker_or_destination(monkeypatch):
    monkeypatch.setenv('DRY_RUN', '1')
    monkeypatch.setenv('CRON', '0 6 * * *')
    with pytest.raises(RuntimeError, match='SCHEDULING_NOT_IMPLEMENTED'):
        connector.buy_simulation_config()


def test_readable_empty_map_is_valid_but_empty_yaml_or_missing_file_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv('DRY_RUN', '1')
    monkeypatch.setenv('CRON', '')
    monkeypatch.setenv('BD_SOURCE_ACCOUNT_REF', ACCOUNT['source_account_ref'])
    monkeypatch.setenv('GHOST_ACCOUNT_ID', 'synthetic-destination')
    path = tmp_path / 'mapping.yaml'
    monkeypatch.setenv('MAPPING_FILE', str(path))
    with pytest.raises(RuntimeError, match='MAPPING_FILE_UNREADABLE_OR_INVALID'):
        connector.buy_simulation_config()
    path.write_text('{}\n')
    assert connector.buy_simulation_config()['mappings'] == {}
    for raw, code in (('', 'INVALID_KEYED_YAML'), ('[]', 'INVALID_KEYED_YAML'),
        ('FR0000000002: {symbol: BAD, currency: USD}', 'INVALID_EXPLICIT_MAPPING'),
        ('FR0000000002: {symbol: BAD, currency: EUR, venue: Paris}', 'INVALID_EXPLICIT_MAPPING')):
        path.write_text(raw)
        with pytest.raises(RuntimeError, match=code):
            connector.buy_simulation_config()


def candidate(symbol='VERIFIED.PA', currency='EUR', source='YAHOO', isin='FR0000000002'):
    return {'isin': isin, 'symbol': symbol, 'currency': currency, 'dataSource': source}


def test_override_and_unique_profile_precede_lookup():
    lookup = lambda isin: pytest.fail('lookup must not run')
    assert connector.resolve_instrument('FR0000000002', MAPPING, [candidate('OTHER.PA')], lookup) == MAPPING['FR0000000002']
    assert connector.resolve_instrument('FR0000000002', {}, [candidate(), candidate()], lookup) == MAPPING['FR0000000002']


def test_lookup_uses_isin_and_only_one_distinct_eligible_eur_symbol():
    calls = []
    def lookup(isin):
        calls.append(isin)
        return [candidate(), candidate(), candidate('US', 'USD'), candidate('CUSTOM', source='MANUAL'),
                candidate('NO_CURRENCY', currency=None)]
    assert connector.resolve_instrument('FR0000000002', {}, [candidate(isin='FR0000000010')], lookup) == MAPPING['FR0000000002']
    assert calls == ['FR0000000002']


@pytest.mark.parametrize('items,code', [([], 'INSTRUMENT_UNRESOLVED'),
    ([candidate('A.PA'), candidate('B.PA')], 'INSTRUMENT_AMBIGUOUS'),
    ([candidate('US', 'USD'), candidate('NO_CURRENCY', currency=None)], 'INSTRUMENT_UNRESOLVED')])
def test_unresolved_lookup_reports_candidates(items, code, capsys):
    import json
    assert connector.resolve_instrument('FR0000000002', {}, [], lambda isin: items) is None
    row = json.loads(capsys.readouterr().out)
    assert row['code'] == code
    assert row['candidate_tickers'] == sorted(item['symbol'] for item in items)


def test_ambiguous_existing_profiles_refuse_without_lookup(capsys):
    assert connector.resolve_instrument('FR0000000002', {}, [candidate('A.PA'), candidate('B.PA')],
        lambda isin: pytest.fail('do not replace ambiguous existing profiles')) is None
    assert 'INSTRUMENT_AMBIGUOUS' in capsys.readouterr().out


def test_provider_failure_is_bounded_and_skips_only_affected_buy(capsys):
    def lookup(isin):
        raise RuntimeError('sensitive-provider-detail')
    assert connector.resolve_instrument('FR0000000002', {}, [], lookup) is None
    output = capsys.readouterr().out
    assert 'INSTRUMENT_LOOKUP_FAILED' in output and 'sensitive' not in output
    document = real_buy()
    failed = dict(document['notes'][0], isin='FR0000000010')
    document['notes'] = [failed, document['notes'][0]]
    failures = []
    result = connector.simulate_buy_notice(document, ACCOUNT, {}, lambda isin: MAPPING.get(isin), failures)
    assert len(result) == 1 and result[0]['unitPrice'] == '8.125'
    assert failures == ['FR0000000010']


@pytest.mark.parametrize('raw,code', [('', 'INVALID_KEYED_YAML'), ('[]', 'INVALID_KEYED_YAML'),
    ('{}\n{}', 'INVALID_KEYED_YAML'), ('key: 1\nkey: 2', 'YAML_DUPLICATE_KEY'),
    ('key: &alias {}', 'YAML_ALIAS_NOT_SUPPORTED'), ('1: {}', 'YAML_STRING_KEYS_REQUIRED'),
    ('key: ' + '[' * 34 + '0' + ']' * 34, 'YAML_TOO_DEEP')])
def test_yaml_diagnostics_remain_visible_before_any_network(raw, code, tmp_path, monkeypatch, capsys):
    import json
    # The real one-shot entrypoint sets a process-wide private umask. Isolate it
    # here so these early-refusal checks cannot alter other tests' permissions.
    monkeypatch.setattr(connector.os, 'umask', lambda mask: 0o022)
    monkeypatch.setenv('DRY_RUN', '1')
    monkeypatch.setenv('CRON', '')
    monkeypatch.setenv('BD_SOURCE_ACCOUNT_REF', ACCOUNT['source_account_ref'])
    monkeypatch.setenv('GHOST_ACCOUNT_ID', 'synthetic-destination')
    path = tmp_path / 'mapping.yaml'
    path.write_text(raw)
    monkeypatch.setenv('MAPPING_FILE', str(path))
    assert connector.main(['--sync']) == 1
    assert json.loads(capsys.readouterr().out) == {'code': code, 'financial_writes': 0, 'imported': 0}

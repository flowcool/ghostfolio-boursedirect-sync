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


def test_vat_and_non_eur_price_refuse():
    for field, value in [('vat', connector.Decimal('0.01')), ('price_currency', 'USD')]:
        document = real_buy()
        document['notes'][0][field] = value
        with pytest.raises(RuntimeError, match='BUY_CURRENCY_OR_VAT_UNVERIFIED'):
            connector.simulate_buy_notice(document, ACCOUNT, MAPPING)


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

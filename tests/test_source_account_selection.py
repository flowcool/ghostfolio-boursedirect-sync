"""Select the configured broker reference, never another account with its wrapper."""
import copy

import pytest

from test_source_notice_window import calendar, no_network
from test_source_qualification import qualification, ORIGIN

ACCOUNT = {'source_account_ref': 'ACCOUNT_B PEA',
    'account_key': '11111111-1111-4111-8111-111111111111', 'target_account_id': 'destination-b'}
FORM = '''<form method=GET><input type=hidden name=ong value=5>
<select id=nc name=nc><option value=1 selected>ACCOUNT_A Owner (Compte PEA)</option>
<option value=2>ACCOUNT_B Owner (Compte PEA)</option></select></form>'''


def select(form=FORM):
    state = qualification.planner(notice_as_of='2026-10-12', account=ACCOUNT)
    qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', form.encode(), 'frame_document')
    row = qualification.next_document(state)
    assert row['accounts_verified'] is False and row['configured_account_verified'] is False
    assert row['document']['url'].endswith('ong=5&nc=2')
    assert state['accounts'] == {'PEA': '2'} and state['account_ids'] == {'PEA': 'ACCOUNT_B'}
    return state, row['document']


def test_selected_reference_works_with_multiple_peas_and_no_peapme():
    state, doc = select()
    selected = FORM.replace('value=1 selected', 'value=1').replace('value=2>', 'value=2 selected>')
    qualification.discover(state, doc['url'], selected.encode() + calendar(nc=2, days=()), 'frame_document')
    assert state['verified'] == {'PEA'}
    assert qualification.next_document(state)['configured_account_verified'] is True
    state['queue'].clear()
    for month in (9, 8, 7):
        url = ORIGIN + f'/priv/new/avis-operes.php?nc=2&month={month}&year=2026'
        state['current'] = {'account': 'PEA', 'url': url}
        qualification.discover(state, url, calendar(month=month, nc=2, days=()), 'frame_document')
        state['queue'].clear()
    assert qualification.next_document(state)['documents'] == {
        'complete': True, 'monthly_statements': 0, 'contract_notes': 0}
    assert state['account_binding'] == ACCOUNT


@pytest.mark.parametrize('form', [FORM.replace('ACCOUNT_B', 'ACCOUNT_C'),
    FORM.replace('ACCOUNT_B Owner (Compte PEA)', 'ACCOUNT_B Owner (Compte PEA-PME)'),
    FORM.replace('</select>', '<option value=3>ACCOUNT_B Owner (Compte PEA)</option></select>'),
    FORM.replace('</select>', '<option value=2>ACCOUNT_C Owner (Compte PEA)</option></select>')])
def test_missing_wrong_wrapper_or_ambiguous_reference_refuses(form):
    with pytest.raises(RuntimeError): select(form)


def test_wrong_selected_option_refuses_before_authentication_confirmation():
    state, doc = select()
    with pytest.raises(RuntimeError):
        qualification.discover(state, doc['url'], FORM.encode() + calendar(nc=2, days=()), 'frame_document')
    assert state['verified'] == set()


@pytest.mark.parametrize('key,value', [('source_account_ref', 'ACCOUNT_B CTO'),
    ('source_account_ref', 'ACCOUNT_B'), ('account_key', 'invalid'),
    ('target_account_id', ''), ('target_account_id', 'destination\n')])
def test_invalid_binding_refuses_before_source_planning(key, value):
    account = {**ACCOUNT, key: value}
    with pytest.raises(RuntimeError):
        qualification.planner(notice_as_of='2026-10-12', account=account)


def test_configured_selection_requires_notice_mode_and_does_not_mutate_input():
    account = copy.deepcopy(ACCOUNT)
    with pytest.raises(RuntimeError): qualification.planner(account=account)
    qualification.planner(notice_as_of='2026-10-12', account=account)
    assert account == ACCOUNT


@pytest.mark.parametrize('change', ['public', 'duplicates', 'binding', 'mode'])
def test_invalid_private_account_config_refuses_before_live_helpers(tmp_path, monkeypatch, change):
    import yaml
    path = tmp_path / 'account.yaml'
    config = {'schema_version': 1, 'source_mode': 'notices', 'account': ACCOUNT}
    if change == 'binding': config['account'] = {**ACCOUNT, 'target_account_id': ''}
    if change == 'mode': config['source_mode'] = 'statements'
    path.write_text(yaml.safe_dump(config) + ('schema_version: 1\n' if change == 'duplicates' else ''))
    path.chmod(0o644 if change == 'public' else 0o600)
    monkeypatch.setattr(qualification.replay, 'helper', lambda *args: pytest.fail('Invalid binding accessed live runtime'))
    with pytest.raises(RuntimeError):
        qualification.qualify(tmp_path, tmp_path / 'lab', {}, notice_as_of='2026-10-12', account_config='account.yaml')

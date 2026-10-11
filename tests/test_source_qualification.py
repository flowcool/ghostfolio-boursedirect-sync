"""Saved source navigation must preserve account identity and source provenance."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_qualification as qualification

ORIGIN = qualification.ORIGIN
ACCOUNT_FORM = '''<form name=frmCompte method=GET><input type=hidden name=ong value=RO>
<select id=nc name=nc><option value=ACCOUNT_A selected>ACCOUNT_A Account PEA</option>
<option value=ACCOUNT_B>ACCOUNT_B Account PEA-PME</option></select></form>'''


def test_source_get_form_selection_keeps_wrappers_distinct_and_header_checked():
    state = qualification.planner()
    qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', ACCOUNT_FORM.encode(), 'frame_document')
    first = qualification.next_document(state)['document']
    assert first['url'] == ORIGIN + '/priv/new/avis-operes.php?ong=RO&nc=ACCOUNT_A'
    qualification.discover(state, first['url'], (ACCOUNT_FORM + "<a href=\"javascript:ouvrePopup('releveOpe.php?id=synthetic',1)\">Note</a>").encode(), first['role'])
    note = qualification.next_document(state)['document']
    assert note['role'] == 'contract_note'
    assert note['url'] == ORIGIN + '/priv/new/releveOpe.php?id=synthetic'
    raw = b"<strong>Avis d'Op\xc3\xa9ration</strong><table><tr><td>COMPTE N\xc2\xb0</td><td>ACCOUNT_A PEA</td></tr></table>"
    qualification.discover(state, note['url'], raw, note['role'])
    second = qualification.next_document(state)['document']
    assert second['url'].endswith('ong=RO&nc=ACCOUNT_B')
    qualified_form = ACCOUNT_FORM.replace('ACCOUNT_A selected', 'ACCOUNT_A').replace('value=ACCOUNT_B>', 'value=ACCOUNT_B selected>')
    qualification.discover(state, second['url'], qualified_form.encode(), second['role'])
    result = qualification.next_document(state)
    assert result['accounts_verified'] is True
    assert result['documents'] == {'complete': False, 'monthly_statements': 0, 'contract_notes': 1}


@pytest.mark.parametrize('html', [ACCOUNT_FORM.replace('PEA-PME', 'PEA'),
    ACCOUNT_FORM.replace('ACCOUNT_B', 'ACCOUNT_A'), ACCOUNT_FORM.replace('method=GET', 'method=POST')])
def test_ambiguous_inventory_and_mutating_forms_refuse(html):
    with pytest.raises(RuntimeError):
        qualification.discover(qualification.planner(), ORIGIN + '/priv/new/avis-operes.php', html.encode(), 'frame_document')


def test_wrong_selected_account_cannot_prove_navigation():
    state = qualification.planner()
    qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', ACCOUNT_FORM.encode(), 'frame_document')
    qualification.next_document(state)
    qualification.discover(state, state['current']['url'], ACCOUNT_FORM.encode(), 'frame_document')
    qualification.next_document(state)
    with pytest.raises(RuntimeError):
        qualification.discover(state, state['current']['url'], ACCOUNT_FORM.encode(), 'frame_document')
    assert state['verified'] == {'PEA'}


@pytest.mark.parametrize('header,title', [('ACCOUNT_B PEA', "Avis d'Opération"),
    ('PREFIXACCOUNT_A PEA', "Avis d'Opération"), ('ACCOUNT_A PEA', 'Login')])
def test_document_requires_known_title_and_exact_account_token(header, title):
    state = qualification.planner()
    state.update(accounts={'PEA': 'ACCOUNT_A', 'PEA-PME': 'ACCOUNT_B'}, account_ids={'PEA': 'ACCOUNT_A', 'PEA-PME': 'ACCOUNT_B'}, verified={'PEA'}, current={'account': 'PEA'})
    html = f'<strong>{title}</strong><table><tr><td>COMPTE N°</td><td>{header}</td></tr></table>'
    with pytest.raises(RuntimeError):
        qualification.discover(state, ORIGIN + '/priv/new/releveOpe.php', html.encode(), 'contract_note')
    assert not state['documents']


@pytest.mark.parametrize('url', ['https://foreign.invalid/priv/new/releveOpe.php',
    ORIGIN + '/fr/page/ordres', ORIGIN + '/priv/new/releveOpe.php#fragment'])
def test_only_observed_read_paths_on_exact_origin_are_candidates(url):
    with pytest.raises(RuntimeError):
        qualification.source_url(ORIGIN + '/fr/page/inventaire', url)


def test_incomplete_lists_allow_only_a_retained_source_and_verified_account_selection():
    state = qualification.planner()
    state.update(accounts={'PEA': 'ACCOUNT_A', 'PEA-PME': 'ACCOUNT_B'}, verified={'PEA', 'PEA-PME'},
        current={'account': 'PEA-PME'})
    choice = {'url': ORIGIN + '/priv/new/avis-operes.php?nc=ACCOUNT_A',
        'role': 'frame_document', 'sourceSha256': 'a' * 64, 'account': 'PEA'}
    captured = {'a' * 64: {'role': 'frame_document'}}
    assert qualification.validate_selection(state, captured, choice)['verify_account'] is True
    state['seen'].add(('PEA', choice['url'], ''))
    with pytest.raises(RuntimeError):
        qualification.validate_selection(state, captured, choice)
    state['seen'].clear()
    state['documents']['PEA'] = {'monthly_statement': {}}
    acquired = {**choice, 'role': 'monthly_statement'}
    with pytest.raises(RuntimeError):
        qualification.validate_selection(state, captured, acquired)
    state['documents'].clear()
    for invalid in ({**choice, 'sourceSha256': 'b' * 64}, {**choice, 'account': 'unknown'},
        {**choice, 'url': ORIGIN + '/priv/new/avis-operes.php'},
        {**choice, 'url': ORIGIN + '/priv/new/avis-operes.php?nc=ACCOUNT_B'}):
        with pytest.raises(RuntimeError):
            qualification.validate_selection(state, captured, invalid)


@pytest.mark.parametrize('browser_failure,cli_result', [(False, True), (True, True), (False, False)])
@pytest.mark.parametrize('public_only', [False, True])
def test_failed_delivery_attempts_both_owned_cleanups_and_retains_uncertain_lease(tmp_path, monkeypatch,
        browser_failure, cli_result, public_only):
    import json
    from types import SimpleNamespace
    root = tmp_path / 'project'
    root.mkdir(mode=0o700)
    lab = root / 'inputs/lab'
    lab.mkdir(parents=True, mode=0o700)
    (root / 'inputs/source-observations').mkdir(mode=0o700)
    code = root / 'collector/lab'
    code.mkdir(parents=True)
    (code / 'source-browser-pipe.mjs').write_text('// synthetic')
    (root / 'binding.json').write_text(json.dumps({'containerId': 'a' * 64, 'destination': 'synthetic',
        'egressProxy': 'http://10.1.2.3:8080', 'configuration': {'schema_version': 3,
            'vaultOrigin': 'https://vault.synthetic.invalid', 'cli': {}}}))
    (root / 'binding.json').chmod(0o600)
    (root / 'contract.yaml').write_text('{}')
    qualification.replay.private._publish(root / 'inspection.yaml', {'selected': {
        'itemId': '11111111-1111-4111-8111-111111111111', 'principalHash': 'b' * 64,
        'uri': ORIGIN + '/fr/login', 'uriAliasesSha256': 'c' * 64}}, exclusive=True)
    inventory = {'_verified_helpers': {}, 'source_contract': 'contract.yaml', 'evidence': {
        'vault_cli_binding': {'path': 'binding.json'}, 'vault_alias_inspection': {'path': 'inspection.yaml'}}}
    calls = []

    def delivery_failure(*args):
        # A restarted container has an empty tmpfs: prepare the delivery parent
        # before attempting a shell redirection into it.
        assert args[0] == ['docker', 'exec', '-u', '1000:1000', 'b' * 64,
            'mkdir', '-p', '/home/fixture/proof/lab']
        raise RuntimeError('SYNTHETIC_DELIVERY_FAILURE')

    def browser_stop():
        calls.append('browser')
        if browser_failure:
            raise RuntimeError('SYNTHETIC_STOP_FAILURE')

    def helper(lab_path, name, verified):
        assert lab_path == lab
        if name == 'qualify':
            return SimpleNamespace(owned=lambda *args: {'HostConfig': {'Init': True}}, checked=delivery_failure,
                durable=SimpleNamespace(_sync_directory=lambda path: None))
        if name == 'attest':
            return SimpleNamespace(attest=lambda: {'containers': {'bitwarden-cli': {'id': 'a' * 64}}})
        if name == 'broker-attest':
            return SimpleNamespace(attest=lambda: {'containers': {'browser': {'id': 'b' * 64}}})
        if name == 'broker-stop':
            return SimpleNamespace(stop=browser_stop)
        pytest.fail('No provision, SSH or credentials are allowed in this fixture')

    def cli_stop(*args):
        calls.append('cli')
        return cli_result

    monkeypatch.setattr(qualification, 'CODE_ROOT', root)
    monkeypatch.setattr(qualification.replay, 'helper', helper)
    monkeypatch.setattr(qualification, 'stop_owned_cli', cli_stop)
    monkeypatch.setattr(qualification.subprocess, 'check_output',
        lambda args, **kwargs: 'd' * 40 if kwargs.get('text') else b'')
    with pytest.raises(RuntimeError, match='SYNTHETIC_DELIVERY_FAILURE'):
        qualification.qualify(root, lab, inventory, public_only=public_only)
    assert calls == (['browser'] if public_only else ['browser', 'cli'])
    cleanup = not browser_failure and (public_only or cli_result)
    assert (lab / 'vault-operation.lock').exists() == (not cleanup)
    attempt = next((root / 'inputs/source-observations').glob('qualification-*/attempt.yaml'))
    record = qualification.replay.private._read(attempt)
    assert record['failed_phase'] == 'source_delivery'
    assert record['exact_owned_cleanup_verified'] == cleanup
    assert record['cli_unused'] is public_only
    if public_only:
        assert record['cli_stopped_owned'] is None


def test_selector_indexes_are_distinct_from_stable_account_identifiers():
    form = ACCOUNT_FORM.replace('value=ACCOUNT_A', 'value=1').replace('value=ACCOUNT_B', 'value=2')
    state = qualification.planner()
    qualification.discover(state, ORIGIN + '/priv/new/avis-operes.php', form.encode(), 'frame_document')
    first = qualification.next_document(state)['document']
    assert first['url'].endswith('nc=1')
    qualification.discover(state, first['url'], form.encode(), first['role'])
    assert state['account_ids'] == {'PEA': 'ACCOUNT_A', 'PEA-PME': 'ACCOUNT_B'}
    note = "<strong>Avis d'Opération</strong><table><tr><td>COMPTE N°</td><td>ACCOUNT_A PEA</td></tr></table>"
    qualification.discover(state, ORIGIN + '/priv/new/releveOpe.php?id=synthetic', note.encode(), 'contract_note')
    assert 'contract_note' in state['documents']['PEA']
    wrong = note.replace('ACCOUNT_A PEA', '1 PEA')
    with pytest.raises(RuntimeError):
        qualification.discover(state, ORIGIN + '/priv/new/releveOpe.php?id=wrong', wrong.encode(), 'contract_note')
    changed = form.replace('ACCOUNT_A Account', 'ACCOUNT_C Account')
    with pytest.raises(RuntimeError):
        qualification.discover(state, first['url'], changed.encode(), 'frame_document')


@pytest.mark.parametrize('changed', [
    ACCOUNT_FORM.replace('>ACCOUNT_B Account', '>ACCOUNT_A Account'),
    ACCOUNT_FORM.replace('>ACCOUNT_A Account', '>1 Account'),
])
def test_inventory_refuses_missing_or_duplicate_stable_identifiers(changed):
    with pytest.raises(RuntimeError):
        qualification.discover(qualification.planner(), ORIGIN + '/priv/new/avis-operes.php', changed.encode(), 'frame_document')


def test_saved_month_form_only_submits_exact_owned_account_and_observed_period():
    state = qualification.planner()
    html = ACCOUNT_FORM.replace('value=ACCOUNT_A', 'value=1').replace('value=ACCOUNT_B', 'value=2')
    monthly = '<form method=post><input type=hidden name=nc value=1><select name=RlvCombo><option value=1 selected>September</option><option value=2>August</option></select></form>'
    url = ORIGIN + '/priv/new/releves.php'
    qualification.discover(state, url, (html + monthly).encode(), 'frame_document')
    wrapper = qualification.next_document(state)['document']
    qualification.discover(state, wrapper['url'], (html + monthly).encode(), 'frame_document')
    period = qualification.next_document(state)['document']
    assert period == {'url': url, 'role': 'frame_document', 'sourceSha256': qualification.digest((html + monthly).encode()), 'method': 'POST', 'fields': {'nc': '1', 'RlvCombo': '2'}}
    state['documents']['PEA'] = {'monthly_statement': {}}
    assert qualification.next_document(state)['document']['url'].endswith('nc=2')
    bad = monthly.replace('name=nc value=1', 'name=nc value=2')
    state['current'] = {'account': 'PEA', 'verify_account': True}
    with pytest.raises(RuntimeError):
        qualification.discover(state, wrapper['url'], (html + bad).encode(), 'frame_document')


def test_acquisition_is_complete_only_for_matching_note_and_statement_periods():
    state = qualification.planner()
    state['verified'] = {'PEA', 'PEA-PME'}
    for account in state['verified']:
        state['documents'][account] = {'monthly_statement': {'period': '202609'}, 'contract_note': {'period': '202610'}}
    assert qualification.next_document(state)['documents']['complete'] is False
    for account in state['verified']:
        state['documents'][account]['contract_note']['period'] = '202609'
    assert qualification.next_document(state)['documents']['complete'] is True
    state['documents']['PEA']['contract_note']['period'] = None
    assert qualification.next_document(state)['documents']['complete'] is False


def test_note_period_accepts_source_zero_padded_month():
    state = qualification.planner()
    state.update(account_ids={'PEA': 'ACCOUNT_A'}, verified={'PEA'}, current={'account': 'PEA'})
    html = "<strong>Avis d'Opération</strong><table><tr><td>COMPTE N°</td><td>ACCOUNT_A PEA</td></tr></table>"
    qualification.discover(state, ORIGIN + '/priv/new/releveOpe.php?year=2026&month=09&day=23', html.encode(), 'contract_note')
    assert state['documents']['PEA']['contract_note']['period'] == '202609'


@pytest.mark.parametrize('period,label,value', [('202607', 'Juillet 2026', '3'),
    ('202608', 'Août 2026', '2')])
def test_preferred_statement_uses_only_observed_month_value(period, label, value):
    state = qualification.planner({'PEA': period})
    state.update(accounts={'PEA': '1', 'PEA-PME': '2'}, verified={'PEA'}, current={'account': 'PEA'})
    html = ('<form method=post><input type=hidden name=nc value=1><select name=RlvCombo>'
        '<option value=1 selected>Septembre 2026</option><option value=2>Août 2026</option>'
        '<option value=3>Juillet 2026</option></select></form>'
        '<a href="releveCompte.php?dt=20260930">Current</a>')
    qualification.discover(state, ORIGIN + '/priv/new/releves.php', html.encode(), 'frame_document')
    assert len(state['queue']) == 1
    choice = qualification.next_document(state)['document']
    assert choice['method'] == 'POST'
    assert choice['fields'] == {'nc': '1', 'RlvCombo': value}
    assert choice['sourceSha256'] == qualification.digest(html.encode())


@pytest.mark.parametrize('options', [
    '<option value=1 selected>Septembre 2026</option>',
    '<option value=1 selected>Juillet 2026</option><option value=2>Juillet 2026</option>',
    '<option value=22>Juillet 2026</option>',
])
def test_unavailable_ambiguous_or_invalid_preferred_month_refuses(options):
    state = qualification.planner({'PEA': '202607'})
    state.update(accounts={'PEA': '1'}, verified={'PEA'}, current={'account': 'PEA'})
    html = ('<form method=post><input type=hidden name=nc value=1>'
        '<select name=RlvCombo>' + options + '</select></form>')
    with pytest.raises(RuntimeError):
        qualification.discover(state, ORIGIN + '/priv/new/releves.php', html.encode(), 'frame_document')
    assert not state['queue']


def test_preferred_statement_rejects_wrong_period_and_accepts_exact_observed_link():
    state = qualification.planner({'PEA': '202607'})
    state.update(account_ids={'PEA': 'ACCOUNT_A'}, verified={'PEA'}, current={'account': 'PEA'})
    html = '<strong>RELEVE DE COMPTE</strong><table><tr><td>COMPTE N°</td><td>ACCOUNT_A PEA</td></tr></table>'
    with pytest.raises(RuntimeError):
        qualification.discover(state, ORIGIN + '/priv/new/releveCompte.php?dt=20260930', html.encode(), 'monthly_statement')
    assert not state['documents']
    qualification.discover(state, ORIGIN + '/priv/new/releveCompte.php?dt=20260731', html.encode(), 'monthly_statement')
    assert state['documents']['PEA']['monthly_statement']['period'] == '202607'


@pytest.mark.parametrize('periods', [[], {'unknown': '202607'}, {'PEA': 202607},
    {'PEA': '202613'}, {'PEA': '20267'}, {'PEA': None}])
def test_invalid_statement_preferences_refuse_before_navigation(periods):
    with pytest.raises(RuntimeError):
        qualification.planner(periods)


def test_invalid_private_preference_refuses_before_owned_helper_access(tmp_path, monkeypatch):
    (tmp_path / 'inputs/source-observations').mkdir(parents=True, mode=0o700)
    qualification.replay.private._publish(tmp_path / 'inputs/source-observations/statement-preference.yaml',
        {'schema_version': 2, 'statement_periods': {'PEA': '202607'}}, exclusive=True)
    monkeypatch.setattr(qualification.replay, 'helper', lambda *args: pytest.fail('No runtime access allowed'))
    with pytest.raises(RuntimeError):
        qualification.qualify(tmp_path, tmp_path / 'lab', {})

import copy
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from test_source_qualification import qualification, ORIGIN

FUNCTION = """function MoisPrecedent(tr,nc,month,year) {
  if(month == 1) { --year; month=13; }
  document.location.href = 'avis-operes.php?tr='+tr+'&nc='+nc+'&month='+(month-1)+'&year='+year;
}
"""
MONTHS = ('Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre')


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('Offline source planning only')
    monkeypatch.setattr(socket, 'socket', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)


def state(clock='2026-10-12'):
    result = qualification.planner(notice_as_of=clock)
    result.update(accounts={'PEA': '1', 'PEA-PME': '2'}, account_ids={'PEA': 'ACCOUNT_A', 'PEA-PME': 'ACCOUNT_B'}, verified={'PEA', 'PEA-PME'})
    return result


def calendar(month=10, year=2026, nc=1, days=(2,)):
    notes = ''.join(f'''<a href="javascript:ouvrePopup('releveOpe.php?nc={nc}&amp;type=RO&amp;year={year}&amp;month={month}&amp;day={day}&amp;trash=/avis.pdf','encours');">{day:02d}</a>''' for day in days)
    empty = '' if days else "<div class='msg texte1T7A'>Vous n'avez pas effectué d'opération ce mois-ci.</div>"
    return (f"<script>{FUNCTION}</script><table><tr><td class='topdatas'><span>{year}</span></td></tr><tr><td class='topdatas'><span>{MONTHS[month-1]}</span></td></tr></table>"
            + f'''<a href="javascript:MoisPrecedent('RO',{nc},{month},{year})">Previous</a>''' + notes + empty).encode()


def visit(result, account, month, year=2026, days=(2,)):
    nc = result['accounts'][account]
    url = ORIGIN + f'/priv/new/avis-operes.php?tr=RO&nc={nc}&month={month}&year={year}'
    result['current'] = {'account': account, 'url': url}
    qualification.discover(result, url, calendar(month, year, int(nc), days), 'frame_document')


def test_plans_window_months_and_all_observed_notes_without_monthly_sources():
    result = state()
    for account in ('PEA', 'PEA-PME'):
        for month in (10, 9, 8, 7):
            visit(result, account, month, days=(2,) if account == 'PEA' else ())
            while result['queue']:
                row = qualification.next_document(result)
                doc = row['document']
                assert doc['role'] != 'monthly_statement' and 'method' not in doc
                if doc['role'] == 'contract_note':
                    ref = result['account_ids'][account] + ' ' + account
                    raw = f"<strong>Avis d'Opération</strong><table><tr><td>COMPTE N°</td><td>{ref}</td></tr></table>".encode()
                    qualification.discover(result, doc['url'], raw, doc['role'])
    done = qualification.next_document(result)
    assert done['documents'] == {'complete': True, 'monthly_statements': 0, 'contract_notes': 4}
    assert len(result['notice_calendars']) == 8


def test_previous_month_follows_exact_observed_javascript_across_new_year():
    result = state('2026-01-12'); visit(result, 'PEA', 1, year=2026, days=())
    doc = qualification.next_document(result)['document']
    query = parse_qs(urlsplit(doc['url']).query)
    assert query == {'tr': ['RO'], 'nc': ['1'], 'month': ['12'], 'year': ['2025']}


@pytest.mark.parametrize('change', ['function', 'account', 'heading', 'missing_empty', 'ambiguous_empty'])
def test_ambiguous_or_unqualified_calendar_refuses(change):
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar(days=())
    if change == 'function': raw = raw.replace(b'--year', b'++year')
    elif change == 'account': raw = raw.replace(b"'RO',1,10", b"'RO',2,10")
    elif change == 'heading': raw = raw.replace(b'Octobre', b'Septembre')
    elif change == 'missing_empty': raw = raw.replace(b"Vous n'avez pas effectu", b'Changed')
    else: raw += b'<a href="releveOpe.php?nc=1">Unexpected note</a>'
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')


def test_missing_account_month_stays_incomplete_even_with_notes():
    result = state(); visit(result, 'PEA', 7, days=()); result['queue'].clear()
    assert qualification.next_document(result)['documents']['complete'] is False


@pytest.mark.parametrize('clock', ['2026-02-30', '2026-10-12T00:00:00', True, '0001-01-01'])
def test_invalid_window_clock_refuses_before_navigation(clock):
    with pytest.raises(RuntimeError): qualification.planner(notice_as_of=clock)


def test_window_never_queues_monthly_or_future_document_links():
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar(days=(2, 13)) + b'<a href="releveCompte.php?nc=1&amp;dt=20260930&amp;type=RE">Statement</a>'
    qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')
    assert len([r for r in result['queue'] if r['role'] == 'contract_note']) == 1
    assert all(r['role'] != 'monthly_statement' for r in result['queue'])


def test_external_source_navigation_script_must_arrive_before_previous_month():
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar(days=()).replace(f'<script>{FUNCTION}</script>'.encode(), b'<script src="/priv/scripts/avis-operes.js"></script>')
    url = ORIGIN + '/priv/new/avis-operes.php?nc=1&ong=5'
    qualification.discover(result, url, raw, 'frame_document')
    assert result['notice_pending_calendars'] and not result['notice_navigation_verified']
    assert all('month=9' not in r['url'] for r in result['queue'])
    script = qualification.next_document(result)['document']
    assert script['url'] == ORIGIN + '/priv/scripts/avis-operes.js'
    qualification.discover(result, script['url'], FUNCTION.encode(), script['role'])
    assert not result['notice_pending_calendars'] and result['notice_navigation_verified']
    previous = qualification.next_document(result)['document']
    assert parse_qs(urlsplit(previous['url']).query)['month'] == ['9']


def test_unrelated_scripts_do_not_prevent_known_calendar_navigation():
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar(days=()).replace(f'<script>{FUNCTION}</script>'.encode(),
        b'<script src="/priv/scripts/avis-operes.js"></script>'
        b'<script src="/unrelated.js"></script><script src="https://other.example/asset.js"></script>')
    qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')
    assert result['notice_pending_calendars']
    assert [row['url'] for row in result['queue']] == [ORIGIN + '/priv/scripts/avis-operes.js']


def test_duplicate_known_navigation_script_links_queue_one_read():
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar(days=()).replace(f'<script>{FUNCTION}</script>'.encode(),
        b'<script src="/priv/scripts/avis-operes.js"></script>' * 2)
    qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')
    assert qualification.next_document(result)['document']['url'] == ORIGIN + '/priv/scripts/avis-operes.js'
    assert qualification.next_document(result)['done'] is True


def test_foreign_navigation_script_cannot_supply_calendar_proof():
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar(days=()).replace(f'<script>{FUNCTION}</script>'.encode(),
        b'<script src="https://other.example/priv/scripts/avis-operes.js"></script>')
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')


def test_changed_external_function_refuses_without_navigation_grant():
    result = state(); result['current'] = {'account': 'PEA'}
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/scripts/avis-operes.js', FUNCTION.replace('month-1', 'month+1').encode(), 'frame_document')
    assert not result['notice_navigation_verified'] and not result['queue']


def test_duplicate_note_account_parameter_refuses():
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar().replace(b'nc=1&amp;type', b'nc=1&amp;nc=2&amp;type')
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')


def test_both_empty_accounts_can_complete_window_without_manufacturing_notes():
    result = state()
    for account in ('PEA', 'PEA-PME'):
        for month in (10,9,8,7):
            visit(result, account, month, days=()); result['queue'].clear()
    assert qualification.next_document(result)['documents'] == {'complete': True, 'monthly_statements': 0, 'contract_notes': 0}


def test_monthly_period_preferences_cannot_enter_notice_window_mode():
    with pytest.raises(RuntimeError): qualification.planner({'PEA': '202609'}, notice_as_of='2026-10-12')


def test_retained_real_calendar_follows_source_script_and_requires_every_offered_notice():
    result = state('2026-10-13')
    result['required_accounts'] = {'PEA'}
    result['verified'] = {'PEA'}
    result['current'] = {'account': 'PEA'}
    raw = (Path(__file__).parent / 'fixtures/notice-calendar-anonymized-real.html').read_bytes()
    qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')
    assert len(result['notice_expected_documents']) == 2
    qualification.discover(result, ORIGIN + '/priv/scripts/avis-operes.js', FUNCTION.encode(), 'frame_document')
    for month in (9, 8, 7):
        visit(result, 'PEA', month, days=())
    result['queue'].clear()
    assert qualification.next_document(result)['documents']['complete'] is False
    result['notice_documents'] = result['notice_expected_documents'].copy()
    coverage = qualification.notice_coverage(result)
    assert coverage['window'] == {'first_day': '2026-07-16', 'last_day': '2026-10-13', 'days': 90}
    assert coverage['observed_months'] == {'PEA': ['2026-07', '2026-08', '2026-09', '2026-10']}
    assert coverage['empty_months'] == {'PEA': ['2026-07', '2026-08', '2026-09']}
    assert qualification.next_document(result)['documents']['complete'] is True


@pytest.mark.parametrize('query', ['nc=2', 'nc=1&nc=2', 'nc=1&month=9&year=2026',
    'nc=1&month=10', 'nc=1&month=10&year=2025'])
def test_calendar_response_must_match_requested_account_and_period(query):
    result = state(); result['current'] = {'account': 'PEA'}
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?' + query,
            calendar(days=()), 'frame_document')
    assert not result['notice_calendars']


@pytest.mark.parametrize('href', ["javascript:changedPopup('releveOpe.php?nc=1')",
    'https://other.example/releveOpe.php?nc=1'])
def test_unqualified_offered_notice_cannot_be_silently_ignored(href):
    result = state(); result['current'] = {'account': 'PEA'}
    raw = calendar().replace(b'javascript:ouvrePopup(', b'javascript:changedPopup(') if href.startswith('javascript:') else calendar(days=()).replace(
        b'</table>', ('</table><a href="' + href + '">Notice</a>').encode())
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', raw, 'frame_document')


@pytest.mark.parametrize('change', ['renamed', 'other_known_path', 'missing_href', 'fragment', 'different_month'])
def test_real_calendar_with_one_valid_and_one_changed_notice_refuses_all(change):
    result = state('2026-10-13'); result['current'] = {'account': 'PEA'}
    raw = (Path(__file__).parent / 'fixtures/notice-calendar-anonymized-real.html').read_bytes()
    soup = qualification.BeautifulSoup(raw, 'html.parser')
    link = soup.select('a.linkE')[1]
    if change == 'renamed': link['href'] = link['href'].replace('releveOpe.php', 'newOpe.php')
    elif change == 'other_known_path': link['href'] = link['href'].replace('releveOpe.php', 'releveCompte.php')
    elif change == 'missing_href': del link['href']
    elif change == 'fragment': link['href'] = '#changed'
    else: link['href'] = link['href'].replace('month=10', 'month=9')
    with pytest.raises(RuntimeError):
        qualification.discover(result, ORIGIN + '/priv/new/avis-operes.php?nc=1', str(soup).encode(), 'frame_document')
    assert not result['queue'] and not result['notice_expected_documents']

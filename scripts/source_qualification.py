"""One owned source qualification; use existing access, private pipes and receipts."""
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import selectors
import signal
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
import source_connection as replay
from source_vault_inspection import read_frame, write_frame, stop_owned_cli

CODE_ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://www.boursedirect.fr'
READ_PATHS = {'/fr/page/inventaire', '/fr/page/mes-comptes', '/fr/page/releves',
    '/fr/page/avis-operes', '/fr/page/avis-d-operes', '/priv/new/releves.php',
    '/priv/new/avis-operes.php', '/priv/new/releveCompte.php', '/priv/new/releveOpe.php',
    '/priv/scripts/avis-operes.js'}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_url(base, relative):
    url = urljoin(base, relative)
    parsed = urlsplit(url)
    replay.require(parsed.scheme + '://' + parsed.netloc == ORIGIN
        and not parsed.username and not parsed.password and not parsed.fragment
        and parsed.path in READ_PATHS and len(url) <= 4096)
    return url


def source_account_binding(account):
    replay.require(isinstance(account, dict) and set(account) == {'source_account_ref', 'account_key', 'target_account_id'})
    replay.require(type(account['source_account_ref']) is str
        and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63} (?:PEA|PEA-PME)', account['source_account_ref']))
    replay.require(type(account['account_key']) is str
        and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}', account['account_key']))
    replay.require(type(account['target_account_id']) is str and account['target_account_id'].strip()
        and len(account['target_account_id']) <= 256
        and not any(ord(c) < 32 or ord(c) == 127 for c in account['target_account_id']))
    return dict(account)


def planner(statement_periods=None, notice_as_of=None, account=None, choose_account=None, discovery_only=False):
    periods = {} if statement_periods is None else statement_periods
    replay.require(isinstance(periods, dict) and set(periods) <= {'PEA', 'PEA-PME'})
    replay.require(all(type(value) is str and re.fullmatch(r'[1-9][0-9]{3}(?:0[1-9]|1[0-2])', value)
        for value in periods.values()))
    state = {'queue': [], 'seen': set(), 'accounts': {}, 'account_ids': {}, 'verified': set(),
        'documents': {}, 'current': None, 'captures': 0, 'statement_periods': dict(periods),
        'required_accounts': {'PEA', 'PEA-PME'}}
    if discovery_only:
        replay.require(account is None and choose_account is None and notice_as_of is not None)
        state['discovery_only'] = True
    if choose_account is not None:
        replay.require(callable(choose_account) and account is None and notice_as_of is not None)
        state['choose_account'] = choose_account
    if account is not None:
        replay.require(notice_as_of is not None)
        state['account_binding'] = source_account_binding(account)
        state['required_accounts'] = {account['source_account_ref'].split(' ', 1)[1]}
    if notice_as_of is not None:
        replay.require(not periods and type(notice_as_of) is str and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', notice_as_of))
        try:
            last = datetime.strptime(notice_as_of, '%Y-%m-%d').date()
            first = last - timedelta(days=89)
        except (ValueError, OverflowError):
            raise RuntimeError('SOURCE_REPLAY_REFUSED') from None
        state['notice_window'] = {'first': first.isoformat(), 'last': last.isoformat()}
        state['notice_calendars'] = set()
        state['notice_empty_calendars'] = set()
        state['notice_expected_documents'] = set()
        state['notice_documents'] = set()
        state['notice_pending_calendars'] = {}
        state['notice_navigation_verified'] = False
    return state


def notice_calendar_previous(state, url, raw, account, parent):
    """Interpret only the exact previously observed source navigation function."""
    if account not in state['verified'] or urlsplit(url).path != '/priv/new/avis-operes.php':
        return None
    soup = BeautifulSoup(raw, 'html.parser')
    calls = set()
    for link in soup.select('a[href]'):
        match = re.fullmatch(r"javascript:MoisPrecedent\('RO',([1-9][0-9]*),([0-9]{1,2}),([0-9]{4})\)", link['href'])
        if match:
            calls.add(match.groups())
    replay.require(len(calls) == 1)
    nc, month, year = next(iter(calls))
    replay.require(nc == state['accounts'][account] and 1 <= int(month) <= 12)
    try:
        html = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError:
        html = raw.decode('cp1252', errors='strict')
    calendar = BeautifulSoup(html, 'html.parser')
    headings = [[' '.join(span.get_text(' ', strip=True).split()) for span in cell.find_all('span', recursive=False)
                 if not span.get('class')] for cell in calendar.select('td.topdatas')]
    months = ('Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre')
    replay.require(headings == [[year], [months[int(month) - 1]]])
    period = year + '-' + month.zfill(2)
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    query = dict(pairs)
    replay.require(len(pairs) == len(query) and query.get('nc') == nc
        and (('month' not in query and 'year' not in query)
            or query.get('month') == str(int(month)) and query.get('year') == year))
    window = state['notice_window']
    replay.require(window['first'][:7] <= period <= window['last'][:7])
    offered = [node for node in soup.select('a[href]') if 'releveOpe.php' in node['href']]
    empty = [' '.join(node.get_text(' ', strip=True).split()) for node in soup.select('div.msg.texte1T7A')]
    replay.require(bool(offered) and not empty or not offered and empty == ["Vous n'avez pas effectué d'opération ce mois-ci."])
    state['notice_calendars'].add((account, period))
    if not offered:
        state['notice_empty_calendars'].add((account, period))
    if period == window['first'][:7]:
        return None
    functions = re.findall(r'function\s+MoisPrecedent\(tr,nc,month,year\)\s*\{([\s\S]*?)\n\}', raw.decode('cp1252'))
    expected = "if(month == 1) { --year; month=13; } document.location.href = 'avis-operes.php?tr='+tr+'&nc='+nc+'&month='+(month-1)+'&year='+year;"
    if not functions and not state['notice_navigation_verified']:
        # The real calendar references an external inert script. Retain this
        # calendar until that source-declared script has been captured.
        scripts = {source_url(url, node['src']) for node in soup.select('script[src]')
            if urljoin(url, node['src']) == ORIGIN + '/priv/scripts/avis-operes.js'}
        replay.require(len(scripts) == 1)
        state['notice_pending_calendars'][(account, period)] = (url, raw, parent)
        return None
    replay.require(not functions and state['notice_navigation_verified']
        or len(functions) == 1 and ''.join(functions[0].split()) == ''.join(expected.split()))
    previous = (datetime(int(year), int(month), 1) - timedelta(days=1))
    target = source_url(url, 'avis-operes.php?' + urlencode({'tr': 'RO', 'nc': nc, 'month': previous.month, 'year': previous.year}))
    return {'url': target, 'role': 'frame_document', 'sourceSha256': parent, 'account': account}


def available_source_accounts(options):
    """Project the observed selector onto references/wrappers only."""
    available = []
    for option in options:
        label = ' '.join(option.get_text(' ', strip=True).upper().split())
        kind = 'PEA-PME' if 'PEA-PME' in label or 'PEA PME' in label else 'PEA' if 'PEA' in label else None
        if kind:
            identity = option.get_text(' ', strip=True).split()[0]
            replay.require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63}', identity) and option.get('value'))
            available.append(identity + ' ' + kind)
    replay.require(available and len(set(available)) == len(available)
        and len({option.get('value') for option in options}) == len(options))
    return available


def discover(state, url, raw, role):
    """Derive exact document requests from inert HTML, preserving account identity."""
    soup = BeautifulSoup(raw, 'html.parser')
    parent = digest(raw)
    current = state['current']
    account = current.get('account') if current else None
    wanted = state['statement_periods'].get(account)
    notice_only = 'notice_window' in state
    if notice_only and url == ORIGIN + '/priv/scripts/avis-operes.js':
        functions = re.findall(r'function\s+MoisPrecedent\(tr,nc,month,year\)\s*\{([\s\S]*?)\n\}', raw.decode('cp1252'))
        expected = "if(month == 1) { --year; month=13; } document.location.href = 'avis-operes.php?tr='+tr+'&nc='+nc+'&month='+(month-1)+'&year='+year;"
        replay.require(len(functions) == 1 and ''.join(functions[0].split()) == ''.join(expected.split()))
        state['notice_navigation_verified'] = True
        for (pending_account, period), (calendar_url, body, sha) in list(state['notice_pending_calendars'].items()):
            replay.require(pending_account == account)
            previous = notice_calendar_previous(state, calendar_url, body, pending_account, sha)
            if previous is not None:
                state['queue'].insert(0, previous)
            del state['notice_pending_calendars'][(pending_account, period)]
        return
    selectors = soup.select('select#nc[name=nc]')
    if selectors:
        replay.require(len(selectors) == 1)
        select = selectors[0]
        options = select.find_all('option', recursive=False)
        if state.get('discovery_only'):
            state['discovered_accounts'] = available_source_accounts(options)
            state['queue'].clear()
            return
        if 'choose_account' in state and 'account_binding' not in state:
            available = available_source_accounts(options)
            chosen = state['choose_account'](available)
            if chosen is None:
                state['selection_source'] = (url, raw, role)
                return
            binding = source_account_binding(chosen)
            replay.require(binding['source_account_ref'] in available)
            state['account_binding'] = binding
            state['required_accounts'] = {binding['source_account_ref'].split(' ', 1)[1]}
            state.pop('selection_source', None)
        rows = {}
        identities = {}
        for option in options:
            label = ' '.join(option.get_text(' ', strip=True).upper().split())
            kind = 'PEA-PME' if 'PEA-PME' in label or 'PEA PME' in label else 'PEA' if 'PEA' in label else None
            if 'account_binding' in state:
                identity = option.get_text(' ', strip=True).split()[0] if option.get_text(' ', strip=True) else ''
                expected_id, expected_wrapper = state['account_binding']['source_account_ref'].split(' ', 1)
                if identity != expected_id:
                    continue
                replay.require(kind == expected_wrapper)
            if kind:
                replay.require(kind not in rows and option.get('value'))
                rows[kind] = option['value']
                identity = option.get_text(' ', strip=True).split()[0]
                replay.require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63}', identity))
                identities[kind] = identity
        replay.require(set(rows) == state['required_accounts'] and len(set(rows.values())) == len(rows))
        replay.require(len(set(identities.values())) == len(rows))
        if 'account_binding' in state:
            replay.require(all(sum(option.get('value') == value for option in options) == 1
                for value in rows.values()))
        if state['accounts']:
            replay.require(rows == state['accounts'] and identities == state['account_ids'])
        else:
            state['accounts'] = rows
            state['account_ids'] = identities
        form = select.find_parent('form')
        replay.require(form is not None and form.get('method', 'GET').upper() == 'GET')
        base = source_url(url, form.get('action') or url)
        fields = [(row['name'], row.get('value', '')) for row in form.select('input[name]')
            if row.get('type', '').lower() == 'hidden']
        replay.require(len(fields) <= 16 and not any(name == 'nc' for name, _ in fields))
        parsed = urlsplit(base)
        for kind, identifier in rows.items():
            params = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                if key not in {'nc', *(name for name, _ in fields)}]
            selected = urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                urlencode(params + fields + [('nc', identifier)]), ''))
            if (kind, selected, '') not in state['seen']:
                state['queue'].append({'url': selected, 'role': 'frame_document', 'sourceSha256': parent,
                    'account': kind, 'verify_account': True})
        if current and current.get('verify_account'):
            chosen = [row for row in options if row.has_attr('selected')]
            replay.require(len(chosen) == 1 and chosen[0].get('value') == rows[account])
            state['verified'].add(account)
    if role in ('monthly_statement', 'contract_note'):
        replay.require(not notice_only or role == 'contract_note')
        replay.require(account in state['verified'])
        title = 'RELEVE DE COMPTE' if role == 'monthly_statement' else "Avis d'Opération"
        replay.require(sum(node.get_text(' ', strip=True) == title for node in soup.select('strong')) == 1)
        headers = []
        for row in soup.select('tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'COMPTE N°':
                headers.append(cells[1].get_text(' ', strip=True))
        replay.require(len(headers) == 1 and headers[0].split()[:1] == [state['account_ids'][account]])
        params = dict(parse_qsl(urlsplit(url).query))
        period = None
        if role == 'monthly_statement' and re.fullmatch(r'[0-9]{8}', params.get('dt', '')):
            period = params['dt'][:6]
        if role == 'contract_note' and re.fullmatch(r'[0-9]{4}', params.get('year', '')) and re.fullmatch(r'(?:0?[1-9]|1[0-2])', params.get('month', '')):
            period = params['year'] + params['month'].zfill(2)
        replay.require(role != 'monthly_statement' or wanted is None or period == wanted)
        state['documents'].setdefault(account, {})[role] = {'sha256': parent, 'url': url, 'period': period}
        if notice_only:
            state['notice_documents'].add((account, url))
        return
    # Before selecting each wrapper, traverse only source-declared account frames.
    candidates = []
    for node in soup.select('iframe[src],frame[src],a[href],script[src]'):
        relative = node.get('src') if node.name in ('iframe', 'frame', 'script') else node.get('href')
        if not relative or relative.startswith('#'):
            continue
        if relative.startswith(('javascript:', 'ouvrePopup(')):
            match = re.fullmatch(r"(?:javascript:)?ouvrePopup\('([^']+)'(?:,[^)]*)?\);?", relative)
            if not match:
                replay.require(not (notice_only and account is not None and 'releveOpe.php' in relative))
                continue
            relative = match.group(1)
        try:
            target = source_url(url, relative)
        except RuntimeError:
            replay.require(not (notice_only and account is not None and 'releveOpe.php' in relative))
            continue
        path = urlsplit(target).path
        if notice_only and path in {'/fr/page/releves', '/priv/new/releves.php', '/priv/new/releveCompte.php'}:
            continue
        document_role = 'monthly_statement' if path.endswith('/releveCompte.php') else 'contract_note' if path.endswith('/releveOpe.php') else 'frame_document'
        if notice_only and document_role == 'contract_note':
            if account is None:
                continue
            pairs = parse_qsl(urlsplit(target).query, keep_blank_values=True)
            query = dict(pairs)
            replay.require(account in state['verified'] and set(query) == {'nc', 'type', 'year', 'month', 'day', 'trash'}
                and len(pairs) == len(query)
                and query['nc'] == state['accounts'][account] and query['type'] == 'RO' and query['trash'] == '/avis.pdf'
                and re.fullmatch(r'[0-9]{4}', query['year'])
                and all(re.fullmatch(r'[0-9]{1,2}', query[k]) for k in ('month', 'day')))
            try:
                note_day = datetime(int(query['year']), int(query['month']), int(query['day'])).date().isoformat()
            except ValueError:
                raise RuntimeError('SOURCE_REPLAY_REFUSED') from None
            if note_day > state['notice_window']['last'] or note_day[:7] < state['notice_window']['first'][:7]:
                continue
        if document_role == 'monthly_statement' and wanted is not None:
            date = dict(parse_qsl(urlsplit(target).query)).get('dt', '')
            if not re.fullmatch(r'[0-9]{8}', date) or date[:6] != wanted:
                continue
        if node.name == 'script' and path != '/priv/scripts/avis-operes.js':
            continue
        if account is None and node.name == 'a' and path not in {'/fr/page/releves', '/fr/page/avis-operes', '/fr/page/avis-d-operes'}:
            continue
        if document_role != 'frame_document' and (account is None
                or document_role == 'monthly_statement' and document_role in state['documents'].get(account, {})):
            continue
        candidates.append({'url': target, 'role': document_role, 'sourceSha256': parent, 'account': account})
        if notice_only and document_role == 'contract_note':
            state['notice_expected_documents'].add((account, target))
    # Finish the selected wrapper before switching the broker's account context.
    if notice_only:
        previous = notice_calendar_previous(state, url, raw, account, parent)
        if previous is not None:
            candidates.append(previous)
    elif account in state['verified'] and urlsplit(url).path == '/priv/new/releves.php':
        month_selects = soup.select('select[name=RlvCombo]')
        replay.require(len(month_selects) == 1)
        month_select = month_selects[0]
        form = month_select.find_parent('form')
        replay.require(form is not None and form.get('method', '').upper() == 'POST')
        target = source_url(url, form.get('action') or url)
        replay.require(urlsplit(target).path == '/priv/new/releves.php')
        target = urlunsplit((*urlsplit(target)[:3], '', ''))
        inputs = form.select('input[name]')
        replay.require(len(inputs) == 1 and inputs[0].get('name') == 'nc'
            and inputs[0].get('type', '').lower() == 'hidden'
            and inputs[0].get('value') == state['accounts'][account])
        options = month_select.find_all('option', recursive=False)
        replay.require(1 <= len(options) <= 21 and len({row.get('value') for row in options}) == len(options))
        desired_value = None
        if wanted is not None:
            months = {'janvier': '01', 'février': '02', 'mars': '03', 'avril': '04',
                'mai': '05', 'juin': '06', 'juillet': '07', 'août': '08', 'septembre': '09',
                'octobre': '10', 'novembre': '11', 'décembre': '12'}
            matches = []
            for option in options:
                label = ' '.join(option.get_text(' ', strip=True).casefold().split())
                parts = label.split(' ')
                if len(parts) == 2 and parts[0] in months and parts[1] + months[parts[0]] == wanted:
                    matches.append(option)
            replay.require(len(matches) == 1)
            desired_value = matches[0].get('value')
        for option in options:
            value = option.get('value')
            replay.require(re.fullmatch(r'(?:[1-9]|1[0-9]|2[01])', value or ''))
            if not option.has_attr('selected') and (wanted is None or value == desired_value):
                candidates.append({'url': target, 'role': 'frame_document', 'sourceSha256': parent,
                    'account': account, 'verify_account': True, 'method': 'POST',
                    'fields': {'nc': state['accounts'][account], 'RlvCombo': value}})
    state['queue'][0:0] = candidates


def notice_coverage(state):
    """Summarize observed calendars and offered notices, without personal fields."""
    first = datetime.strptime(state['notice_window']['first'][:7], '%Y-%m')
    last = state['notice_window']['last'][:7]
    periods = []
    while first.strftime('%Y-%m') <= last:
        periods.append(first.strftime('%Y-%m'))
        first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    observed = {account: sorted(period for wrapper, period in state['notice_calendars'] if wrapper == account)
        for account in sorted(state['required_accounts'])}
    empty = {account: sorted(period for wrapper, period in state['notice_empty_calendars'] if wrapper == account)
        for account in observed}
    missing = {account: sorted(set(periods) - set(months)) for account, months in observed.items()}
    return {'window': {'first_day': state['notice_window']['first'], 'last_day': state['notice_window']['last'], 'days': 90},
        'expected_months': periods, 'observed_months': observed, 'empty_months': empty, 'missing_months': missing,
        'expected_contract_notes': len(state['notice_expected_documents']),
        'captured_contract_notes': len(state['notice_documents']),
        'complete': state['verified'] == state['required_accounts'] and not state['notice_pending_calendars']
            and not any(missing.values()) and state['notice_expected_documents'] == state['notice_documents']}


def next_document(state):
    if state.get('discovery_only') and 'discovered_accounts' in state:
        return {'done': True, 'accounts_verified': True, 'account_discovery_verified': True,
            'documents': {'complete': True, 'monthly_statements': 0, 'contract_notes': 0}}
    if 'selection_source' in state:
        discover(state, *state['selection_source'])
        if 'selection_source' in state:
            return {'needs_selection': True, 'accounts_verified': False}
    while state['queue']:
        row = state['queue'].pop(0)
        key = (row['account'], row['url'], json.dumps(row.get('fields', ''), sort_keys=True) if row.get('fields') else '')
        if key in state['seen'] or row['role'] == 'monthly_statement' and row['role'] in state['documents'].get(row['account'], {}):
            continue
        if row.get('method') == 'POST' and 'monthly_statement' in state['documents'].get(row['account'], {}):
            continue
        state['seen'].add(key)
        state['current'] = row
        return {'accounts_verified': state['verified'] == state['required_accounts'],
            **({'configured_account_verified': state['verified'] == state['required_accounts']}
                if 'account_binding' in state else {}),
            'document': {key: row[key] for key in ('url', 'role', 'sourceSha256', 'method', 'fields') if key in row}}
    replay.require(state['verified'] == state['required_accounts'])
    if 'notice_window' in state:
        complete = notice_coverage(state)['complete']
        return {'done': True, 'accounts_verified': True,
            **({'configured_account_verified': True} if 'account_binding' in state else {}),
            'documents': {'complete': complete,
            'monthly_statements': 0, 'contract_notes': len(state['notice_documents'])}}
    complete = all(set(state['documents'].get(kind, {})) == {'monthly_statement', 'contract_note'}
        and state['documents'][kind]['monthly_statement'].get('period') is not None
        and state['documents'][kind]['monthly_statement'].get('period') == state['documents'][kind]['contract_note'].get('period')
        for kind in state['verified'])
    return {'done': True, 'accounts_verified': True, 'documents': {'complete': complete,
        'monthly_statements': sum('monthly_statement' in value for value in state['documents'].values()),
        'contract_notes': sum('contract_note' in value for value in state['documents'].values())}}


def validate_selection(state, captured, choice):
    replay.require(set(choice) == {'url', 'role', 'sourceSha256', 'account'}
        and choice['sourceSha256'] in captured and choice['account'] in state['verified']
        and choice['role'] in ('frame_document', 'monthly_statement', 'contract_note'))
    source_url(choice['url'], choice['url'])
    replay.require((choice['account'], choice['url'], '') not in state['seen']
        and (choice['role'] != 'monthly_statement' or choice['role'] not in state['documents'].get(choice['account'], {})))
    selected = dict(parse_qsl(urlsplit(choice['url']).query)).get('nc')
    current_account = state['current'].get('account')
    replay.require(selected is None or selected == state['accounts'][choice['account']])
    if choice['account'] != current_account:
        replay.require(selected is not None)
    return {**choice, **({'verify_account': True} if selected is not None else {})}


def source_pins(root, inventory):
    reference = inventory['evidence']['public_form_bootstrap']
    saved = json.loads(replay.private._read_bytes(replay.contained(root, reference['path'])))
    replay.require(saved['credentials_read'] is False and saved['authentication_requests'] == 0)
    prior = replay.private._read(replay.contained(root, inventory['evidence']['public_login']['path']))
    old_raw = replay.private._read_bytes(root / 'inputs/source-observations/public-login-1/stdout.private.json')
    replay.require(digest(old_raw) == prior['stdout_sha256'])
    old = json.loads(old_raw)
    assets = [{'url': row['url'], 'resourceType': row['resource_type']} for row in old['requests']
        if not row['continued'] and row['method'] == 'GET' and row['resource_type'] == 'Stylesheet']
    replay.require(len(assets) == 2)
    return {'app_sha256': inventory['evidence']['auth_app_body']['sha256'], 'assets': assets}


def qualify(root, lab, inventory, public_only=False, notice_as_of=None, account_config=None):
    replay.require(type(public_only) is bool)
    account = None
    account_config_sha256 = None
    if account_config is not None:
        replay.require(not public_only and notice_as_of is not None)
        raw = replay.private._read_bytes(replay.contained(root, account_config))
        config = replay.private._decode(raw)
        replay.require(isinstance(config, dict) and type(config.get('schema_version')) is int
            and config['schema_version'] == 1 and config.get('source_mode') == 'notices')
        account = source_account_binding(config.get('account'))
        account_config_sha256 = digest(raw)
    preference_path = root / 'inputs/source-observations/statement-preference.yaml'
    preference = replay.private._read(preference_path) if notice_as_of is None and preference_path.exists() else {
        'schema_version': 1, 'statement_periods': {}}
    replay.require(isinstance(preference, dict) and set(preference) == {'schema_version', 'statement_periods'}
        and type(preference['schema_version']) is int and preference['schema_version'] == 1)
    state = planner(preference['statement_periods'], notice_as_of=notice_as_of, account=account)
    verified = inventory['_verified_helpers']
    q = replay.helper(lab, 'qualify', verified)
    vault = replay.helper(lab, 'attest', verified).attest()
    broker = replay.helper(lab, 'broker-attest', verified).attest()
    identifier = vault['containers']['bitwarden-cli']['id']
    browser_id = broker['containers']['browser']['id']
    replay.require(q.owned(broker, 'container', browser_id)['HostConfig']['Init'] is True)
    replay.require(public_only or subprocess.check_output(['git', '-C', str(CODE_ROOT), 'status', '--porcelain']) == b'')
    head = subprocess.check_output(['git', '-C', str(CODE_ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    binding = json.loads(replay.private._read_bytes(replay.contained(root, inventory['evidence']['vault_cli_binding']['path'])))
    replay.require(binding['containerId'] == identifier)
    selected = replay.private._read(replay.contained(root, inventory['evidence']['vault_alias_inspection']['path']))['selected']
    contract_path = replay.contained(root, inventory['source_contract'])
    configuration = {**binding['configuration'], 'schema_version': 4, 'binding': {
        'name': 'boursedirect.fr', **{key: selected[key] for key in ('itemId', 'principalHash', 'uri', 'uriAliasesSha256')},
        'accountConfig': {'path': str(contract_path), 'sha256': digest(contract_path.read_bytes())}}}
    output = root / ('inputs/source-observations/qualification-' + uuid.uuid4().hex)
    output.mkdir(mode=0o700)
    intent = {'schema_version': 1, 'owner': 'infra-4g8u.70', 'source_commit': head,
        'state': 'reserved', 'public_only': public_only,
        'statement_periods': state['statement_periods'],
        'source_contract_sha256': configuration['binding']['accountConfig']['sha256'],
        **({'account_binding': account, 'import_account_config_sha256': account_config_sha256}
            if account is not None else {})}
    replay.private._publish(output / 'attempt.yaml', intent, exclusive=True)
    lease = lab / 'vault-operation.lock'
    lease.mkdir(mode=0o700)
    q.durable._sync_directory(lease.parent)
    process = None
    passed = False
    document = None
    sequence = 0
    consumed = set()
    captured = {}
    awaiting_selection = False
    phase = 'source_delivery'
    try:
        # Reuse the existing owned-browser source delivery; no new image or service.
        q.checked(['docker', 'exec', '-u', '1000:1000', browser_id,
            'mkdir', '-p', '/home/fixture/proof/lab'])
        files = ['collector/lab/source-browser-pipe.mjs', 'collector/lab/browser-sandbox-proof.mjs', 'collector/capability-pipe.mjs']
        hashes = {}
        for name in files:
            raw = (CODE_ROOT / name).read_bytes()
            target = '/home/fixture/proof/' + name.removeprefix('collector/')
            q.checked(['docker', 'exec', '-i', '-u', '1000:1000', browser_id,
                'sh', '-c', 'umask 077; cat > ' + target], raw)
            replay.require(q.checked(['docker', 'exec', '-u', '1000:1000', browser_id,
                'sha256sum', target]).decode().split()[0] == digest(raw))
            hashes[name] = digest(raw)
        replay.private._publish(output / 'attempt.yaml', {**intent, 'source_hashes': hashes, 'state': 'source_delivered'})
        replay.live_status(lab, verified)
        phase = 'worker_start'
        process = subprocess.Popen(['/usr/bin/node', str(CODE_ROOT / 'collector/lab/source-qualification-command.mjs')],
            cwd=CODE_ROOT, env={'PATH': '/usr/bin:/bin', 'HOME': str(Path.home())},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        write_frame(process, {'destination': binding['destination'], 'browserId': browser_id,
            'browserProxy': 'http://' + broker['proxy_ip'] + ':8080', 'sourcePin': source_pins(root, inventory),
            'vault': {'configuration': configuration, 'containerId': identifier, 'egressProxy': binding['egressProxy']},
            'publicOnly': public_only, 'credentials': None if public_only else replay.helper(lab, 'provision', verified).initial_environment()})
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, 'stdout')
        selector.register(process.stderr, selectors.EVENT_READ, 'stderr')
        deadline = time.monotonic() + 620
        try:
            for _ in range(1024):
                row = read_frame(process, selector, b'', deadline)
                action = row.get('action')
                phase = action if action in {'attest_vault', 'stop_vault', 'attest_browser', 'stop_browser',
                    'reserve_enrollment', 'retain', 'consume_read', 'document_begin', 'document_chunk', 'document_end',
                    'next_document', 'complete', 'refused'} else 'invalid_worker_frame'
                replay.require(action in {'attest_vault', 'stop_vault', 'attest_browser', 'stop_browser',
                    'reserve_enrollment', 'retain', 'consume_read', 'document_begin', 'document_chunk', 'document_end',
                    'next_document', 'complete'})
                result = True
                if action == 'attest_vault':
                    replay.require(row['containerId'] == identifier and row['pin'] == configuration['cli'])
                    replay.require(replay.helper(lab, 'attest', verified).attest()['containers']['bitwarden-cli']['id'] == identifier)
                elif action == 'stop_vault':
                    replay.require(row['containerId'] == identifier)
                    result = stop_owned_cli(q, lab, identifier)
                elif action == 'attest_browser':
                    replay.require(replay.helper(lab, 'broker-attest', verified).attest()['containers']['browser']['id'] == browser_id)
                elif action == 'stop_browser':
                    replay.helper(lab, 'broker-stop', verified).stop()
                elif action == 'reserve_enrollment':
                    replay.require(row['principal'] == selected['principalHash']
                        and digest(contract_path.read_bytes()) == configuration['binding']['accountConfig']['sha256'])
                    location = Path.home() / '.local/state/ghostfolio-boursedirect-sync/auth' / row['principal']
                    result = {'enroll': not location.exists()}
                    replay.private._publish(output / 'enrollment-intent.yaml', {
                        'principal_sha256': row['principal'], 'binding_sha256': digest(json.dumps(configuration, sort_keys=True).encode()),
                        'canonical_namespace': True, 'new_enrollment': result['enroll']}, exclusive=True)
                elif action == 'retain':
                    sequence += 1
                    replay.private._publish(output / ('request-' + str(sequence) + '.yaml'), row['observation'], exclusive=True)
                elif action == 'consume_read':
                    grant = row['grant']
                    replay.require(grant['grant'] not in consumed)
                    replay.private._publish(output / ('grant-' + str(len(consumed)) + '.yaml'), grant, exclusive=True)
                    consumed.add(grant['grant'])
                elif action == 'document_begin':
                    replay.require(document is None)
                    expected = state['current']
                    replay.require(expected is None or (row['url'] == expected['url'] and row['role'] == expected['role']))
                    source_url(row['url'], row['url'])
                    document = {**row, 'body': bytearray()}
                elif action == 'document_chunk':
                    replay.require(document is not None)
                    raw = base64.b64decode(row['body'], validate=True)
                    document['body'].extend(raw)
                    replay.require(len(document['body']) <= 1048576)
                elif action == 'document_end':
                    replay.require(document is not None)
                    state['captures'] += 1
                    raw = bytes(document.pop('body'))
                    path = output / ('document-' + str(state['captures']) + '.html')
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                    with os.fdopen(fd, 'wb') as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    q.durable._sync_directory(output)
                    replay.private._publish(output / ('document-' + str(state['captures']) + '.yaml'), {
                        **document, 'sha256': digest(raw), 'path': path.name, 'original_response_bytes': False,
                        'account_wrapper': state['current'].get('account') if state['current'] else None,
                        'broker_account_id': state['account_ids'].get(state['current'].get('account'))
                            if state['current'] else None}, exclusive=True)
                    captured[digest(raw)] = {key: document[key] for key in ('url', 'role')}
                    discover(state, document['url'], raw, document['role'])
                    document = None
                elif action == 'next_document':
                    if awaiting_selection:
                        finish = output / 'finish-acquisition.yaml'
                        if finish.exists():
                            replay.require(replay.private._read(finish) == {'stop_after_retained_absence': True}
                                and state['verified'] == state['required_accounts'])
                            write_frame(process, {'result': next_document(state)})
                            continue
                        selection = output / 'selection.yaml'
                        until = min(deadline, time.monotonic() + 15)
                        while not selection.exists() and time.monotonic() < until:
                            time.sleep(0.25)
                        replay.require(time.monotonic() < deadline)
                        if not selection.exists():
                            write_frame(process, {'result': {'accounts_verified': True, 'needs_selection': True,
                                **({'configured_account_verified': True} if 'account_binding' in state else {})}})
                            continue
                        choice = validate_selection(state, captured, replay.private._read(selection))
                        selection.rename(output / ('selection-used-' + uuid.uuid4().hex + '.yaml'))
                        q.durable._sync_directory(output)
                        state['queue'].append(choice)
                        awaiting_selection = False
                    result = next_document(state)
                    if result.get('done') and not result['documents']['complete']:
                        replay.private._publish(output / 'read-selection-needed.yaml', {
                            'accounts': state['accounts'], 'account_ids': state['account_ids'],
                            'verified_wrappers': sorted(state['verified']),
                            'documents': state['documents'], 'captured_sources': captured,
                            'current_account': state['current'].get('account')}, exclusive=False)
                        print(json.dumps({'code': 'SOURCE_READ_SELECTION_REQUIRED', 'accounts': len(state['required_accounts']),
                            **result['documents']}), flush=True)
                        result = {'accounts_verified': True, 'needs_selection': True,
                            **({'configured_account_verified': True} if 'account_binding' in state else {})}
                        awaiting_selection = True
                elif action == 'complete':
                    replay.require(row['accounts_verified'] is True and row['session_logged_out'] is True
                        and row['browser_exit_verified'] is True and row['totp_requests'] == 1)
                    replay.require(process.wait(timeout=15) == 0)
                    replay.require(process.stdout.read(1) == b'' and process.stderr.read(1) == b'')
                    replay.require(row['documents'] == next_document(state)['documents'])
                    replay.private._publish(output / 'qualification.yaml', {**intent, **row,
                        'state': 'owned_session_closed', 'captures': state['captures'],
                        'accounts': state['accounts'], 'account_ids': state['account_ids'],
                        'verified_wrappers': sorted(state['verified']),
                        **({'notice_window': state['notice_window']} if 'notice_window' in state else {})}, exclusive=True)
                    passed = True
                    return {'code': 'SOURCE_QUALIFICATION_COMPLETED' if row['documents']['complete'] else
                        'SOURCE_DOCUMENT_ACQUISITION_INCOMPLETE', 'accounts': len(state['required_accounts']), **row['documents']}
                write_frame(process, {'result': result})
            raise RuntimeError('SOURCE_REPLAY_REFUSED')
        finally:
            selector.close()
    finally:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        if not passed:
            browser_stopped = cli_stopped = False
            try:
                replay.helper(lab, 'broker-stop', verified).stop()
                browser_stopped = True
            except Exception:
                pass
            try:
                cli_stopped = True if public_only else stop_owned_cli(q, lab, identifier)
            except Exception:
                pass
            cleanup = browser_stopped and cli_stopped
            replay.private._publish(output / 'attempt.yaml', {**intent, 'state': 'refused_preserved',
                'failed_phase': phase, 'exact_owned_cleanup_verified': cleanup,
                'browser_stopped_owned': browser_stopped, 'cli_stopped_owned': None if public_only else cli_stopped,
                'cli_unused': public_only,
                'accounts': state['accounts'], 'account_ids': state['account_ids'],
                'verified_wrappers': sorted(state['verified']),
                'documents': state['documents'], 'captures': state['captures']})
        if passed or cleanup:
            lease.rmdir()
            q.durable._sync_directory(lease.parent)

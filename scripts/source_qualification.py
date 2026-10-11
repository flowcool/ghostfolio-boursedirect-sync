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


def planner():
    return {'queue': [], 'seen': set(), 'accounts': {}, 'account_ids': {}, 'verified': set(),
        'documents': {}, 'current': None, 'captures': 0}


def discover(state, url, raw, role):
    """Derive exact GETs from inert saved HTML, maintaining the selected account."""
    soup = BeautifulSoup(raw, 'html.parser')
    parent = digest(raw)
    current = state['current']
    account = current.get('account') if current else None
    selectors = soup.select('select#nc[name=nc]')
    if selectors:
        replay.require(len(selectors) == 1)
        select = selectors[0]
        options = select.find_all('option', recursive=False)
        rows = {}
        identities = {}
        for option in options:
            label = ' '.join(option.get_text(' ', strip=True).upper().split())
            kind = 'PEA-PME' if 'PEA-PME' in label or 'PEA PME' in label else 'PEA' if 'PEA' in label else None
            if kind:
                replay.require(kind not in rows and option.get('value'))
                rows[kind] = option['value']
                identity = option.get_text(' ', strip=True).split()[0]
                replay.require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63}', identity))
                identities[kind] = identity
        replay.require(set(rows) == {'PEA', 'PEA-PME'} and len(set(rows.values())) == 2)
        replay.require(len(set(identities.values())) == 2)
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
        replay.require(account in state['verified'])
        title = 'RELEVE DE COMPTE' if role == 'monthly_statement' else "Avis d'Opération"
        replay.require(sum(node.get_text(' ', strip=True) == title for node in soup.select('strong')) == 1)
        headers = []
        for row in soup.select('tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'COMPTE N°':
                headers.append(cells[1].get_text(' ', strip=True))
        replay.require(len(headers) == 1 and re.search(r'(?<![A-Za-z0-9_-])' + re.escape(state['account_ids'][account]) + r'(?![A-Za-z0-9_-])', headers[0]))
        params = dict(parse_qsl(urlsplit(url).query))
        period = None
        if role == 'monthly_statement' and re.fullmatch(r'[0-9]{8}', params.get('dt', '')):
            period = params['dt'][:6]
        if role == 'contract_note' and re.fullmatch(r'[0-9]{4}', params.get('year', '')) and re.fullmatch(r'(?:0?[1-9]|1[0-2])', params.get('month', '')):
            period = params['year'] + params['month'].zfill(2)
        state['documents'].setdefault(account, {})[role] = {'sha256': parent, 'url': url, 'period': period}
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
                continue
            relative = match.group(1)
        try:
            target = source_url(url, relative)
        except RuntimeError:
            continue
        path = urlsplit(target).path
        document_role = 'monthly_statement' if path.endswith('/releveCompte.php') else 'contract_note' if path.endswith('/releveOpe.php') else 'frame_document'
        if node.name == 'script' and path != '/priv/scripts/avis-operes.js':
            continue
        if account is None and node.name == 'a' and path not in {'/fr/page/releves', '/fr/page/avis-operes', '/fr/page/avis-d-operes'}:
            continue
        if document_role != 'frame_document' and (account is None
                or document_role == 'monthly_statement' and document_role in state['documents'].get(account, {})):
            continue
        candidates.append({'url': target, 'role': document_role, 'sourceSha256': parent, 'account': account})
    # Finish the selected wrapper before switching the broker's account context.
    if account in state['verified'] and urlsplit(url).path == '/priv/new/releves.php':
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
        for option in options:
            value = option.get('value')
            replay.require(re.fullmatch(r'(?:[1-9]|1[0-9]|2[01])', value or ''))
            if not option.has_attr('selected'):
                candidates.append({'url': target, 'role': 'frame_document', 'sourceSha256': parent,
                    'account': account, 'verify_account': True, 'method': 'POST',
                    'fields': {'nc': state['accounts'][account], 'RlvCombo': value}})
    state['queue'][0:0] = candidates


def next_document(state):
    while state['queue']:
        row = state['queue'].pop(0)
        key = (row['account'], row['url'], json.dumps(row.get('fields', ''), sort_keys=True) if row.get('fields') else '')
        if key in state['seen'] or row['role'] == 'monthly_statement' and row['role'] in state['documents'].get(row['account'], {}):
            continue
        if row.get('method') == 'POST' and 'monthly_statement' in state['documents'].get(row['account'], {}):
            continue
        state['seen'].add(key)
        state['current'] = row
        return {'accounts_verified': state['verified'] == {'PEA', 'PEA-PME'},
            'document': {key: row[key] for key in ('url', 'role', 'sourceSha256', 'method', 'fields') if key in row}}
    replay.require(state['verified'] == {'PEA', 'PEA-PME'})
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


def qualify(root, lab, inventory, public_only=False):
    replay.require(type(public_only) is bool)
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
        'state': 'reserved', 'public_only': public_only, 'source_contract_sha256': configuration['binding']['accountConfig']['sha256']}
    replay.private._publish(output / 'attempt.yaml', intent, exclusive=True)
    lease = lab / 'vault-operation.lock'
    lease.mkdir(mode=0o700)
    q.durable._sync_directory(lease.parent)
    process = None
    passed = False
    state = planner()
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
                    replay.require(not location.exists())
                    replay.private._publish(output / 'enrollment-intent.yaml', {
                        'principal_sha256': row['principal'], 'binding_sha256': digest(json.dumps(configuration, sort_keys=True).encode()),
                        'canonical_namespace': True}, exclusive=True)
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
                                and state['verified'] == {'PEA', 'PEA-PME'})
                            write_frame(process, {'result': next_document(state)})
                            continue
                        selection = output / 'selection.yaml'
                        until = min(deadline, time.monotonic() + 15)
                        while not selection.exists() and time.monotonic() < until:
                            time.sleep(0.25)
                        replay.require(time.monotonic() < deadline)
                        if not selection.exists():
                            write_frame(process, {'result': {'accounts_verified': True, 'needs_selection': True}})
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
                        print(json.dumps({'code': 'SOURCE_READ_SELECTION_REQUIRED', 'accounts': 2,
                            **result['documents']}), flush=True)
                        result = {'accounts_verified': True, 'needs_selection': True}
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
                        'verified_wrappers': sorted(state['verified'])}, exclusive=True)
                    passed = True
                    return {'code': 'SOURCE_QUALIFICATION_COMPLETED' if row['documents']['complete'] else
                        'SOURCE_DOCUMENT_ACQUISITION_INCOMPLETE', 'accounts': 2, **row['documents']}
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

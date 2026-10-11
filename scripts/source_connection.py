#!/usr/bin/env python3
"""Resume the dedicated acquisition lab from private saved evidence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import native_cdp_allocation as private


def require(value, code='SOURCE_REPLAY_REFUSED'):
    if not value:
        raise RuntimeError(code)


def contained(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute())
    path = root / name
    require(root.resolve() in path.resolve().parents and not path.is_symlink())
    return path


def inspect_saved(root, lab):
    require((lab / 'replay.yaml').is_file(), 'SOURCE_REPLAY_INVENTORY_MISSING')
    inventory = private._read(lab / 'replay.yaml')
    require(inventory['schema_version'] == 1)
    require(set(inventory['trusted_helpers']) == {'qualify.py', 'attest.py', 'broker-attest.py',
        'broker-stop.py', 'stop.py', 'provision.py'})
    evidence = {}
    for name, reference in inventory['evidence'].items():
        path = contained(root, reference['path'])
        require(path.is_file() and path.stat().st_mode & 0o077 == 0, 'SOURCE_REPLAY_EVIDENCE_MISSING_OR_PUBLIC')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == reference['sha256'], 'SOURCE_REPLAY_EVIDENCE_CHANGED')
        if name != 'auth_app_body':
            evidence[name] = private._read(path)
    for name, expected in inventory['trusted_helpers'].items():
        path = contained(lab / 'host', name)
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'SOURCE_REPLAY_HELPER_CHANGED')
    contract = private._read(contained(root, inventory['source_contract']))
    auth = evidence['historical_authentication_manifest']['authentication']
    journal = evidence['historical_authentication_journal']['accounts']
    require(journal and all(row['stage'] == 'AUTHENTICATED' for row in journal.values()))
    require(auth['password_submissions'] == auth['totp_submissions'] == 1 and not auth['credentials_persisted'])
    vault = evidence['vault_inspection']
    require(all(vault[key] is True for key in ('exact_name_unique', 'broker_uri_verified',
        'credential_fields_verified', 'totp_profile_verified')))
    source = evidence['auth_app_source']
    require(source['http_status'] == 200 and not source['credentials_read']
        and source['authentication_requests'] == 0 and source['owned_browser_exit_verified'])
    idle = evidence['browser_idle']
    require(idle['browser_init'] and all(idle['counts'][key] == 0 for key in
        ('live_chrome', 'zombies', 'unexpected_proc_errors')))
    required = ('password_submit', 'app_method', 'otp_submit', 'frame_document', 'monthly_statement', 'contract_note')
    missing = [name for name in required if contract['roles'].get(name, {}).get('enabled') is not True]
    accounts = contract.get('expected_account_inventory', {}).get('accounts', [])
    return inventory, {
        'code': 'SOURCE_REPLAY_EVIDENCE_VERIFIED',
        'historical_authentication_confirmed': True,
        'vault_inspection_reused': True,
        'public_auth_app_source_reused': True,
        'saved_browser_cleanup_verified': True,
        'current_collector_authentication_ready': False,
        'missing_request_roles': missing,
        'declared_accounts': len(accounts),
        'verified_account_bindings': sum(row.get('verified') is True for row in accounts),
    }


def helper(lab, name):
    spec = importlib.util.spec_from_file_location(name, lab / 'host' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_status(lab):
    sys.path.insert(0, str(lab / 'host'))
    vault = helper(lab, 'attest').attest()
    broker = helper(lab, 'broker-attest').attest()
    import qualify as q
    browser = q.owned(broker, 'container', broker['containers']['browser']['id'])
    require(browser['HostConfig']['Init'] is True)
    return {'code': 'SOURCE_LAB_ATTESTED', 'containers': len(vault['containers']) + len(broker['containers']),
        'browser_init': True, 'new_vault_sessions': 0, 'new_broker_requests': 0}


def restart_browser(lab):
    sys.path.insert(0, str(lab / 'host'))
    import qualify as q
    path = lab / 'host' / 'broker-runtime.yaml'
    broker = private._read(path)
    require(broker['state'] == 'browser_stopped_owned')
    worker = broker['containers']['browser']
    details = q.owned(broker, 'container', worker['id'])
    require(not details['State']['Running'] and details['HostConfig']['Init'] is True)
    proxy = q.owned(broker, 'container', broker['containers']['broker-egress']['id'])
    require(proxy['State']['Running'] and proxy['State']['Pid'] == broker['containers']['broker-egress']['pid'])
    private._publish(lab / ('browser-before-restart-' + uuid.uuid4().hex + '.yaml'), broker, exclusive=True)
    try:
        broker['state'] = 'browser_start_intent'
        private._publish(path, broker)
        q.docker(['start', worker['id']])
        details = q.owned(broker, 'container', worker['id'])
        require(details['State']['Running'])
        worker.update(state='started_unqualified', pid=details['State']['Pid'])
        worker['netns'] = q.checked(['sudo', '-n', 'readlink', '/proc/' + str(worker['pid']) + '/ns/net']).decode().strip()
        broker['state'] = 'browser_acl_intent'
        private._publish(path, broker)
        rules = [('/usr/sbin/iptables', ['-P', 'OUTPUT', 'DROP']),
            ('/usr/sbin/ip6tables', ['-P', 'OUTPUT', 'DROP']),
            ('/usr/sbin/iptables', ['-F', 'OUTPUT']), ('/usr/sbin/ip6tables', ['-F', 'OUTPUT']),
            ('/usr/sbin/iptables', ['-A', 'OUTPUT', '-p', 'tcp', '-d', broker['proxy_ip'], '--dport', '8080', '-j', 'ACCEPT'])]
        for executable, arguments in rules:
            details = q.owned(broker, 'container', worker['id'])
            require(details['State']['Running'] and details['State']['Pid'] == worker['pid'])
            require(q.checked(['sudo', '-n', 'readlink', '/proc/' + str(worker['pid']) + '/ns/net']).decode().strip() == worker['netns'])
            q.checked(['sudo', '-n', 'nsenter', '-t', str(worker['pid']), '-n', executable] + arguments)
        worker['state'] = 'started'
        broker['state'] = 'routes_qualified'
        private._publish(path, broker)
        live_status(lab)
    except Exception:
        helper(lab, 'broker-stop').stop()
        raise
    return {'code': 'SOURCE_BROWSER_RESTARTED_ATTESTED', 'new_broker_requests': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'status', 'restart-browser', 'stop-browser', 'connect'))
    parser.add_argument('--lab-root', default='inputs/lab')
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        lab = contained(root, arguments.lab_root)
        _, report = inspect_saved(root, lab)
        if arguments.action == 'connect':
            report['code'] = 'SOURCE_AUTHENTICATED_REPLAY_NOT_QUALIFIED'
            print(json.dumps(report))
            return 2
        if arguments.action == 'status':
            report['live'] = live_status(lab)
        elif arguments.action == 'restart-browser':
            report['live'] = restart_browser(lab)
        elif arguments.action == 'stop-browser':
            sys.path.insert(0, str(lab / 'host'))
            helper(lab, 'broker-stop').stop()
        print(json.dumps(report))
        return 0
    except Exception as error:
        allowed = {'SOURCE_REPLAY_INVENTORY_MISSING', 'SOURCE_REPLAY_EVIDENCE_MISSING_OR_PUBLIC',
            'SOURCE_REPLAY_EVIDENCE_CHANGED', 'SOURCE_REPLAY_HELPER_CHANGED'}
        code = str(error) if isinstance(error, RuntimeError) and str(error) in allowed else 'SOURCE_REPLAY_REFUSED'
        print(json.dumps({'code': code, 'action': arguments.action}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

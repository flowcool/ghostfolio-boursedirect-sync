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
    core_helpers = {'qualify.py', 'attest.py', 'broker-attest.py', 'broker-stop.py', 'stop.py', 'provision.py'}
    require(core_helpers <= set(inventory['trusted_helpers']) <= core_helpers | {'public-form.py'})
    evidence = {}
    for name, reference in inventory['evidence'].items():
        path = contained(root, reference['path'])
        require(path.is_file(), 'SOURCE_REPLAY_EVIDENCE_MISSING_OR_PUBLIC')
        raw = private._read_bytes(path, max_bytes=1048576 if name == 'auth_app_body' else private._LIMIT)
        require(hashlib.sha256(raw).hexdigest() == reference['sha256'], 'SOURCE_REPLAY_EVIDENCE_CHANGED')
        if name != 'auth_app_body':
            evidence[name] = private._decode(raw)
    verified_helpers = {}
    for name, expected in inventory['trusted_helpers'].items():
        path = contained(lab / 'host', name)
        raw = private._read_bytes(path)
        require(hashlib.sha256(raw).hexdigest() == expected, 'SOURCE_REPLAY_HELPER_CHANGED')
        verified_helpers[name] = raw
    inventory['_verified_helpers'] = verified_helpers
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
    required = ('preliminary_verify', 'password_submit', 'app_method', 'otp_submit',
        'password_finalize', 'frame_document', 'monthly_statement', 'contract_note')
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


def helper(lab, name, verified):
    if name != 'qualify':
        helper(lab, 'qualify', verified)
    spec = importlib.util.spec_from_file_location(name, lab / 'host' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(verified[name + '.py'], str(module.__file__), 'exec'), module.__dict__)
    return module


def live_status(lab, verified):
    sys.path.insert(0, str(lab / 'host'))
    vault = helper(lab, 'attest', verified).attest()
    broker = helper(lab, 'broker-attest', verified).attest()
    import qualify as q
    browser = q.owned(broker, 'container', broker['containers']['browser']['id'])
    require(browser['HostConfig']['Init'] is True)
    return {'code': 'SOURCE_LAB_ATTESTED', 'containers': len(vault['containers']) + len(broker['containers']),
        'browser_init': True, 'new_vault_sessions': 0, 'new_broker_requests': 0}


def restart_browser(lab, verified):
    sys.path.insert(0, str(lab / 'host'))
    helper(lab, 'qualify', verified)
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
        live_status(lab, verified)
    except Exception:
        helper(lab, 'broker-stop', verified).stop()
        raise
    return {'code': 'SOURCE_BROWSER_RESTARTED_ATTESTED', 'new_broker_requests': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'status', 'restart-browser', 'stop-browser', 'connect', 'observe-public-form', 'characterize-password-request', 'inspect-vault-aliases', 'qualify-connection'))
    parser.add_argument('--lab-root', default='inputs/lab')
    parser.add_argument('--notice-window-as-of', help='Explicit notice-only90day broker calendar clock for qualify-connection')
    parser.add_argument('--account-config', help='Private notice configuration containing the explicit source and destination account binding')
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        lab = contained(root, arguments.lab_root)
        inventory, report = inspect_saved(root, lab)
        require(arguments.notice_window_as_of is None or arguments.action == 'qualify-connection')
        require(arguments.account_config is None or
            arguments.action == 'qualify-connection' and arguments.notice_window_as_of is not None)
        verified = inventory['_verified_helpers']
        if arguments.action == 'connect':
            report['code'] = 'SOURCE_AUTHENTICATED_REPLAY_NOT_QUALIFIED'
            print(json.dumps(report))
            return 2
        if arguments.action == 'qualify-connection':
            import source_qualification
            report['live'] = source_qualification.qualify(root, lab, inventory,
                notice_as_of=arguments.notice_window_as_of, account_config=arguments.account_config)
        elif arguments.action == 'status':
            report['live'] = live_status(lab, verified)
        elif arguments.action == 'inspect-vault-aliases':
            require('vault_cli_binding' in inventory['evidence'])
            import source_vault_inspection
            report['live'] = source_vault_inspection.inspect(root, lab, inventory)
        elif arguments.action in ('observe-public-form', 'characterize-password-request'):
            require('public-form.py' in verified)
            probe = arguments.action == 'characterize-password-request'
            live_status(lab, verified)
            adapter = helper(lab, 'public-form', verified)
            report['live'] = adapter.run(probe=True) if probe else adapter.run()
        elif arguments.action == 'restart-browser':
            report['live'] = restart_browser(lab, verified)
        elif arguments.action == 'stop-browser':
            sys.path.insert(0, str(lab / 'host'))
            helper(lab, 'broker-stop', verified).stop()
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

"""Offline replay of the real selector and restart/serialization boundaries."""
import os
from pathlib import Path
import sys
import uuid

import pytest

import boursedirect_to_ghostfolio as connector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import community_connect as acquisition
import source_qualification as source


def real_selector():
    return (Path(__file__).parent / 'fixtures/account-selector-anonymized-real.html').read_bytes()


def test_discovery_projects_only_references_and_wrappers_and_stops_before_notices():
    state = source.planner(notice_as_of='2026-10-13', discovery_only=True)
    source.discover(state, source.ORIGIN + '/fr/page/avis-operes', real_selector(), 'frame_document')
    assert state['discovered_accounts'] == ['SYNTHETIC001 PEA', 'SYNTHETIC002 PEA-PME']
    assert state['queue'] == []
    assert source.next_document(state) == {'done': True, 'accounts_verified': True,
        'account_discovery_verified': True,
        'documents': {'complete': True, 'monthly_statements': 0, 'contract_notes': 0}}


@pytest.mark.parametrize('change', ['duplicate', 'invalid', 'no_supported'])
def test_bad_selector_never_confirms_discovery(change):
    raw = real_selector()
    if change == 'duplicate': raw = raw.replace(b'SYNTHETIC002', b'SYNTHETIC001').replace(b'PEA-PME', b'PEA')
    if change == 'invalid': raw = raw.replace(b'SYNTHETIC001', b'invalid/reference')
    if change == 'no_supported': raw = raw.replace(b'PEA-PME', b'CTO').replace(b'PEA', b'CTO')
    state = source.planner(notice_as_of='2026-10-13', discovery_only=True)
    with pytest.raises(RuntimeError):
        source.discover(state, source.ORIGIN + '/fr/page/avis-operes', raw, 'frame_document')
    assert 'discovered_accounts' not in state


def receipt(root, state='completed'):
    saved = {'schema_version': 1, 'state': state, 'run_id': str(uuid.uuid4()),
        'accounts': {'SYNTHETIC001 PEA': 'PEA'} if state == 'completed' else {}}
    connector.atomic_private_yaml(root / 'discovery.yaml', saved)
    return saved


def test_restart_ignores_missing_destination_and_mapping_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(connector.os, 'umask', lambda mask: 0o022)
    receipt(tmp_path)
    monkeypatch.setenv('DRY_RUN', '1')
    monkeypatch.setenv('CRON', '')
    monkeypatch.delenv('BD_SOURCE_ACCOUNT_REF', raising=False)
    monkeypatch.setenv('GHOST_HOST', 'invalid')
    monkeypatch.setenv('GHOST_ACCOUNT_ID', '')
    monkeypatch.setenv('MAPPING_FILE', '/absent/file')
    monkeypatch.setattr(connector, 'Path', lambda value: tmp_path if value == '/state' else Path(value))
    monkeypatch.setattr(acquisition, 'broker_login_ready', lambda root: None)
    def forbidden(*args, **kwargs):
        pytest.fail('Retained discovery must not use vault, broker or Ghostfolio')
    monkeypatch.setattr(acquisition, 'ghostfolio_snapshot', forbidden)
    monkeypatch.setattr(acquisition, 'acquire', forbidden)
    monkeypatch.setattr(acquisition.subprocess, 'Popen', forbidden)
    assert connector.main(['--sync']) == 1
    logs = capsys.readouterr().out
    assert 'SOURCE_ACCOUNT_CONFIGURATION_REQUIRED' in logs
    assert '"broker_attempts": 0' in logs
    assert 'BD_SOURCE_ACCOUNT_REF=\'SYNTHETIC001 PEA\'' in logs


def test_pending_discovery_refuses_without_altering_receipt(tmp_path):
    receipt(tmp_path, 'started')
    before = (tmp_path / 'discovery.yaml').read_bytes()
    with pytest.raises(RuntimeError, match='BROKER_DISCOVERY_UNRESOLVED'):
        acquisition.discovery_receipt(tmp_path)
    assert (tmp_path / 'discovery.yaml').read_bytes() == before


def test_two_services_cannot_hold_the_broker_lock_and_release_allows_restart(tmp_path):
    first = acquisition.broker_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match='BROKER_RUN_LOCKED'):
            acquisition.broker_lock(tmp_path)
    finally:
        os.close(first)
    os.close(acquisition.broker_lock(tmp_path))


def test_source_accounts_keep_distinct_destination_bindings(tmp_path):
    first = acquisition.account_binding_path(tmp_path, 'SYNTHETIC001 PEA')
    second = acquisition.account_binding_path(tmp_path, 'SYNTHETIC002 PEA-PME')
    assert first != second
    saved = {'schema_version': 1, 'ghostfolio_origin': 'https://ghost.invalid',
        'account': {'source_account_ref': 'SYNTHETIC001 PEA',
            'account_key': str(uuid.uuid4()), 'target_account_id': 'destination'}}
    connector.atomic_private_yaml(tmp_path / 'community-binding.yaml', saved)
    assert acquisition.saved_account_binding(tmp_path, first, 'SYNTHETIC001 PEA') == saved
    assert acquisition.saved_account_binding(tmp_path, second, 'SYNTHETIC002 PEA-PME') is None
    with pytest.raises(RuntimeError, match='ACCOUNT_BINDING_CONFLICT'):
        acquisition.reconcile_binding(saved, 'https://ghost.invalid', 'SYNTHETIC001 PEA', 'other')

"""Offline run-finalization and isolated notification-worker regressions."""
import json
import subprocess
import sys

import pytest

import boursedirect_to_ghostfolio as b


@pytest.mark.parametrize('mode,failed,alerts', [('1', True, 0), (None, True, 0),
    ('0', False, 0), ('0', True, 1), ('invalid', True, 0)])
def test_final_summary_and_failure_delivery_gate(monkeypatch, capsys, mode, failed, alerts):
    monkeypatch.delenv('DRY_RUN', raising=False)
    if mode is not None:
        monkeypatch.setenv('DRY_RUN', mode)
    monkeypatch.setenv('APPRISE_URLS', '["json://synthetic-secret@notify.invalid"]')
    calls = []
    def sync(progress):
        progress.update(proposed=3, duplicates=2, skipped=1)
        if failed:
            raise RuntimeError('synthetic-secret must never appear')
        return 0
    monkeypatch.setattr(b, 'sync_buy_simulation', sync)
    monkeypatch.setattr(b, 'send_notification', lambda *args: calls.append(args) or 'timeout')
    assert b.main(['--sync']) == int(failed)
    output = capsys.readouterr().out
    assert 'synthetic-secret' not in output
    logs = [json.loads(line) for line in output.splitlines()]
    summary = next(row for row in logs if row['code'] == 'NOTICE_RUN_COMPLETED')
    assert summary['status'] == ('failed' if failed else 'succeeded')
    assert summary['errors'] == int(failed)
    assert summary['failed_rows'] == 0
    assert summary['proposed'] == 3 and summary['duplicates'] == 2 and summary['skipped'] == 1
    assert len(calls) == alerts
    if alerts:
        assert json.loads(calls[0][2]) == summary


@pytest.mark.parametrize('raw,timeout', [('not-json-secret', '10'), ('["secret"]', '31'),
    (json.dumps(['secret'] * 11), '1')])
def test_invalid_alert_settings_are_fixed_and_disabled(monkeypatch, caplog, raw, timeout):
    monkeypatch.setenv('APPRISE_URLS', raw)
    monkeypatch.setenv('APPRISE_TIMEOUT', timeout)
    assert b.load_notification_config() is None
    assert 'secret' not in caplog.text


def test_notification_worker_deadline_kills_and_reaps_without_secret_output(tmp_path, monkeypatch, capsys):
    worker = tmp_path / 'worker.py'
    worker.write_text("import sys,time; print('secret',flush=True); time.sleep(60)")
    monkeypatch.setattr(b, '_notify_worker_argv', lambda: [sys.executable, str(worker)])
    real_popen, processes = subprocess.Popen, []
    def start(*args, **kwargs):
        assert 'BW_PASSWORD' not in kwargs['env'] and 'GHOST_ACCESS_TOKEN' not in kwargs['env']
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setenv('BW_PASSWORD', 'secret')
    monkeypatch.setenv('GHOST_ACCESS_TOKEN', 'secret')
    monkeypatch.setattr(b.subprocess, 'Popen', start)
    assert b.send_notification({'urls': ['json://secret'], 'timeout': 1}, 'fixed', 'fixed') == 'timeout'
    assert len(processes) == 1 and processes[0].poll() is not None
    assert capsys.readouterr().out == ''


def test_worker_flag_never_enters_sync(monkeypatch):
    monkeypatch.setattr(b, 'notify_worker', lambda: 10)
    monkeypatch.setattr(b, 'sync_buy_simulation', lambda *args: pytest.fail('sync forbidden'))
    assert b.main(['--notify-worker']) == 10

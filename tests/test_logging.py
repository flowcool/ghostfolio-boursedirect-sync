"""CLI logging at the process boundary, with isolated synthetic work."""
import os
import re
import subprocess
import sys

import pytest


def run_cli(code, **settings):
    env = {"PATH": os.environ["PATH"], **settings}
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING"])
def test_log_threshold_streams_format_and_private_request_debug(level):
    result = run_cli("""
import logging
from ghostfolio_boursedirect_sync import __main__ as cli

def synthetic(**kwargs):
    for name in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        logging.getLogger('synthetic').log(getattr(logging, name), 'CANARY_LEVEL_%s', name)
    logging.getLogger('urllib3.connectionpool').debug(
        'https://user:CREDENTIAL_CANARY@example.invalid/?token=TOKEN_CANARY')
    return 0
cli.main = synthetic
raise SystemExit(cli.run())
""", LOG_LEVEL=level)
    assert result.returncode == 0, result.stderr
    for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        visible = (level == "DEBUG" or name != "DEBUG") and (level != "WARNING" or name not in ("DEBUG", "INFO"))
        stream = result.stdout if name in ("DEBUG", "INFO") else result.stderr
        other = result.stderr if name in ("DEBUG", "INFO") else result.stdout
        marker = "CANARY_LEVEL_" + name
        assert stream.count(marker) == int(visible)
        assert marker not in other
        if visible:
            assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[" + name + r"\] " + marker, stream)
    assert "TOKEN_CANARY" not in result.stdout + result.stderr
    assert "CREDENTIAL_CANARY" not in result.stdout + result.stderr


@pytest.mark.parametrize('version,revision,expected', [
    ('2.2.0', 'abcdef012345' + 'a' * 28, '2.2.0 — commit abcdef012345'),
    ('', '', 'dev — commit unknown'),
    ('dev', 'a' * 39 + '\n', 'dev — commit unknown'),
])
@pytest.mark.parametrize('dry_run', [None, '1', '0'])
def test_each_application_run_logs_identity_timezone_and_default_simulation(version, revision, expected, dry_run):
    settings = dict(APP_VERSION=version, APP_REVISION=revision, TZ='Europe/Paris',
                    GHOST_HOST='https://ghostfolio.invalid', GHOST_TOKEN='offline',
                    GHOST_ACCOUNT_NAME='test', BD_ACCOUNT_REF='TESTACCOUNT',
                    PAPERLESS_URL='https://paperless.invalid', PAPERLESS_TOKEN='offline')
    if dry_run is not None:
        settings['DRY_RUN'] = dry_run
    result = run_cli("""
from ghostfolio_boursedirect_sync import __main__ as cli, app
app.paperless.document_ids = lambda settings: []
raise SystemExit(cli.run())
""", **settings)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('[INFO] ghostfolio-boursedirect-sync version ' + expected) == 1
    assert result.stdout.count('Activity comparison TZ=Europe/Paris; must match the Ghostfolio server TZ') == 1
    assert result.stderr.count('[WARNING] DRY_RUN not set: simulation, nothing written') == int(dry_run is None)


def test_worker_dispatch_stays_silent_without_running_sync():
    result = run_cli("""
import sys
from ghostfolio_boursedirect_sync import __main__ as cli
cli.main = lambda **kwargs: (_ for _ in ()).throw(AssertionError('sync must not run'))
sys.argv = ['sync', '--notify-worker']
raise SystemExit(cli.run())
""")
    assert result.returncode == 10
    assert not result.stdout + result.stderr


@pytest.mark.parametrize("level", ["BASIC_FORMAT", "debug", "TOKEN-CANARY"])
def test_invalid_log_level_uses_fixed_configuration_failure(level):
    result = run_cli("""
from ghostfolio_boursedirect_sync import __main__ as cli
raise SystemExit(cli.run())
""", LOG_LEVEL=level, GHOST_HOST='https://ghostfolio.invalid', GHOST_TOKEN='offline',
        GHOST_ACCOUNT_NAME='test', BD_ACCOUNT_REF='TESTACCOUNT',
        PAPERLESS_URL='https://paperless.invalid', PAPERLESS_TOKEN='offline')
    assert result.returncode == 1
    assert 'invalid_configuration LOG_LEVEL' in result.stderr
    assert 'TOKEN-CANARY' not in result.stdout + result.stderr
    assert 'Traceback' not in result.stdout + result.stderr

"""BD failure finalization from real anonymized BUY notice text."""

import json
import logging
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_pdf_buy import settings  # noqa: F401

from ghostfolio_boursedirect_sync import (
    app,
    config,
    ghostfolio,
    notices,
    notify,
    outcome,
    paperless,
)
from ghostfolio_boursedirect_sync.models import ActivityIndex

pytestmark = pytest.mark.usefixtures("settings")


def failure_run(monkeypatch):
    text = (Path(__file__).parent / "fixtures/pdf_buy.txt").read_text()
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"offline PDF boundary")
    monkeypatch.setattr(notices, "extract_text", lambda _: text)
    monkeypatch.setattr(ghostfolio, "exchange_token", lambda _: "offline")
    monkeypatch.setattr(ghostfolio, "find_account", lambda *_: "target")
    monkeypatch.setattr(ghostfolio, "read_activities", lambda *_: ActivityIndex((), {}, {}))
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: None)
    monkeypatch.setattr(ghostfolio, "import_activities", Mock(side_effect=AssertionError("no POST")))


@pytest.mark.parametrize("status", ["sent", "failed", "timeout", RuntimeError("private destination")])
def test_unresolved_real_buy_notifies_once_without_changing_exit(monkeypatch, caplog, status):
    failure_run(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("APPRISE_URLS", json.dumps(["json://notify.invalid/hook"]))
    sender = Mock(side_effect=status) if isinstance(status, Exception) else Mock(return_value=status)
    monkeypatch.setattr(notify, "send_notification", sender)
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    sender.assert_called_once()
    assert sender.call_args.args[2] == "Run failed: unresolved_security."
    assert caplog.text.count("Summary:") == 1
    assert ("Failure notification sent" in caplog.text) == (status == "sent")
    assert "private destination" not in caplog.text


@pytest.mark.parametrize("mode", [None, "1", "bad", "false", ""])
@pytest.mark.parametrize("destinations", ["invalid private destination", '["json://notify.invalid/hook"]'])
def test_simulation_or_invalid_mode_never_reads_notification_settings(monkeypatch, mode, destinations):
    failure_run(monkeypatch)
    if mode is not None:
        monkeypatch.setenv("DRY_RUN", mode)
    monkeypatch.setenv("APPRISE_URLS", destinations)
    loader = Mock(side_effect=AssertionError("must stay silent"))
    monkeypatch.setattr(config, "load_notification_config", loader)
    assert app.main() == 1
    loader.assert_not_called()


def test_config_failure_can_notify_without_disclosing_value(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.delenv("PAPERLESS_TOKEN")
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    sender = Mock(return_value="sent")
    monkeypatch.setattr(notify, "send_notification", sender)
    assert app.main() == 1
    assert sender.call_args.args[2] == "Run failed: invalid_configuration."


def test_success_stays_silent(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setattr(paperless, "document_ids", lambda _: [])
    sender = Mock()
    monkeypatch.setattr(notify, "send_notification", sender)
    assert app.main() == 0
    sender.assert_not_called()


def test_unknown_failure_text_is_replaced_by_fixed_code():
    assert outcome.failure_summary({"secret holder account", "unresolved_security"}) == (
        "Run failed: unhandled_error, unresolved_security.")


def test_unexpected_failure_notifies_without_exception_text(monkeypatch, caplog):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    monkeypatch.setattr(config, "load", Mock(side_effect=ValueError("private failure value")))
    sender = Mock(return_value="sent")
    monkeypatch.setattr(notify, "send_notification", sender)
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert sender.call_args.args[2] == "Run failed: unhandled_error."
    assert caplog.text.count("Summary:") == 1
    assert "created=0" in caplog.text and "private failure value" not in caplog.text


def test_unexpected_failure_keeps_confirmed_creation_count(monkeypatch, caplog):
    failure_run(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    text = (Path(__file__).parent / "fixtures/pdf_buy.txt").read_text()
    # Preserve two occurrences of the same real BUY, under one account label.
    monkeypatch.setattr(notices, "extract_text", lambda _: text + "\n" + text.split("\n", 1)[1])
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
    writer = Mock(side_effect=[None, ValueError("private failure value")])
    monkeypatch.setattr(ghostfolio, "import_activities", writer)
    sender = Mock(return_value="sent")
    monkeypatch.setattr(notify, "send_notification", sender)
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert writer.call_count == 2
    assert caplog.text.count("Summary:") == 1
    assert "created=1" in caplog.text and "private failure value" not in caplog.text
    assert sender.call_args.args[2] == "Run failed: unhandled_error."


@pytest.mark.parametrize("mode", [None, "0", "1", "bad"])
def test_invalid_schedule_uses_configuration_finalizer(monkeypatch, caplog, mode):
    if mode is not None:
        monkeypatch.setenv("DRY_RUN", mode)
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    loader = Mock(side_effect=AssertionError("configuration and sync must not run"))
    monkeypatch.setattr(config, "load", loader)
    sender = Mock(return_value="sent")
    monkeypatch.setattr(notify, "send_notification", sender)
    with caplog.at_level(logging.INFO):
        assert app.main(invalid_schedule=True) == 1
    loader.assert_not_called()
    assert sender.call_count == int(mode == "0")
    if mode == "0":
        assert sender.call_args.args[2] == "Run failed: invalid_configuration."
    assert caplog.text.count("Summary:") == 1
    assert "created=0" in caplog.text


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_interrupted_run_does_not_notify(monkeypatch, interrupt):
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    monkeypatch.setattr(config, "load", Mock(side_effect=interrupt))
    sender = Mock()
    monkeypatch.setattr(notify, "send_notification", sender)
    with pytest.raises(interrupt):
        app.main()
    sender.assert_not_called()

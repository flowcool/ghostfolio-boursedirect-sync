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


@pytest.mark.parametrize("mode", [None, "1", "0"])
def test_persistent_failure_notifies_once_each_run_including_simulation(monkeypatch, mode):
    failure_run(monkeypatch)
    if mode is not None:
        monkeypatch.setenv("DRY_RUN", mode)
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    sender = Mock(return_value="sent")
    monkeypatch.setattr(notify, "send_notification", sender)
    assert app.main() == 1
    assert app.main() == 1
    assert sender.call_count == 2
    assert all(call.args[2] == "Run failed: unresolved_security." for call in sender.call_args_list)


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


@pytest.mark.parametrize("mode", ["0", "1"])
@pytest.mark.parametrize("field,value", [
    ("APPRISE_URLS", "private invalid destination"),
    ("APPRISE_URLS", '["not-an-apprise-url"]'),
    ("APPRISE_TIMEOUT", "0"),
    ("APPRISE_TIMEOUT", "31"),
])
def test_invalid_notification_settings_stop_before_service_access(monkeypatch, caplog, mode, field, value):
    monkeypatch.setenv("DRY_RUN", mode)
    monkeypatch.setenv(field, value)
    source = Mock(side_effect=AssertionError("no service access"))
    monkeypatch.setattr(paperless, "document_ids", source)
    target = Mock(side_effect=AssertionError("no target access"))
    monkeypatch.setattr(ghostfolio, "exchange_token", target)
    sender = Mock()
    monkeypatch.setattr(notify, "send_notification", sender)
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    source.assert_not_called()
    target.assert_not_called()
    sender.assert_not_called()
    assert f"invalid_configuration {field}" in caplog.text
    assert "private invalid destination" not in caplog.text
    assert caplog.text.count("Summary:") == 1
    assert "created=0" in caplog.text


def test_invalid_destination_does_not_log_its_secret(monkeypatch, caplog):
    monkeypatch.setenv("APPRISE_URLS", '["discord//123456/SECRET-CANARY"]')
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError, match="^invalid_configuration APPRISE_URLS$"):
            config.load_notification_config()
    assert "SECRET-CANARY" not in caplog.text


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
    assert sender.call_count == 1
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


@pytest.mark.parametrize("stage", ["configuration", "document", "review"])
@pytest.mark.parametrize("message", [
    "SECRET-CANARY https://user:CREDENTIAL-CANARY@example.invalid/?token=TOKEN-CANARY",
    "notice_unreadable SECRET-CANARY",
    "invalid_configuration SECRET-CANARY",
])
def test_runtime_exception_text_never_reaches_logs_or_notifications(monkeypatch, caplog, stage, message):
    failure_run(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "0")
    monkeypatch.setenv("APPRISE_URLS", '["json://notify.invalid/hook"]')
    sender = Mock(return_value="sent")
    monkeypatch.setattr(notify, "send_notification", sender)
    if stage == "configuration":
        monkeypatch.setattr(config, "load", Mock(side_effect=RuntimeError(message)))
    elif stage == "document":
        monkeypatch.setattr(notices, "extract_text", Mock(side_effect=RuntimeError(message)))
    else:
        monkeypatch.setenv("ACTIVITY_REVIEW_FILE", "/review/activities.yaml")
        monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
        monkeypatch.setattr(app.activity_review, "open_review", Mock(side_effect=RuntimeError(message)))
    with caplog.at_level(logging.DEBUG):
        assert app.main() == 1
    sender.assert_called_once()
    evidence = caplog.text + sender.call_args.args[2]
    for secret in ("SECRET-CANARY", "CREDENTIAL-CANARY", "TOKEN-CANARY", "example.invalid"):
        assert secret not in evidence
    assert "Run failed: " in sender.call_args.args[2]



def test_blocked_review_logs_a_fixed_reason_without_private_exception_status(caplog):
    proposal = {"source event": "derived-event", "actionable": False,
                "status": "SECRET-CANARY https://user:TOKEN-CANARY@example.invalid"}
    codes = set()
    with caplog.at_level(logging.WARNING):
        app.activity_review.report_review_outcome({}, {"_codes": codes},
                                                 {"derived": proposal}, {"derived-event"}, set())
    assert codes == {"review_evidence"}
    assert "reason=review_evidence" in caplog.text
    assert "SECRET-CANARY" not in caplog.text
    assert "TOKEN-CANARY" not in caplog.text
    assert proposal["status"].startswith("SECRET-CANARY")  # Retain private review evidence.


@pytest.mark.parametrize("review", [False, True])
def test_operational_evidence_keeps_infra_result_contract(monkeypatch, caplog, tmp_path, review):
    failure_run(monkeypatch)
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(ghostfolio, "lookup_symbol", lambda *_: "EXAMPLE.PA")
    if review:
        monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(tmp_path / "review.yaml"))
    with caplog.at_level(logging.INFO):
        assert app.main() == 0
    lines = [record.message for record in caplog.records]
    assert "Cycle result: success" in lines
    assert "Summary: simulated=1 duplicates=0 corrections=0 other_account_notices=0 unreadable_notices=0 created=0" in lines
    deferred = "0" if review else "disabled"
    assert ("Account evidence: simulated proposals=1; duplicates=0; other held events=0; "
            f"deferred automatic work={deferred}; cash=not managed") in lines
    if review:
        assert ("Reconciliation result: already consistent=0; automatically corrected=0; manually corrected=0; "
                "automatic work deferred=0; manual review required=0; rejected association=0; blocked=0; "
                "would correct=0; reference migrations=0; corrected targets=0; decision counts can overlap") in lines
        assert ("Review summary: conforming=0 corrections=0 migrations=0 held=0 deferred=0 "
                "would_correct=0 counts_available=True counts_can_overlap=yes") in lines
    else:
        assert "Reconciliation result: disabled" in lines
        assert "Review summary: disabled" in lines
        assert not any("Review summary: conforming=" in line for line in lines)
    assert "Notification result: not required" in lines


def test_failed_acquisition_has_no_invented_account_evidence(monkeypatch, caplog):
    monkeypatch.setattr(config, "load", Mock(side_effect=RuntimeError("invalid_configuration")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert ("Account evidence: imports=unavailable; duplicates=unavailable; "
            "other held events=unavailable; deferred automatic work=unavailable; cash=not managed") in caplog.text


def test_configured_review_without_results_stays_unavailable(monkeypatch, caplog, tmp_path):
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(tmp_path / "review.yaml"))
    monkeypatch.setattr(paperless, "document_ids", Mock(side_effect=RuntimeError("paperless_unreachable")))
    with caplog.at_level(logging.INFO):
        assert app.main() == 1
    assert "Reconciliation result: unavailable" in caplog.text
    assert "Review summary: unavailable" in caplog.text
    assert "Review summary: conforming=" not in caplog.text
    assert "paperless_unreachable" in caplog.text

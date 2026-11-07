"""IBKR grouped delivery semantics adapted to the BD private review mount."""

import os

import pytest

from ghostfolio_boursedirect_sync import action_notifications as grouped


def plan(tmp_path, groups, now=1000):
    return grouped.plan_action_notification(groups, str(tmp_path / "review.yaml"), "a" * 64, now)


def test_grouped_changed_cleared_and_seven_day_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(grouped.time, "time", lambda: 1000)
    first = plan(tmp_path, {"coverage_gap": {"private-event"}})
    assert first["due"]
    assert grouped.confirm_action_notification(first)
    assert not plan(tmp_path, {"coverage_gap": {"other-event"}}, 1001)["due"]
    assert not plan(tmp_path, {"coverage_gap": {"x"}}, 1000 + 168 * 3600 - 1)["due"]
    assert plan(tmp_path, {"coverage_gap": {"x"}}, 1000 + 168 * 3600)["due"]
    assert plan(tmp_path, {"coverage_gap": {"x", "y"}})["due"]
    assert plan(tmp_path, {"review_approval": {"x"}})["due"]
    cleared = plan(tmp_path, {})
    assert cleared["due"] and cleared["cleared"] == ["coverage_gap"]
    assert grouped.confirm_action_notification(cleared)
    assert not plan(tmp_path, {})["due"]
    state = (tmp_path / "review.yaml.normal.required-actions.yaml").read_text()
    assert "private-event" not in state and "other-event" not in state


@pytest.mark.parametrize("damage", ["corrupt", "rollback", "concurrent", "symlink", "input-alias"])
def test_bad_delivery_state_keeps_actions_eligible_without_overwrite(tmp_path, monkeypatch, damage):
    monkeypatch.setattr(grouped.time, "time", lambda: 1000)
    first = plan(tmp_path, {"coverage_gap": {"x"}})
    assert grouped.confirm_action_notification(first)
    path = first["path"]
    if damage == "corrupt":
        path.write_text("invalid")
        assert plan(tmp_path, {"coverage_gap": {"x"}})["due"]
    elif damage == "rollback":
        assert plan(tmp_path, {"coverage_gap": {"x"}}, 999)["due"]
    elif damage == "concurrent":
        next_plan = plan(tmp_path, {"coverage_gap": {"x", "y"}})
        path.write_bytes(path.read_bytes() + b"\n")
        assert not grouped.confirm_action_notification(next_plan)
    elif damage == "symlink":
        target = tmp_path / "protected.yaml"
        path.rename(target)
        path.symlink_to(target)
        unsafe = plan(tmp_path, {"coverage_gap": {"x"}})
        assert unsafe["due"] and unsafe["path"] is None
    else:
        protected = grouped.plan_action_notification({"coverage_gap": {"x"}}, str(tmp_path / "review.yaml"),
                                                     "a" * 64, inputs=[path])
        assert protected["path"] is None


def test_failed_run_never_announces_actions_cleared(tmp_path, monkeypatch):
    from ghostfolio_boursedirect_sync import activity_review, app, config, notify

    filename = str(tmp_path / "review.yaml")
    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", filename)
    context = activity_review.fingerprint([os.environ.get(key, "") for key in
        ("GHOST_HOST", "GHOST_ACCOUNT_NAME", "BD_ACCOUNT_REF", "PAPERLESS_URL")])
    confirmed = grouped.plan_action_notification({"review_approval": {"private-event"}}, filename, context)
    assert grouped.confirm_action_notification(confirmed)
    before = confirmed["path"].read_bytes()

    def failure(errors, **kwargs):
        errors.add("paperless_unreachable")
        return 1

    messages = []
    monkeypatch.setattr(app, "run_sync", failure)
    monkeypatch.setattr(config, "load_notification_config", lambda: {"urls": ["json://notify.invalid"], "timeout": 1})
    monkeypatch.setattr(notify, "send_notification", lambda _, title, body: messages.append(body) or "sent")
    assert app.main() == 1
    assert len(messages) == 1 and "paperless_unreachable" in messages[0]
    assert "Action cleared" not in messages[0]
    assert confirmed["path"].read_bytes() == before


@pytest.mark.parametrize("first_mode,reason", [("1", "coverage_gap"), ("0", "review_approval")])
def test_alternating_modes_never_clear_unevaluated_actions(tmp_path, monkeypatch, first_mode, reason):
    from ghostfolio_boursedirect_sync import app, config, notify

    monkeypatch.setenv("ACTIVITY_REVIEW_FILE", str(tmp_path / "review.yaml"))
    clock = [1000]
    monkeypatch.setattr(grouped.time, "time", lambda: clock[0])
    current = {reason: {"private-event"}}

    def run(errors, **kwargs):
        kwargs["actions"].update(current)
        errors.update(current)
        return 0

    messages = []
    monkeypatch.setattr(app, "run_sync", run)
    monkeypatch.setattr(config, "load_notification_config", lambda: {"urls": ["json://notify.invalid"], "timeout": 1})
    monkeypatch.setattr(notify, "send_notification", lambda _, title, body: messages.append(body) or "sent")
    monkeypatch.setenv("NOTICE_COVERAGE", first_mode)
    assert app.main() == 0 and len(messages) == 1
    current.clear()
    monkeypatch.setenv("NOTICE_COVERAGE", "0" if first_mode == "1" else "1")
    assert app.main() == 0 and len(messages) == 1
    current[reason] = {"private-event"}
    monkeypatch.setenv("NOTICE_COVERAGE", first_mode)
    clock[0] += 168 * 3600 - 1
    assert app.main() == 0 and len(messages) == 1
    clock[0] += 1
    assert app.main() == 0 and len(messages) == 2
    assert all("Action cleared" not in message for message in messages)

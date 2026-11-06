"""IBKR grouped delivery semantics adapted to the BD private review mount."""

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
    state = (tmp_path / "review.yaml.required-actions.yaml").read_text()
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

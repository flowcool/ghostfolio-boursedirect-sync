"""Review file behavior; financial examples derive from anonymized PDF fixtures."""

import os

import pytest

from ghostfolio_boursedirect_sync import activity_review as review


def test_private_review_roundtrip_detects_concurrent_operator_edit(tmp_path):
    path = tmp_path / "review.yaml"
    state = review.open_review(str(path), [])
    try:
        review.publish_review(state, {"version": 1, "proposals": {}})
        assert review.read_yaml(path.read_bytes())["version"] == 3
        assert path.stat().st_mode & 0o777 == 0o600
        path.write_bytes(path.read_bytes() + b"\n")
        with pytest.raises(RuntimeError):
            review.assert_unchanged(state)
    finally:
        review.close_review(state)


@pytest.mark.parametrize("kind", ["public-parent", "public-file", "symlink", "missing", "hardlink", "overlap"])
def test_unsafe_review_paths_fail_before_financial_work(tmp_path, kind):
    source = tmp_path / "source.yaml"
    source.write_text("version: 1")
    source.chmod(0o600)
    path = tmp_path / "review.yaml"
    if kind == "public-parent":
        tmp_path.chmod(0o755)
    elif kind == "public-file":
        path.write_text("version: 1")
        path.chmod(0o644)
    elif kind == "symlink":
        path.symlink_to(source)
    elif kind == "missing":
        path = tmp_path / "missing" / "review.yaml"
    elif kind == "hardlink":
        os.link(source, path)
    elif kind == "overlap":
        path = source
    with pytest.raises(RuntimeError):
        review.open_review(str(path), [str(source)])


def test_decision_yes_is_literal_and_duplicate_yaml_keys_are_rejected():
    assert review.read_yaml(b"decision: yes")["decision"] == "yes"
    assert review.read_yaml(b"decision: true")["decision"] is True
    with pytest.raises(RuntimeError):
        review.read_yaml(b"version: 1\nversion: 2\n")



def sample():
    from test_activity_evidence import existing_row, proposed

    row = existing_row(userId="owner", tags=[], fee=2)
    event = proposed()
    events = review.source_events([event], "TESTACCOUNT", {event.comment: [{"sha256": "a" * 64}]})
    return row, event, events


def test_proposal_keeps_notes_and_consent_only_for_unchanged_evidence():
    row, event, events = sample()
    row["comment"] += "\n\nPrivate note"
    first, held = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    item = next(iter(first.values()))
    assert held == {event.comment}
    assert item["changed fields"] == ["fee"]
    assert item["proposed values"]["comment"].endswith("Private note")
    item["approve"] = "yes"
    same, _ = review.refresh_proposals(first, events, [row], {"TESTACCOUNT": "target"})
    assert next(iter(same.values()))["approve"] == "yes"
    changed, _ = review.refresh_proposals(same, events, [{**row, "fee": 3}], {"TESTACCOUNT": "target"})
    assert next(iter(changed.values()))["approve"] is None


@pytest.mark.parametrize("change", [{"quantity": 5}, {"type": "SELL"}, {"accountId": "other"},
    {"currency": "USD"}, {"assetProfile": {"symbol": "OTHER", "dataSource": "YAHOO"}},
    {"assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "YAHOO", "isin": "FR0000000002"}}])
def test_manual_yes_cannot_approve_immutable_or_conflicting_fields(change):
    row, event, events = sample()
    row.update(change)
    if change.get("type") == "SELL":
        with pytest.raises(RuntimeError, match="invalid_identity"):
            review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
        return
    with pytest.raises(RuntimeError, match="owned_activity_conflict"):
        review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    # A nearby unowned row stays a blocked review proposal, never executable.
    row["comment"] = "Manual note"
    proposals, held = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    if proposals:
        assert not next(iter(proposals.values()))["actionable"]
        assert event.comment in held


def test_unchanged_unowned_duplicate_does_not_require_migration():
    row, event, events = sample()
    row.update(comment="Manual note", fee=1)
    proposals, held = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    assert proposals == {}
    assert held == set()


def test_changed_yes_cannot_be_replaced_by_immediate_profile_authority():
    row, event, events = sample()
    first, _ = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"}, reconciliation="conservative")
    next(iter(first.values()))["approve"] = "yes"
    changed, _ = review.refresh_proposals(first, events, [{**row, "fee": 3}],
                                        {"TESTACCOUNT": "target"}, reconciliation="conservative")
    item = next(iter(changed.values()))
    assert item["approve"] is None
    assert not item["automatic eligible"]


def test_competing_candidates_hold_only_related_events_even_with_one_yes():
    row, event, events = sample()
    row["comment"] = "Manual note"
    alternative = {**row, "id": "alternative"}
    proposals, held = review.refresh_proposals({}, events, [row, alternative], {"TESTACCOUNT": "target"})
    next(iter(proposals.values()))["approve"] = "yes"
    selected, blocked_accounts = review.selected_proposals(proposals)
    assert held == {event.comment}
    assert selected == []
    assert blocked_accounts == set()


def test_missing_source_clears_authority_and_keeps_hold():
    row, event, events = sample()
    first, _ = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    next(iter(first.values()))["approve"] = "yes"
    missing, held = review.refresh_proposals(first, {}, [row], {"TESTACCOUNT": "target"})
    item = next(iter(missing.values()))
    assert held == {event.comment}
    assert not item["actionable"]
    assert item["approve"] is None


def test_legacy_migration_requires_reproducible_pdf_hash_inputs():
    import hashlib
    import json
    from decimal import Decimal
    from pathlib import Path

    from ghostfolio_boursedirect_sync import notices, sync

    text = (Path(__file__).parent / "fixtures" / "pdf_buy.txt").read_text().replace("TEST ACCOUNT", "TESTACCOUNT")
    notice = notices.parse_text(text)
    event = sync.activity(notice.trades[0], {notice.trades[0].isin: "EXAMPLE.PA"}, "target",
                          notice.account_ref, sync.notice_namespace(notice), 0)
    events = review.source_events([event], notice.account_ref, {event.comment: [{"sha256": "a" * 64}]})
    # Independent reproduction of legacy-wip notice_identity; no edited review input.
    namespace = hashlib.sha256(b'["TESTACCOUNT PEA","target"]').hexdigest()
    body = {"kind": "BUY", "date": "2025-02-03", "isin": "FR0000120271",
            "execution_time": "12:00:00", "quantity": "4", "unit_price": "25.5",
            "brokerage": "1", "vat": "0", "debit": "103", "credit": "0"}
    digest = hashlib.sha256((json.dumps(body, sort_keys=True, separators=(",", ":")) + ":1").encode()).hexdigest()
    reference = f"BD#v2#{namespace}#{digest}"
    assert events[event.comment]["legacy"] == [reference]
    row, _, _ = sample()
    row.update(date=event.date, quantity=event.quantity, unitPrice=event.unit_price,
               fee=3, comment=reference + "\n\nKeep notes")
    row["assetProfile"]["isin"] = event.isin
    proposals, _ = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    proposal = next(iter(proposals.values()))
    assert proposal["actionable"]
    assert proposal["changed fields"] == ["comment"]
    assert proposal["proposed values"]["fee"] == "3"
    assert proposal["proposed values"]["comment"] == event.comment + "\n\nKeep notes"
    # Migration must precede the separately authorized TTF fee correction.
    row["fee"] = 1
    events[event.comment]["brokerage"] = "1"
    events[event.comment]["values"]["fee"] = "1.30"
    events[event.comment]["payload"]["fee"] = Decimal("1.30")
    ttf_migration, _ = review.refresh_proposals({}, events, [row], {"TESTACCOUNT": "target"})
    migrating = next(iter(ttf_migration.values()))
    assert migrating["changed fields"] == ["comment"]
    assert not migrating["ttf eligible"]

    # Missing execution-time evidence must not invent an old identity.
    missing = notices.parse_text(text.replace("Heure Execution: 12:00:00         Lieu: DEUTSCHER KASSENVEREIN GRUPPE DEUTSC", ""))
    missing_event = sync.activity(missing.trades[0], {missing.trades[0].isin: "EXAMPLE.PA"}, "target",
                                  missing.account_ref, sync.notice_namespace(missing), 0)
    missing_events = review.source_events([missing_event], missing.account_ref, {})
    assert missing_events[missing_event.comment]["legacy"] == []
    blocked, _ = review.refresh_proposals({}, missing_events, [row], {"TESTACCOUNT": "target"})
    assert not next(iter(blocked.values()))["actionable"]

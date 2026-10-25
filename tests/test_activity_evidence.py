"""Startup and selection regressions using the anonymized real BUY notice.

API envelopes follow pinned IBKR ghostfolio.py:208,259. All HTTP is mocked.
"""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from itertools import combinations_with_replacement, permutations
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from ghostfolio_boursedirect_sync import app, ghostfolio, notices, paperless, sync

FIXTURE = Path(__file__).parent / "fixtures/pdf_buy.txt"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def proposed():
    notice = notices.parse_text(FIXTURE.read_text())
    return sync.activity(notice.buys[0], {notice.buys[0].isin: "EXAMPLE.PA"},
                         "target", notice.account_ref, sync.notice_namespace(notice), 0)


def existing_row(**changes):
    value = proposed()
    return {
        "id": "existing", "accountId": value.account_id, "date": value.date,
        "type": "BUY", "quantity": 4, "unitPrice": Decimal("25.50"), "fee": 1,
        "currency": "EUR", "comment": value.comment,
        "assetProfile": {"symbol": value.symbol, "dataSource": "YAHOO",
                         "isin": "FR0000120271"}, **changes,
    }


def index(*rows):
    return ghostfolio.index_existing_activities({"count": len(rows), "activities": list(rows)}, now=NOW)


@pytest.mark.parametrize("body", [None, {}, {"activities": [], "count": True},
                                  {"activities": [], "count": 1},
                                  {"activities": [None], "count": 1}])
def test_missing_or_partial_activity_evidence_refuses(body):
    with pytest.raises(RuntimeError, match="^activities_unavailable$"):
        ghostfolio.index_existing_activities(body)


@pytest.mark.parametrize("change", [
    {"quantity": None}, {"quantity": True}, {"quantity": 0.1},
    {"unitPrice": Decimal("NaN")}, {"fee": -1}, {"comment": 3},
    {"date": "2025-02-03"}, {"isExcluded": 1}, {"account": []},
    {"tags": [{"id": None}]}, {"assetProfile": None},
    {"assetProfile": {"symbol": "EXAMPLE.PA"}},
])
def test_redaction_invalid_numbers_profiles_and_eligibility_refuse(change):
    with pytest.raises(RuntimeError, match="^activities_unavailable$"):
        index(existing_row(**change))


def test_current_profile_cannot_hide_behind_valid_legacy_profile():
    row = existing_row()
    row["SymbolProfile"] = row["assetProfile"]
    row["assetProfile"] = None
    with pytest.raises(RuntimeError, match="^activities_unavailable$"):
        index(row)
    del row["assetProfile"]
    assert index(row).positions == {("target", "EXAMPLE.PA"): Decimal(4)}


@pytest.mark.parametrize("changes", [{"isExcluded": True}, {"isDraft": True},
    {"account": {"tags": [{"id": next(iter(ghostfolio.INACTIVE_TAGS))}]}},
    {"assetProfile": {"symbol": "EXAMPLE.PA", "dataSource": "MANUAL"}},
    {"date": "2099-01-01T00:00:00Z"}])
def test_ineligible_rows_keep_owned_identity_without_supporting_holdings(changes):
    ledger = index(existing_row(**changes))
    assert proposed().comment in ledger.identities
    assert ledger.positions == {}


def test_duplicate_activity_ids_cannot_inflate_positions():
    with pytest.raises(RuntimeError, match="^activities_unavailable$"):
        index(existing_row(), existing_row())


def test_decimal_positions_retain_digits_beyond_default_context():
    quantity = Decimal("0.12345678901234567890123456789")
    ledger = index(existing_row(quantity=quantity))
    assert ledger.positions[("target", "EXAMPLE.PA")] == quantity


@pytest.mark.parametrize("comment", ["BD#v4#unexpected", "BD#v3#bad", "BD#v3#X:SELL:key"])
def test_reserved_identity_errors_do_not_echo_comment(comment):
    with pytest.raises(RuntimeError, match="^invalid_identity$"):
        index(existing_row(comment=comment))


def test_legacy_identities_remain_manual_match_evidence():
    for comment in ("BD#v1#legacy-account#" + "a" * 64,
                    "BD#v2#" + "a" * 64 + "#" + "b" * 64):
        ledger = index(existing_row(comment=comment))
        assert ledger.identities == {}
        assert ledger.positions[("target", "EXAMPLE.PA")] == 4


def test_owned_duplicate_and_moved_or_changed_identity_selection():
    assert sync.select_account_activities([proposed()], index(existing_row()), now=NOW).duplicates == 1
    for changes in ({"accountId": "other"}, {"quantity": 5},
                    {"assetProfile": {"symbol": "OTHER.PA", "dataSource": "YAHOO"}}):
        result = sync.select_account_activities([proposed()], index(existing_row(**changes)), now=NOW)
        assert result.activities == ()
        assert result.errors == ("owned_activity_conflict",)


def test_manual_match_requires_exact_price_and_consumes_one_row():
    manual = existing_row(comment="manual entry", date="2025-02-04T12:00:00Z")
    result = sync.select_account_activities([proposed()], index(manual), now=NOW)
    assert result.activities == ()
    assert result.duplicates == 1
    assert result.errors == ()

    nearby = existing_row(comment="manual entry", unitPrice=Decimal("25.51"))
    result = sync.select_account_activities([proposed()], index(nearby), now=NOW)
    assert result.activities == ()
    assert result.duplicates == 0
    assert result.errors == ("possible_duplicate",)


def test_manual_row_does_not_match_two_source_rows():
    first = proposed()
    second = replace(first, comment=first.comment + "-other")
    result = sync.select_account_activities([first, second], index(existing_row(comment="manual entry")), now=NOW)
    assert result.duplicates == 1
    assert result.activities == (second,)


def test_manual_match_source_copy_is_still_a_duplicate():
    result = sync.select_account_activities(
        [proposed(), proposed()], index(existing_row(comment="manual entry")), now=NOW
    )
    assert result.activities == ()
    assert result.duplicates == 2


def test_manual_match_uses_calendar_days_and_closest_candidate_first():
    manual = existing_row(comment="manual entry", date="2025-02-05T10:00:00Z")
    result = sync.select_account_activities([proposed()], index(manual), now=NOW)
    assert result.duplicates == 1 and result.errors == ()

    first = replace(proposed(), date="2025-02-03T00:00:00+00:00", comment=proposed().comment + "-first")
    second = replace(proposed(), date="2025-02-05T00:00:00+00:00", comment=proposed().comment + "-second")
    manual = existing_row(comment="manual entry", date="2025-02-05T10:00:00Z")
    result = sync.select_account_activities([first, second], index(manual), now=NOW)
    assert result.duplicates == 1
    assert result.activities == (first,)


def test_manual_closest_date_is_recomputed_after_each_match():
    candidates = [
        replace(proposed(), date=f"2025-02-{day:02d}T00:00:00+00:00",
                comment=proposed().comment + f"-{day}")
        for day in (1, 2, 3)
    ]
    rows = [
        existing_row(id="manual-1", comment="manual one", date="2025-02-01T12:00:00Z"),
        existing_row(id="manual-2", comment="manual two", date="2025-02-04T12:00:00Z"),
    ]
    result = sync.select_account_activities(candidates, index(*rows), now=NOW)
    assert result.duplicates == 2
    assert [item.date[:10] for item in result.activities] == ["2025-02-02"]


@pytest.mark.parametrize("reverse_candidates", [False, True])
@pytest.mark.parametrize("reverse_rows", [False, True])
@pytest.mark.parametrize(("source_days", "manual_days"), [((2, 4), (1, 3)),
                                                          ((1, 4), (3, 5)),
                                                          ((2, 4), (1, 2))])
def test_competing_manual_rows_maximize_matches(reverse_candidates, reverse_rows,
                                               source_days, manual_days):
    candidates = [
        replace(proposed(), date=f"2025-02-{day:02d}T00:00:00+00:00",
                comment=proposed().comment + f"-{day}")
        for day in source_days
    ]
    rows = [existing_row(id=row_id, comment="manual entry",
                         date=f"2025-02-{day:02d}T12:00:00Z")
            for row_id, day in zip(("manual-z", "manual-a"), manual_days, strict=True)]
    result = sync.select_account_activities(
        candidates[::-1] if reverse_candidates else candidates,
        index(*(rows[::-1] if reverse_rows else rows)), now=NOW,
    )
    assert result.duplicates == 2
    assert result.activities == ()
    assert result.errors == ()


def test_manual_assignment_minimizes_total_distance():
    candidates = [replace(proposed(), date=f"2025-02-{day:02d}T00:00:00+00:00",
                          comment=proposed().comment + f"-{day}") for day in (1, 2)]
    ledger = index(*(existing_row(id=f"manual-{day}", comment="manual entry",
                                  date=f"2025-02-{day:02d}T12:00:00Z") for day in (1, 3)))
    groups = [sync._manual_rows(candidate, ledger, set()) for candidate in candidates]
    assignment = sync._manual_assignment(groups, candidates)
    distances = [distance for i, group in enumerate(groups) for distance, row in group
                 if assignment.get(i) == row.id]
    assert len(assignment) == 2
    assert sum(distances) == 1


def test_manual_assignment_matches_exhaustive_small_calendar_oracle():
    value = proposed()
    for source_days in combinations_with_replacement(range(1, 5), 3):
        candidates = [replace(value, date=f"2025-02-{day:02d}T00:00:00+00:00",
                              comment=value.comment + f"-{i}")
                      for i, day in enumerate(source_days)]
        for manual_days in combinations_with_replacement(range(1, 5), 3):
            ledger = index(*(existing_row(id=f"row-{i}", comment="manual entry",
                                          date=f"2025-02-{day:02d}T12:00:00Z")
                             for i, day in enumerate(manual_days)))
            groups = [sync._manual_rows(candidate, ledger, set()) for candidate in candidates]
            assignment = sync._manual_assignment(groups, candidates)
            observed = (-len(assignment), sum(distance for i, group in enumerate(groups)
                                             for distance, row in group
                                             if assignment.get(i) == row.id))
            # Enumerate full pair permutations, allowing unavailable pairs to be omitted.
            expected = min((-len(gaps), sum(gaps))
                           for order in permutations(manual_days)
                           for gaps in [[abs(a - b) for a, b in zip(source_days, order, strict=True)
                                         if abs(a - b) <= 2]])
            assert observed == expected, (source_days, manual_days)


def test_independent_manual_securities_do_not_share_assignment_work(monkeypatch):
    value = proposed()
    candidates = [replace(value, symbol=f"SECURITY-{i}", isin=None,
                          comment=value.comment + f"-{i}") for i in range(20)]
    ledger = index(*(existing_row(id=f"row-{i}", comment="manual entry",
                                  assetProfile={"symbol": candidate.symbol,
                                                "dataSource": "YAHOO"})
                     for i, candidate in enumerate(candidates)))
    solve = Mock(wraps=sync._assign_manual_component)
    monkeypatch.setattr(sync, "_assign_manual_component", solve)
    result = sync.select_account_activities(candidates, ledger, now=NOW)
    assert result.duplicates == 20
    assert result.activities == ()
    assert result.errors == ()
    assert solve.call_count == 0


def test_source_copy_does_not_reserve_another_manual_row():
    first = proposed()
    second = replace(first, date="2025-02-05T00:00:00+00:00", comment=first.comment + "-second")
    ledger = index(existing_row(id="first", comment="manual entry"),
                   existing_row(id="second", comment="manual entry", date=second.date))
    result = sync.select_account_activities([first, first, second], ledger, now=NOW)
    assert result.activities == ()
    assert result.duplicates == 3
    assert result.errors == ()


def test_excluded_owned_duplicate_is_not_recreated():
    result = sync.select_account_activities([proposed()], index(existing_row(isExcluded=True)), now=NOW)
    assert result.duplicates == 1
    assert result.activities == ()


def test_duplicate_sources_future_and_conflicts_leave_snapshot_unchanged():
    ledger = index()
    before = deepcopy(ledger)
    value = proposed()
    result = sync.select_account_activities([value, value], ledger, now=NOW)
    assert result.activities == (value,)
    assert result.duplicates == 1
    result = sync.select_account_activities([value, replace(value, quantity=Decimal(5))], ledger, now=NOW)
    assert result.activities == ()
    assert result.errors == ("owned_activity_conflict",)
    future = replace(value, date="2099-01-01T00:00:00Z", comment=value.comment + "future")
    result = sync.select_account_activities([future, value], ledger, now=NOW)
    assert result.activities == (value,)
    assert result.errors == ("future_activity",)
    assert ledger == before


def test_row_namespace_ignores_rendering_and_retains_multiplicity():
    notice = notices.parse_text(FIXTURE.read_text())
    reformatted = notices.parse_text(FIXTURE.read_text().replace("25.50", "25.500"))
    assert sync.notice_namespace(notice) == sync.notice_namespace(reformatted)
    assert sync.notice_namespace(notice) != sync.notice_namespace(replace(notice, buys=notice.buys * 2))


def test_activity_read_uses_exact_wire_numbers_and_one_full_request(monkeypatch):
    # The fractional value is transmitted as JSON numeric text, never a float adapter.
    body = json.dumps({"count": 1, "activities": [existing_row(unitPrice=1)]})
    body = body.replace('"unitPrice": 1', '"unitPrice": 0.12345678901234567890123456789')
    response = Mock(status_code=200, content=body.encode())
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    settings = Mock(ghost_host="http://ghostfolio.test")
    ledger = ghostfolio.read_activities(settings, "offline")
    assert ledger.rows[0].unit_price == Decimal("0.12345678901234567890123456789")
    assert get.call_count == 1
    assert get.call_args.args == ("http://ghostfolio.test/api/v1/activities",)
    assert get.call_args.kwargs["allow_redirects"] is False
    assert "params" not in get.call_args.kwargs


def test_invalid_source_stops_before_target_authentication(monkeypatch, caplog):
    settings = Mock(dry_run=True, mapping_file="", bd_account_ref="TESTACCOUNT")
    monkeypatch.setattr(app.config, "load", lambda: settings)
    monkeypatch.setattr(paperless, "document_ids", lambda _: [1])
    monkeypatch.setattr(paperless, "original_pdf", lambda *_: b"original")
    monkeypatch.setattr(notices, "extract_text", lambda _: FIXTURE.read_text().replace("COMPTE", "MISSING"))
    post = Mock(side_effect=AssertionError("unexpected authentication"))
    monkeypatch.setattr(requests, "post", post)
    assert app.main() == 1
    assert post.call_count == 0
    assert "notice_unreadable" in caplog.text

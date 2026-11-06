"""Exact EUR profile boundaries from the approved PDF contract."""

from decimal import Decimal

import pytest

from ghostfolio_boursedirect_sync import activity_reconciliation as rules


@pytest.mark.parametrize("name,source,target,allowed", [
    ("conservative", "10", "10", True), ("conservative", "10", "10.00000001", False),
    ("balanced", "10", "10.01", True), ("balanced", "1", "1.01", False),
    ("balanced", "100", "100.01000001", False),
    ("permissive", "100", "101", True), ("permissive", "99", "100", False),
    ("permissive", "1000", "1001.00000001", False),
])
def test_both_exact_gross_limits_must_pass(name, source, target, allowed):
    assert rules.gross_within_limits(name, Decimal(source), Decimal(target), "EUR") is allowed


@pytest.mark.parametrize("zone,target,allowed", [
    ("America/New_York", "2025-02-04T00:00:00Z", False),
    ("America/New_York", "2025-02-03T00:00:00Z", True),
    ("Pacific/Auckland", "2025-02-02T12:00:00Z", True),
    ("Pacific/Auckland", "2025-02-03T12:00:00Z", False),
])
def test_canonical_payment_day_compares_in_configured_timezone(zone, target, allowed):
    ok, context = rules.date_eligible("balanced", "2025-02-03T00:00:00Z", target, "BUY", zone)
    assert ok is allowed
    assert context["source local date"] == ("2025-02-02" if zone == "America/New_York" else "2025-02-03")


@pytest.mark.parametrize("kind,distance,allowed", [("BUY", 2, True), ("BUY", 3, False),
                                                    ("DIVIDEND", 3, True), ("DIVIDEND", 4, False)])
def test_profile_calendar_distance(kind, distance, allowed):
    assert rules.date_eligible("permissive", "2025-02-03T00:00:00Z",
                               f"2025-02-{3 + distance:02d}T00:00:00Z", kind, "UTC")[0] is allowed

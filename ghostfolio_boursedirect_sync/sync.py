"""Pure mapping and BUY conversion; pinned ibkr sync.py:58 and ghostfolio.py:64."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from ghostfolio_boursedirect_sync.ghostfolio import activity_instant, parse_identity
from ghostfolio_boursedirect_sync.models import (
    Activity,
    ActivityIndex,
    Buy,
    ExistingActivity,
    Notice,
    Selection,
)


def canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def buy_content(buy: Buy) -> str:
    return json.dumps(["BUY", buy.date.isoformat(), buy.isin,
                       *(canonical_decimal(v) for v in (buy.quantity, buy.unit_price, buy.fee)),
                       "EUR"], separators=(",", ":"))


def notice_namespace(notice: Notice) -> str:
    """BD adapter of source identity: rows, not regenerated PDF bytes.

    Legacy notice_identity uses normalized source fields (legacy-wip:4256).
    Sorting preserves duplicate multiplicity and removes page/row-order effects.
    """
    basis = json.dumps([notice.account_ref, sorted(buy_content(buy) for buy in notice.buys)],
                       separators=(",", ":"))
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def load_mapping(path: str) -> dict[str, str]:
    if not path:
        return {}
    try:
        data: object = yaml.safe_load(Path(path).read_text())
    except (OSError, ValueError, yaml.YAMLError):
        raise RuntimeError("invalid_mapping") from None
    if not isinstance(data, dict) or not isinstance(data.get("symbol_mapping"), dict):
        raise RuntimeError("invalid_mapping")
    raw = data["symbol_mapping"]
    if any(not isinstance(k, str) or not isinstance(v, str) or not v.strip() for k, v in raw.items()):
        raise RuntimeError("invalid_mapping")
    return dict(raw)


def activity(buy: Buy, mapping: dict[str, str], account_id: str, source_account: str,
             namespace: str, rank: int) -> Activity:
    symbol = mapping.get(buy.isin)
    if not symbol:
        raise RuntimeError("unresolved_security")
    content = f"{buy_content(buy)}|{rank}"
    key = hashlib.sha256(content.encode()).hexdigest()[:16]
    return Activity(
        account_id=account_id, symbol=symbol, date=f"{buy.date}T00:00:00+00:00",
        quantity=buy.quantity, unit_price=buy.unit_price, fee=buy.fee,
        comment=f"BD#v3#{source_account}:BUY:{namespace}.{key}",
        isin=buy.isin,
    )


def _same_activity(candidate: Activity, existing: ExistingActivity) -> bool:
    """Compare all Ghostfolio fields that define an owned activity."""
    return (
        existing.account_id == candidate.account_id
        and existing.date == activity_instant(candidate.date)
        and existing.type == candidate.type
        and existing.symbol == candidate.symbol
        and existing.data_source == candidate.data_source
        and existing.currency == candidate.currency
        and existing.quantity == candidate.quantity
        and existing.unit_price == candidate.unit_price
        and existing.fee == candidate.fee
    )


def _same_security(candidate: Activity, existing: ExistingActivity) -> bool:
    return existing.symbol == candidate.symbol or (
        candidate.isin is not None and existing.isin is not None and existing.isin == candidate.isin
    )


def _manual_match_kind(
    candidate: Activity,
    existing: ActivityIndex,
    consumed: set[str],
) -> str | None:
    """Return ``duplicate`` or ``possible_duplicate`` for target-account rows.

    Manual evidence is restricted to active YAHOO rows in the selected account.
    An existing row can satisfy one source row only, so identical source rows
    retain their multiplicity.
    """
    candidate_day = activity_instant(candidate.date)
    exact: list[tuple[int, ExistingActivity]] = []
    nearby: list[tuple[int, ExistingActivity]] = []
    for row in existing.rows:
        if row.id in consumed or row.account_id != candidate.account_id or not row.active:
            continue
        if row.comment.startswith("BD#v3#"):
            continue
        if row.type != candidate.type or row.data_source != candidate.data_source:
            continue
        if not _same_security(candidate, row):
            continue
        distance = abs((row.date.date() - candidate_day.date()).days)
        if distance > 2:
            continue
        nearby.append((distance, row))
        if row.quantity == candidate.quantity and row.unit_price == candidate.unit_price:
            exact.append((int(distance), row))
    if exact:
        _, row = min(exact, key=lambda item: (item[0], item[1].id))
        consumed.add(row.id)
        return "duplicate"
    if nearby:
        return "possible_duplicate"
    return None


def _manual_sort_key(candidate: Activity, existing: ActivityIndex) -> tuple[int, str, str]:
    """Process the closest exact manual candidates first."""
    day = activity_instant(candidate.date).date()
    distances = [
        abs((row.date.date() - day).days)
        for row in existing.rows
        if row.account_id == candidate.account_id and row.active
        and not row.comment.startswith("BD#v3#")
        and row.type == candidate.type and row.data_source == candidate.data_source
        and _same_security(candidate, row)
        and row.quantity == candidate.quantity and row.unit_price == candidate.unit_price
        and abs((row.date.date() - day).days) <= 2
    ]
    return (min(distances, default=3), candidate.date, candidate.comment)


def select_account_activities(
    candidates: list[Activity], existing: ActivityIndex, *, now: datetime | None = None,
) -> Selection:
    """IBKR app.py:234: select using isolated input, with no HTTP or dispatch.

    This first BUY slice handles owned identities and source copies. Manual
    proximity matching is added in task 4.1; no writer exists before task 6.1.
    """
    instant = now or datetime.now(UTC)
    proposals: dict[str, Activity] = {}
    conflicts: set[str] = set()
    errors: list[str] = []
    duplicates = 0
    consumed_manual: set[str] = set()
    manual_matches: dict[str, Activity] = {}
    ordered_candidates = sorted(candidates, key=lambda item: _manual_sort_key(item, existing))
    for candidate in ordered_candidates:
        if not parse_identity(candidate.comment, candidate.type):
            raise RuntimeError("invalid_identity")
        if activity_instant(candidate.date) > instant:
            errors.append("future_activity")
            continue
        previous = proposals.get(candidate.comment)
        if previous is not None:
            if previous == candidate:
                duplicates += 1
            else:
                conflicts.add(candidate.comment)
                errors.append("owned_activity_conflict")
            continue
        manual_previous = manual_matches.get(candidate.comment)
        if manual_previous is not None:
            if manual_previous == candidate:
                duplicates += 1
            else:
                errors.append("owned_activity_conflict")
            continue
        occupied = existing.identities.get(candidate.comment, ())
        if occupied:
            if len(occupied) == 1 and _same_activity(candidate, occupied[0]):
                duplicates += 1
            else:
                errors.append("owned_activity_conflict")
            continue
        manual = _manual_match_kind(candidate, existing, consumed_manual)
        if manual == "duplicate":
            duplicates += 1
            manual_matches[candidate.comment] = candidate
            continue
        if manual == "possible_duplicate":
            errors.append("possible_duplicate")
            continue
        proposals[candidate.comment] = candidate
    selected = tuple(sorted((a for key, a in proposals.items() if key not in conflicts),
                            key=lambda a: (a.date, a.comment)))
    return Selection(selected, duplicates, tuple(errors))

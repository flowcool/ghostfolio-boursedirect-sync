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
    )


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
    for candidate in candidates:
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
        occupied = existing.identities.get(candidate.comment, ())
        if occupied:
            if len(occupied) == 1 and (
                occupied[0].account_id, occupied[0].date, occupied[0].type,
                occupied[0].symbol, occupied[0].data_source, occupied[0].currency,
                occupied[0].quantity, occupied[0].unit_price, occupied[0].fee,
            ) == (
                candidate.account_id, activity_instant(candidate.date), candidate.type,
                candidate.symbol, candidate.data_source, candidate.currency,
                candidate.quantity, candidate.unit_price, candidate.fee,
            ):
                duplicates += 1
            else:
                errors.append("owned_activity_conflict")
            continue
        proposals[candidate.comment] = candidate
    selected = tuple(sorted((a for key, a in proposals.items() if key not in conflicts),
                            key=lambda a: (a.date, a.comment)))
    return Selection(selected, duplicates, tuple(errors))

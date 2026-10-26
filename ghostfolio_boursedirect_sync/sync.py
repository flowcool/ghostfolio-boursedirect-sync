"""Pure mapping and trade conversion; pinned ibkr sync.py:58 and ghostfolio.py:64."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from heapq import heappop, heappush
from pathlib import Path

import yaml

from ghostfolio_boursedirect_sync.ghostfolio import activity_instant, parse_identity
from ghostfolio_boursedirect_sync.models import (
    Activity,
    ActivityIndex,
    ExistingActivity,
    Notice,
    Selection,
    Trade,
)


def canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def trade_content(trade: Trade) -> str:
    return json.dumps([trade.type, trade.date.isoformat(), trade.isin,
                       *(canonical_decimal(v) for v in (trade.quantity, trade.unit_price, trade.fee)),
                       "EUR"], separators=(",", ":"))


def notice_namespace(notice: Notice) -> str:
    """BD adapter of source identity: rows, not regenerated PDF bytes.

    Legacy notice_identity uses normalized source fields (legacy-wip:4256).
    Sorting preserves duplicate multiplicity and removes page/row-order effects.
    """
    basis = json.dumps([notice.account_ref, sorted(trade_content(trade) for trade in notice.trades)],
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


def activity(trade: Trade, mapping: dict[str, str], account_id: str, source_account: str,
             namespace: str, rank: int) -> Activity:
    symbol = mapping.get(trade.isin)
    if not symbol:
        raise RuntimeError("unresolved_security")
    content = f"{trade_content(trade)}|{rank}"
    key = hashlib.sha256(content.encode()).hexdigest()[:16]
    return Activity(
        account_id=account_id, symbol=symbol, date=f"{trade.date}T00:00:00+00:00",
        quantity=trade.quantity, unit_price=trade.unit_price, fee=trade.fee,
        comment=f"BD#v3#{source_account}:{trade.type}:{namespace}.{key}",
        isin=trade.isin, type=trade.type,
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


def _manual_rows(
    candidate: Activity, existing: ActivityIndex, consumed: set[str],
) -> list[tuple[int, ExistingActivity]]:
    candidate_day = activity_instant(candidate.date)
    matches: list[tuple[int, ExistingActivity]] = []
    for row in existing.rows:
        if row.id in consumed or row.account_id != candidate.account_id or not row.active:
            continue
        if row.comment.startswith("BD#v3#"):
            continue
        if row.type != candidate.type or row.data_source != candidate.data_source:
            continue
        if candidate.type == "DIVIDEND" and row.currency != candidate.currency:
            continue
        if not _same_security(candidate, row):
            continue
        distance = abs((row.date.date() - candidate_day.date()).days)
        if distance > (3 if candidate.type == "DIVIDEND" else 2):
            continue
        matches.append((distance, row))
    return matches


def _manual_exact(candidate: Activity, row: ExistingActivity) -> bool:
    """BD net-cash adaptation of pinned IBKR sync.py:718; no float tolerance."""
    if candidate.type != "DIVIDEND":
        return row.quantity == candidate.quantity and row.unit_price == candidate.unit_price
    with localcontext() as context:
        context.prec = max(28, sum(len(format(v, "f")) for v in (
            row.quantity, row.unit_price, row.fee, candidate.quantity, candidate.unit_price)) + 2)
        return row.quantity * row.unit_price - row.fee == candidate.quantity * candidate.unit_price


def _manual_assignment(
    matches: list[list[tuple[int, ExistingActivity]]], candidates: list[Activity],
) -> dict[int, str]:
    """Solve independent groups separately; only exact shared rows connect them."""
    exact = [[(distance, row) for distance, row in group
              if _manual_exact(candidate, row)]
             for candidate, group in zip(candidates, matches, strict=True)]
    by_row: dict[str, list[int]] = {}
    for i, group in enumerate(exact):
        for _, row in group:
            by_row.setdefault(row.id, []).append(i)
    pending = {i for i, group in enumerate(exact) if group}
    seen_rows: set[str] = set()
    assigned: dict[int, str] = {}
    for seed in range(len(candidates)):
        if seed not in pending:
            continue
        stack = [seed]
        members = []
        while stack:
            i = stack.pop()
            if i not in pending:
                continue
            pending.remove(i)
            members.append(i)
            for _, row in exact[i]:
                if row.id not in seen_rows:
                    seen_rows.add(row.id)
                    stack.extend(by_row[row.id])
        members.sort()
        if len(members) == 1:
            i = members[0]
            _, row = min(exact[i], key=lambda item: (item[0], item[1].date, item[1].id))
            assigned[i] = row.id
        else:
            local = _assign_manual_component([exact[i] for i in members],
                                             [candidates[i] for i in members])
            assigned.update((members[i], row_id) for i, row_id in local.items())
    return assigned


def _assign_manual_component(
    matches: list[list[tuple[int, ExistingActivity]]], candidates: list[Activity],
) -> dict[int, str]:
    """BD adaptation of IBKR sync.py:546,623; approved maximum/minimum-distance rule.

    Unit-capacity residual paths maximize one-to-one matches. Shortest paths
    minimize total calendar-day distance. Potentials keep reverse costs usable
    with Dijkstra; stable node order resolves equal-cost assignments.
    """
    rows = sorted({row.id: row for group in matches for _, row in group}.values(),
                  key=lambda row: (row.date, row.id))
    offset = len(candidates) + 1
    row_nodes = {row.id: offset + i for i, row in enumerate(rows)}
    sink = offset + len(rows)
    graph: list[list[tuple[int, int]]] = [[] for _ in range(sink + 1)]
    residual: set[tuple[int, int]] = set()
    for i, group in enumerate(matches, 1):
        graph[0].append((i, 0))
        graph[i].append((0, 0))
        residual.add((0, i))
        for distance, row in sorted(group, key=lambda item: (item[0], item[1].date, item[1].id)):
            if not _manual_exact(candidates[i - 1], row):
                continue
            target = row_nodes[row.id]
            graph[i].append((target, distance))
            graph[target].append((i, -distance))
            residual.add((i, target))
    for target in row_nodes.values():
        graph[target].append((sink, 0))
        graph[sink].append((target, 0))
        residual.add((target, sink))
    potentials = [0] * len(graph)
    while True:
        distances = {0: 0}
        previous: dict[int, int] = {}
        queue = [(0, 0)]
        while queue:
            cost, node = heappop(queue)
            if cost != distances[node]:
                continue
            for target, weight in graph[node]:
                if (node, target) not in residual:
                    continue
                distance = cost + weight + potentials[node] - potentials[target]
                if target not in distances or distance < distances[target]:
                    distances[target] = distance
                    previous[target] = node
                    heappush(queue, (distance, target))
        if sink not in distances:
            break
        for node, distance in distances.items():
            potentials[node] += distance
        node = sink
        while node:
            parent = previous[node]
            residual.remove((parent, node))
            residual.add((node, parent))
            node = parent
    ids = {node: row_id for row_id, node in row_nodes.items()}
    return {i - 1: ids[target] for i in range(1, offset)
            for target, _ in graph[i] if target in ids and (target, i) in residual}


def select_account_activities(
    candidates: list[Activity], existing: ActivityIndex, *, now: datetime | None = None,
) -> Selection:
    """IBKR app.py:234: isolated selection with BD exact manual assignment."""
    instant = now or datetime.now(UTC)
    unique: dict[str, Activity] = {}
    conflicts: set[str] = set()
    errors: list[str] = []
    duplicates = 0
    for candidate in sorted(candidates, key=lambda item: (item.date, item.comment)):
        if not parse_identity(candidate.comment, candidate.type):
            raise RuntimeError("invalid_identity")
        if activity_instant(candidate.date) > instant:
            errors.append("future_activity")
            continue
        previous = unique.get(candidate.comment)
        if previous is not None:
            if previous == candidate:
                duplicates += 1
            else:
                conflicts.add(candidate.comment)
                errors.append("owned_activity_conflict")
            continue
        occupied = existing.identities.get(candidate.comment, ())
        if occupied:
            if len(occupied) == 1 and _same_activity(candidate, occupied[0]):
                duplicates += 1
            else:
                errors.append("owned_activity_conflict")
            continue
        unique[candidate.comment] = candidate
    pending = [item for key, item in unique.items() if key not in conflicts]
    # One ledger scan per unique eligible source, including non-exact nearby rows.
    matches = [_manual_rows(candidate, existing, set()) for candidate in pending]
    assigned = _manual_assignment(matches, pending)
    duplicates += len(assigned)
    selected = []
    consumed = set(assigned.values())
    for i, candidate in enumerate(pending):
        if i in assigned:
            continue
        if any(row.id not in consumed for _, row in matches[i]):
            errors.append("possible_duplicate")
        else:
            selected.append(candidate)
    # IBKR sync.py:580,960 checks net holdings after duplicates are removed.
    # BD uses exact chronological running quantities, SELL first on equal dates.
    # This is a simulation only. Task 6.1 must advance real holdings on readback.
    positions = dict(existing.positions)
    guarded = []
    for candidate in sorted(selected, key=lambda a: (a.date, a.type != "SELL", a.comment)):
        if candidate.type in ("BUY", "SELL"):
            key = (candidate.account_id, candidate.symbol)
            current = positions.get(key, Decimal(0))
            with localcontext() as context:
                context.prec = max(28, len(format(current, "f")) + len(format(candidate.quantity, "f")) + 2)
                remaining = (current - candidate.quantity if candidate.type == "SELL"
                             else current + candidate.quantity)
            if candidate.type == "SELL" and remaining < 0:
                errors.append("sell_exceeds_holding")
                continue
            positions[key] = remaining
        guarded.append(candidate)
    return Selection(tuple(guarded), duplicates, tuple(errors))

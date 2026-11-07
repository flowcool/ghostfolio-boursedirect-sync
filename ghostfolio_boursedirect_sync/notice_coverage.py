"""Read-only available-notice diagnosis; approved BD-specific adaptation.

Reuses IBKR 23cb762 activity_reconciliation.py exact interval arithmetic and
activity_review.py candidate evidence. Selection is never proof of absence.
"""

import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from ghostfolio_boursedirect_sync import activity_reconciliation as rules
from ghostfolio_boursedirect_sync import activity_review as review
from ghostfolio_boursedirect_sync import sync
from ghostfolio_boursedirect_sync.models import (
    Activity,
    ActivityIndex,
    DocumentReference,
    Notice,
    Trade,
)

log = logging.getLogger(__name__)


def report(matching: list[tuple[DocumentReference, Notice]], mapping: dict[str, str], account: str,
           existing: ActivityIndex, codes: set[str], actions: dict[str, set[str]],
           timezone: str, *, incomplete: bool = False, unreadable: int = 0) -> dict[str, int]:
    """Keep every supported logical row, including rows a sell guard would hold."""
    counts: Counter[str] = Counter()
    zone = ZoneInfo(timezone)
    if unreadable:
        counts["unreadable"] = unreadable
    unique: dict[str, Activity] = {}
    documents: dict[str, DocumentReference] = {}
    unverified: set[str] = set()
    for document, notice in matching:
        for stop in notice.stops:
            counts["unsupported"] += 1
            if stop.isin:
                unverified.add(stop.isin)
            else:
                incomplete = True
            log.info("Notice coverage: document=%s unsupported=%s isin=%s",
                     document, stop.code, stop.isin)
        ranks: Counter[Trade] = Counter()
        for trade in notice.trades:
            rank = ranks[trade]
            ranks[trade] += 1
            if trade.isin not in mapping:
                counts["unresolved association"] += 1
                unverified.add(trade.isin)
                log.warning("Notice coverage: document=%s date=%s type=%s isin=%s unresolved security",
                            document, trade.date, trade.type, trade.isin)
                continue
            event = sync.activity(trade, mapping, account, notice.account_ref,
                                  sync.notice_namespace(notice), rank)
            previous = unique.get(event.comment)
            if previous is not None and previous != event:
                raise RuntimeError("owned_activity_conflict")
            unique[event.comment] = event
            documents.setdefault(event.comment, document)
    events = review.source_events(list(unique.values()), "coverage", {})
    raw = list(existing.raw_rows)
    manual = review.manual_history_pairs(events, raw, timezone)
    for key, event in unique.items():
        exact = list(existing.identities.get(key, ()))
        legacy = [row for row in existing.rows if row.account_id == account
                  and row.comment.split("\n", 1)[0] in events.get(key, {}).get("legacy", [])]
        if review.instant(event.date) > datetime.now(UTC):
            codes.add("future_activity")
        nearby = [row for row in existing.rows if row.account_id == account and row.active
                  and row.type == event.type and sync._same_security(event, row)
                  and abs((row.date.astimezone(zone).date() - review.instant(event.date).astimezone(zone).date()).days)
                  <= (31 if event.type == "DIVIDEND" else 2)
                  and not row.comment.startswith("BD#v3#")]
        aliases = sync.unresolved_alias_rows(event, existing)
        candidates = exact or legacy or nearby or aliases
        if not candidates:
            classification = "absent supported"
            codes.add("coverage_gap")
            actions.setdefault("coverage_gap", set()).add(key)
        elif len(candidates) != 1:
            classification = "unresolved association"
        else:
            row = candidates[0]
            _, context = rules.date_eligible("permissive", event.date, row.date.isoformat(), event.type, timezone, local_source=True)
            same_day = context.get("calendar distance") == "0"
            identical = (row.currency == event.currency and row.quantity == event.quantity
                         and row.unit_price == event.unit_price and row.fee == event.fee)
            if (row.account_id != account or not row.active or row.type != event.type
                    or row.data_source != event.data_source
                    or not sync._same_security(event, row)
                    or (row.isin and event.isin and row.isin != event.isin)):
                classification = "unresolved association"
            elif not exact and not legacy and not nearby and aliases:
                classification = "unresolved association"
            elif identical and same_day and (bool(exact) or (key, row.id) not in manual
                    or review.mutually_unique((key, row.id), manual)):
                classification = "conforming"
            elif (key, row.id) in manual and review.mutually_unique((key, row.id), manual):
                classification = "correction candidate"
            else:
                classification = "unresolved association"
        counts[classification] += 1
        if classification == "unresolved association":
            codes.add("coverage_unverifiable")
            actions.setdefault("coverage_unverifiable", set()).add(key)
        if classification == "unresolved association" and event.isin:
            unverified.add(event.isin)
        log.info("Notice coverage: %s document=%s event=%s date=%s type=%s symbol=%s "
                 "quantity=%s unitPrice=%s fee=%s currency=%s targets=%s",
                 classification, documents[key], key, event.date, event.type, event.symbol,
                 event.quantity, event.unit_price, event.fee, event.currency, [r.id for r in candidates])
    if unique:
        start = min(review.instant(event.date) for event in unique.values())
        end = max(review.instant(event.date) for event in unique.values()) + timedelta(days=1)
        with localcontext() as arithmetic:
            arithmetic.prec = rules.arithmetic_precision([a.quantity for a in unique.values()],
                                                      [r.quantity for r in existing.rows])
            for isin, symbol in sorted(mapping.items()):
                source = [a for a in unique.values() if a.isin == isin and a.type in ("BUY", "SELL")]
                if not source:
                    continue
                source_total = sum((a.quantity if a.type == "BUY" else -a.quantity for a in source), Decimal(0))
                target_total = sum((r.quantity if r.type == "BUY" else -r.quantity for r in existing.rows
                                    if r.account_id == account and r.active and r.symbol == symbol
                                    and r.type in ("BUY", "SELL") and start <= r.date < end), Decimal(0))
                difference = source_total - target_total
                log.info("Notice position: symbol=%s start_utc=%s end_utc_exclusive=%s source=%s destination=%s "
                         "unexplained_change=%s unverifiable=%s", symbol, start, end, source_total, target_total,
                         difference, incomplete or isin in unverified)
                if incomplete or isin in unverified:
                    counts["unverifiable positions"] += 1
                    continue
                if difference:
                    codes.add("position_mismatch")
                    actions.setdefault("position_mismatch", set()).add(symbol)
    log.info("Notice coverage summary: documents=%s rows=%s counts=%s incomplete=%s",
             len(matching) + unreadable, sum(len(n.trades) + len(n.stops) for _, n in matching), dict(counts), incomplete)
    log.info("Notice coverage information: only available notices were checked; empty periods, "
             "absolute statement holdings and opening acquisitions remain unverified. No action needed.")
    return dict(counts)

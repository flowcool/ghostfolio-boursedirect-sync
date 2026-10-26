"""One simulated notice run; pinned ibkr ghostfolio.py:459 supplies the log format."""

import hashlib
import json
import logging
import os
from collections import Counter

from ghostfolio_boursedirect_sync import (
    config,
    ghostfolio,
    notices,
    notify,
    outcome,
    paperless,
    sync,
)
from ghostfolio_boursedirect_sync.models import (
    Activity,
    ExistingActivity,
    Notice,
    Trade,
)

log = logging.getLogger(__name__)


def run_sync(errors: set[str], *, invalid_schedule: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    document_id: int | None = None
    created = 0
    corrected = 0
    other_accounts = unreadable = duplicates = 0
    try:
        if invalid_schedule:
            raise RuntimeError("invalid_configuration CRON")
        settings = config.load()
        level = os.environ.get("LOG_LEVEL", "INFO")
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise RuntimeError("invalid_configuration LOG_LEVEL")
        # HTTP-library debug logs can include credentials. Keep their level fixed.
        log.setLevel(level)
        if settings.dry_run:
            log.info("DRY RUN")
        mapping = sync.load_mapping(settings.mapping_file)
        other_accounts = 0
        unreadable = 0
        matching: list[tuple[int, Notice]] = []
        source: list[dict[str, int | str]] = []
        for document_id in paperless.document_ids(settings):
            pdf = paperless.original_pdf(settings, document_id)
            source.append({"id": document_id, "sha256": hashlib.sha256(pdf).hexdigest()})
            # IBKR app.py:564-573 isolates source failures; BD keeps readable previews.
            try:
                notice = notices.parse_text(notices.extract_text(pdf))
            except RuntimeError as exc:
                errors.add(str(exc).split()[0] if str(exc).split() else "unhandled_error")
                log.error("%s document=%s", exc, document_id)
                unreadable += 1
                continue
            if notice.account_ref != settings.bd_account_ref:
                other_accounts += 1
                continue
            notice, failed_ttf = sync.attribute_ttf_rows(notice)
            if failed_ttf:
                errors.add("ttf_attribution_failed")
                log.error("ttf_attribution_failed document=%s", document_id)
            if notice.custody_fees:
                log.warning("custody_fee_ignored document=%s rows=%s", document_id, notice.custody_fees)
            if notice.inferred_brokerages:
                log.info("brokerage_zero_inferred document=%s rows=%s", document_id, notice.inferred_brokerages)
            if notice.trades:
                matching.append((document_id, notice))
        if not matching:
            log.info("Summary: simulated=0 duplicates=0 other_account_notices=%s "
                     "unreadable_notices=%s created=0", other_accounts, unreadable)
            return int(unreadable > 0 or bool(errors))
        # IBKR app.py:151 verifies the source before any target-account lookup.
        token = ghostfolio.exchange_token(settings)
        account_id = ghostfolio.find_account(settings, token)
        existing = ghostfolio.read_activities(settings, token)
        # IBKR sync.py:92 gives explicit mappings priority. The approved BD
        # adaptation replaces the broker-symbol fallback with an ISIN lookup.
        unresolved: set[str] = set()
        for isin in sorted({trade.isin for _, notice in matching for trade in notice.trades}):
            if isin in mapping:
                continue
            symbol = ghostfolio.lookup_symbol(settings, token, isin)
            if symbol is None:
                unresolved.add(isin)
                errors.add("unresolved_security")
                # Pinned IBKR app.py:580: one mapping hint per ISIN.
                log.error("unresolved_security isin=%s symbol_mapping: '%s: <yahoo ticker>'",
                          isin, isin)
            else:
                mapping[isin] = symbol
        candidates: list[Activity] = []
        documents: dict[str, int] = {}
        for document_id, notice in matching:
            namespace = sync.notice_namespace(notice)
            ranks: Counter[Trade] = Counter()
            for trade in notice.trades:
                if trade.isin in unresolved:
                    continue
                rank = ranks[trade]
                ranks[trade] += 1
                activity = sync.activity(trade, mapping, account_id, settings.bd_account_ref, namespace, rank)
                candidates.append(activity)
                documents.setdefault(activity.comment, document_id)
        corrections: list[tuple[ExistingActivity, Activity]] = []
        correction_groups: dict[str, list[tuple[ExistingActivity, Activity]]] = {}
        reserved_existing_ids: set[str] = set()
        eligible: list[Activity] = []
        correction_duplicates = 0
        unique_candidates: list[Activity] = []
        seen_comments: set[str] = set()
        for candidate in candidates:
            if candidate.comment in seen_comments:
                correction_duplicates += 1
                continue
            seen_comments.add(candidate.comment)
            unique_candidates.append(candidate)
        for candidate in unique_candidates:
            occupied = existing.identities.get(candidate.comment, ())
            if len(occupied) > 1 or any(
                    row.account_id != candidate.account_id for row in occupied):
                errors.add("owned_activity_conflict")
                log.error("owned_activity_conflict")
                continue
            if occupied:
                owned = occupied[0]
                if (owned.date != ghostfolio.activity_instant(candidate.date)
                        or owned.type != candidate.type or owned.symbol != candidate.symbol
                        or owned.data_source != candidate.data_source
                        or owned.currency != candidate.currency
                        or owned.quantity != candidate.quantity
                        or owned.unit_price != candidate.unit_price):
                    errors.add("owned_activity_conflict")
                    log.error("owned_activity_conflict")
                    continue
            matches = [row for row in existing.rows
                       if row.active and row.account_id == candidate.account_id and row.type == "BUY"
                       and row.date == ghostfolio.activity_instant(candidate.date)
                       and row.symbol == candidate.symbol and row.quantity == candidate.quantity
                       and row.unit_price == candidate.unit_price and row.currency == candidate.currency
                       and (row.id == occupied[0].id if occupied
                            else not row.comment.startswith("BD#v3#"))
                       and (candidate.isin is None or row.isin is None or row.isin == candidate.isin)]
            if (occupied and candidate.type == "BUY" and candidate.brokerage is not None
                    and not any(row.id == occupied[0].id for row in matches)):
                errors.add("owned_activity_conflict")
                log.error("owned_activity_conflict")
                continue
            if occupied and candidate.type == "BUY" and candidate.brokerage is not None:
                matches = [occupied[0]]
            if len(matches) != 1 or candidate.type != "BUY" or candidate.brokerage is None:
                eligible.append(candidate)
                continue
            row = matches[0]
            if row.fee == candidate.fee:
                if row.id in reserved_existing_ids:
                    eligible.append(candidate)
                else:
                    correction_duplicates += 1
                    reserved_existing_ids.add(row.id)
            elif row.fee == candidate.brokerage:
                if row.id in reserved_existing_ids:
                    errors.add("owned_activity_conflict")
                    log.error("owned_activity_conflict")
                else:
                    correction_groups.setdefault(row.id, []).append((row, candidate))
            else:
                errors.add("owned_activity_conflict")
                log.error("owned_activity_conflict")
        for group in correction_groups.values():
            if len(group) == 1:
                corrections.extend(group)
                reserved_existing_ids.add(group[0][0].id)
            elif all(item[1] == group[0][1] for item in group[1:]):
                corrections.append(group[0])
                correction_duplicates += len(group) - 1
                reserved_existing_ids.add(group[0][0].id)
            else:
                errors.add("owned_activity_conflict")
                log.error("owned_activity_conflict")
        selected = sync.select_account_activities(
            eligible, existing, reserved_existing_ids=reserved_existing_ids)
        duplicates = selected.duplicates + correction_duplicates
        # Pinned IBKR ibkr.py:127 and ghostfolio.py:459 expose native DEBUG evidence.
        # BD binds originals instead of a Flex window; decimal strings stay exact.
        log.debug("LAB_EVIDENCE %s", json.dumps({"kind": "source", "value": source}))
        preview: list[dict[str, object]] = [{"accountId": a.account_id, "symbol": a.symbol, "date": a.date,
             "quantity": str(a.quantity), "unitPrice": str(a.unit_price), "fee": str(a.fee),
             "currency": a.currency, "type": a.type, "dataSource": a.data_source,
             "comment": a.comment} for a in selected.activities]
        preview.extend({"id": row.id, "comment": row.comment, "oldFee": str(row.fee),
                        "fee": str(activity.fee), "accountId": row.account_id,
                        "symbol": row.symbol, "date": row.date.isoformat(),
                        "type": row.type, "quantity": str(row.quantity),
                        "unitPrice": str(row.unit_price), "currency": row.currency,
                        "dataSource": row.data_source, "correction": True}
                       for row, activity in corrections)
        log.debug("LAB_EVIDENCE %s", json.dumps({"kind": "preview", "value": preview}))
        for code in selected.errors:
            errors.add(code)
            log.error("%s", code)
        for activity in selected.activities:
            log.info(
                    "%s document=%s date=%s type=%s symbol=%s quantity=%s "
                    "unitPrice=%s fee=%s currency=%s accountId=%s dataSource=%s comment=%s",
                    "[DRY RUN]" if settings.dry_run else "IMPORT",
                    documents[activity.comment], activity.date, activity.type, activity.symbol,
                    activity.quantity, activity.unit_price, activity.fee, activity.currency,
                    activity.account_id, activity.data_source, activity.comment,
            )
        has_errors = bool(selected.errors or unreadable > 0 or unresolved
                          or "ttf_attribution_failed" in errors
                          or "owned_activity_conflict" in errors)
        for row, activity in corrections:
            log.info("%s fee_correction id=%s fee=%s->%s comment=%s",
                     "[DRY RUN]" if settings.dry_run else "IMPORT",
                     row.id, row.fee, activity.fee, row.comment)
        blocking = has_errors if settings.dry_run else (unreadable > 0 or (has_errors and not selected.activities and not corrections))
        if blocking:
            log.info("Summary: simulated=%s duplicates=%s other_account_notices=%s unreadable_notices=%s created=0",
                     len(selected.activities) if settings.dry_run else 0, selected.duplicates, other_accounts, unreadable)
            return 1
        if settings.dry_run:
            log.info("Summary: simulated=%s duplicates=%s corrections=%s other_account_notices=%s unreadable_notices=%s created=0",
                     len(selected.activities), duplicates, len(corrections), other_accounts, unreadable)
            return 0
        # Confirm each row before a later SELL can depend on its quantity.
        for row, activity in corrections:
            ghostfolio.correct_activity_fee(settings, token, row, activity.fee)
            corrected += 1
        for activity in selected.activities:
            ghostfolio.import_activities(settings, token, [activity])
            created += 1
        log.info("Summary: simulated=0 duplicates=%s corrections=%s other_account_notices=%s unreadable_notices=%s created=%s",
                 duplicates, corrected, other_accounts, unreadable, created)
        return int(has_errors)
    except Exception as exc:
        # Pinned IBKR app.main catches unforeseen failures. Keep confirmed counts
        # here and omit unexpected exception text, which can contain credentials.
        message = str(exc) if isinstance(exc, RuntimeError) else "unhandled_error"
        errors.add(message.split()[0] if message.split() else "unhandled_error")
        log.error("%s document=%s", message, document_id)
        log.info("Summary: simulated=0 duplicates=%s corrections=%s other_account_notices=%s unreadable_notices=%s created=%s",
                 duplicates, corrected, other_accounts, unreadable, created)
        return 1


def main(*, invalid_schedule: bool = False) -> int:
    """Finalize once; BD simulation never loads notification settings (IBKR app.py:441)."""
    errors: set[str] = set()
    code = run_sync(errors, invalid_schedule=invalid_schedule)
    if code == 0 or os.environ.get("DRY_RUN", "1") != "0":
        return code
    try:
        settings = config.load_notification_config()
        if settings is None:
            return code
        status = notify.send_notification(settings, notify.NOTIFY_TITLE, outcome.failure_summary(errors))
        if status == "sent":
            log.info("Failure notification sent")
        elif status == "timeout":
            log.warning("Failure notification timed out (it may still arrive; not retried)")
        else:
            log.warning("Failure notification not delivered")
    except Exception:
        log.warning("Failure notification could not be sent")
    return code

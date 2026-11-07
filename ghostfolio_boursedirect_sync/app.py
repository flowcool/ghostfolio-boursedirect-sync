"""One simulated notice run; pinned ibkr ghostfolio.py:459 supplies the log format."""

import json
import logging
import os
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from ghostfolio_boursedirect_sync import (
    action_notifications,
    activity_review,
    config,
    ghostfolio,
    notice_coverage,
    notice_source,
    notices,
    notify,
    outcome,
    paperless,
    sync,
)
from ghostfolio_boursedirect_sync.models import (
    Activity,
    DocumentReference,
    Notice,
    Trade,
)

log = logging.getLogger(__name__)


def run_sync(errors: set[str], *, invalid_schedule: bool = False,
             actions: dict[str, set[str]] | None = None) -> int:
    actions = {} if actions is None else actions
    document_id: DocumentReference | None = None
    created = 0
    held: set[str] = set()
    review_counts: dict[str, int] = {}
    corrected = 0
    other_accounts = unreadable = duplicates = 0
    excluded_rows = excluded_documents = 0
    blocking_unreadable = 0
    review_state: activity_review.ReviewState | None = None
    try:
        if invalid_schedule:
            raise RuntimeError("invalid_configuration CRON")
        settings = config.load()
        cutoff = settings.import_create_from
        log.info("Activity comparison TZ=%s; must match the Ghostfolio server TZ",
                 settings.timezone or "UTC")
        level = os.environ.get("LOG_LEVEL", "INFO")
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise RuntimeError("invalid_configuration LOG_LEVEL")
        if settings.dry_run:
            log.info("DRY RUN")
        mapping = sync.load_mapping(settings.mapping_file)
        other_accounts = 0
        unreadable = 0
        matching: list[tuple[DocumentReference, Notice]] = []
        source: list[dict[str, int | str]] = []
        acquired = notice_source.acquire(settings)
        if acquired.snapshot is not None:
            log.info("Folder source: source_files=%s distinct_documents=%s ignored_entries=%s",
                     acquired.snapshot.files, len(acquired.documents), acquired.snapshot.ignored)
        for document in acquired.documents:
            document_id = document.reference
            source.append({"id": document_id, "sha256": document.digest})
            # IBKR app.py:564-573 isolates source failures; BD keeps readable previews.
            try:
                if document.code or document.pdf is None:
                    raise RuntimeError(document.code or "notice_unreadable")
                notice = notices.parse_text(notices.extract_text(document.pdf))
            except RuntimeError as exc:
                unreadable += 1
                if cutoff and isinstance(document_id, int) and str(exc) == "notice_unreadable":
                    day = paperless.document_date(settings, document_id)
                    if day is not None and day < cutoff:
                        excluded_documents += 1
                        if settings.notice_coverage:
                            errors.add("notice_unreadable")
                        log.warning("Historical unreadable notice: document=%s code=notice_unreadable date=%s; "
                                 "excluded from normal writes; coverage incomplete", document_id, day)
                        continue
                message = outcome.redacted_failure(exc)
                errors.add(message.split()[0])
                log.error("%s document=%s", message, document_id)
                blocking_unreadable += 1
                continue
            if notice.account_ref != settings.bd_account_ref:
                other_accounts += 1
                continue
            if cutoff:
                excluded_rows += document.copies * sum(t.date < cutoff for t in notice.trades)
                if ((notice.trades or notice.stops) and all(t.date < cutoff for t in notice.trades)
                        and all(s.date is not None and s.date < cutoff for s in notice.stops)):
                    excluded_documents += document.copies
            original_ttf = notice.ttf_rows
            notice, failed_ttf = sync.attribute_ttf_rows(notice)
            if failed_ttf:
                if (cutoff and not settings.notice_coverage
                        and all(t.date < cutoff for t in original_ttf if t.isin in failed_ttf)):
                    log.warning("Historical TTF attribution failed: document=%s; affected historical BUYs dropped; not reviewed", document_id)
                else:
                    errors.add("ttf_attribution_failed")
                    log.error("ttf_attribution_failed document=%s", document_id)
            if notice.custody_fees:
                log.warning("custody_fee_ignored document=%s rows=%s", document_id, notice.custody_fees)
            if notice.inferred_brokerages:
                log.info("brokerage_zero_inferred document=%s rows=%s", document_id, notice.inferred_brokerages)
            if notice.trades or notice.stops or settings.notice_coverage:
                matching.append((document_id, notice))
        # IBKR app.py:203-208 filters rejected securities before dispatch.
        # BD stops span all selected notices, regardless of their read order.
        done = paperless.done_document_ids(settings) if not settings.notice_dir and any(n.stops for _, n in matching) else set()
        waivers = set(settings.notice_waivers)
        if settings.notice_dir:
            known = {d.reference for d in acquired.documents}
            log.info("Folder waivers: unknown_waiver_digests=%s",
                     len({digest for digest, _ in waivers} - known))
        blocked: set[str] = set()
        historical_blocked: set[str] = set()
        has_stops = False
        for document_id, notice in matching:
            if document_id in done:
                continue
            for stop in notice.stops:
                if (str(document_id), stop.code) in waivers:
                    continue
                if cutoff and stop.date is not None and stop.date < cutoff and not settings.notice_coverage:
                    log.warning("Historical unsupported row: code=%s document=%s date=%s", stop.code, document_id, stop.date)
                    if stop.isin is not None:
                        historical_blocked.add(stop.isin)
                    continue
                log.error("%s document=%s", stop.code, document_id)
                errors.add(stop.code)
                has_stops = True
                if stop.isin is not None:
                    blocked.add(stop.isin)
        if not any(t.isin not in blocked for _, n in matching for t in n.trades) and not settings.activity_review_file and not settings.notice_coverage:
            log.info("Summary: simulated=0 duplicates=0 other_account_notices=%s "
                     "unreadable_notices=%s created=0", other_accounts, unreadable)
            return int(blocking_unreadable > 0 or bool(errors))
        # IBKR app.py:151 verifies the source before any target-account lookup.
        token = ghostfolio.exchange_token(settings)
        account_id = ghostfolio.find_account(settings, token)
        existing = ghostfolio.read_activities(settings, token)
        # IBKR sync.py:92 gives explicit mappings priority. The approved BD
        # adaptation replaces the broker-symbol fallback with an ISIN lookup.
        unresolved: set[str] = set()
        blocking_unresolved: set[str] = set()
        current_isins = {t.isin for _, n in matching for t in n.trades if not cutoff or t.date >= cutoff}
        needed_isins = {trade.isin for _, notice in matching for trade in notice.trades
                        if not cutoff or trade.date >= cutoff or settings.activity_review_file or settings.notice_coverage}
        for isin in sorted(needed_isins):
            if isin in mapping or (isin in blocked and not settings.notice_coverage):
                continue
            symbol = ghostfolio.lookup_symbol(settings, token, isin)
            if symbol is None:
                unresolved.add(isin)
                if isin in current_isins or settings.notice_coverage:
                    blocking_unresolved.add(isin)
                    errors.add("unresolved_security")
                    # Pinned IBKR app.py:580: one mapping hint per ISIN.
                    log.error("unresolved_security isin=%s symbol_mapping: '%s: <yahoo ticker>'", isin, isin)
                else:
                    log.warning("Historical unresolved security: isin=%s; no creation; inspect mapping for review", isin)
            else:
                mapping[isin] = symbol
        candidates: list[Activity] = []
        documents: dict[str, DocumentReference] = {}
        source_documents: dict[str, set[DocumentReference]] = {}
        for document_id, notice in matching:
            namespace = sync.notice_namespace(notice)
            ranks: Counter[Trade] = Counter()
            for trade in notice.trades:
                rank = ranks[trade]
                ranks[trade] += 1
                if (trade.isin not in mapping or trade.isin in unresolved or trade.isin in blocked
                        or (cutoff and trade.date < cutoff and trade.isin in historical_blocked)
                        or (cutoff and trade.date < cutoff and not settings.activity_review_file)):
                    continue
                activity = sync.activity(trade, mapping, account_id, settings.bd_account_ref, namespace, rank)
                candidates.append(activity)
                documents.setdefault(activity.comment, document_id)
                source_documents.setdefault(activity.comment, set()).add(document_id)
        # Resolve source copies before review. Conflicting identical identities fail closed.
        unique: dict[str, Activity] = {}
        for candidate in candidates:
            previous = unique.get(candidate.comment)
            if previous is not None and previous != candidate:
                raise RuntimeError("owned_activity_conflict")
            if previous is not None and previous.legacy != candidate.legacy:
                candidate = replace(candidate, legacy=None)
            unique[candidate.comment] = candidate
        source_duplicates = len(candidates) - len(unique)
        log.debug("LAB_EVIDENCE %s", json.dumps({"kind": "source", "value": source}))
        notice_source.verify(settings, acquired)
        if settings.notice_coverage:
            notice_coverage.report(matching, mapping, account_id, existing, errors, actions,
                                   settings.timezone or "UTC", incomplete=bool(unreadable or unresolved
                                   or "ttf_attribution_failed" in errors), unreadable=unreadable)
            return int(bool(errors & outcome.FAILURE_CODES))
        if settings.activity_review_file and not blocking_unreadable:
            try:
                review_state = activity_review.open_review(
                    settings.activity_review_file, [p for p in (settings.mapping_file, settings.notice_dir,
                        settings.notice_waiver_file) if p])
                evidence = {candidate.comment: [entry for entry in source
                            if entry["id"] in source_documents[candidate.comment]] for candidate in unique.values()}
                events = activity_review.source_events(list(unique.values()), settings.bd_account_ref, evidence)
                result = activity_review.process_review(review_state, settings, token, events, account_id=account_id,
                                                        source_check=lambda: notice_source.verify(settings, acquired))
                errors.update(result.codes)
                held = result.held
                corrected = result.corrected
                review_counts = result.counts
                for item in review_state["document"]["proposals"].values():
                    if not activity_review.proposal_holds(item):
                        continue
                    if not item["actionable"]:
                        actions.setdefault("review_evidence", set()).add(item["source event"])
                    elif item["approve"] != "yes" and not item.get("automatic eligible"):
                        actions.setdefault("review_approval", set()).add(item["source event"])
                if result.blocked_accounts:
                    raise RuntimeError("import_unconfirmed")
                # Corrections can change holdings context. Never select imports on stale evidence.
                if corrected:
                    existing = ghostfolio.read_activities(settings, token)
            except (OSError, ValueError, RuntimeError) as exc:
                code = outcome.redacted_failure(exc).split()[0]
                if code not in ("import_unconfirmed", "activities_unavailable", "invalid_identity", "owned_activity_conflict",
                                "notice_source_unavailable", "notice_unreadable"):
                    code = "review_unavailable"
                raise RuntimeError(code) from None
        elif not settings.activity_review_file:
            events = activity_review.source_events(list(unique.values()), settings.bd_account_ref, {})
            manual_held = activity_review.manual_history_holds(
                events, list(existing.raw_rows), settings.timezone or "UTC")
            held.update(manual_held)
            if manual_held:
                errors.add("review_evidence")
                actions.setdefault("review_evidence", set()).update(manual_held)
            for candidate in unique.values():
                if sync.ttf_correction_matches(candidate, existing):
                    held.add(candidate.comment)
                    errors.add("review_evidence")
                    actions.setdefault("review_evidence", set()).add(candidate.comment)
                    log.warning("review_evidence scope=%s; BUY held; configure ACTIVITY_REVIEW_FILE "
                                "to retain correction evidence; independent imports continue", candidate.comment)
        for candidate in unique.values():
            if sync.unresolved_alias_rows(candidate, existing):
                held.add(candidate.comment)
                errors.add("review_evidence")
                actions.setdefault("review_evidence", set()).add(candidate.comment)
                log.warning("review_evidence scope=%s; unverified symbol association; inspect mapping; no write", candidate.comment)
        eligible = [candidate for candidate in unique.values() if candidate.comment not in held
                    and (not cutoff or activity_review.instant(candidate.date).date() >= cutoff)]
        selected = sync.select_account_activities(eligible, existing)
        duplicates = selected.duplicates + source_duplicates
        # Pinned IBKR ibkr.py:127 and ghostfolio.py:459 expose native DEBUG evidence.
        # BD binds originals instead of a Flex window; decimal strings stay exact.
        preview: list[dict[str, object]] = [{"accountId": a.account_id, "symbol": a.symbol, "date": a.date,
             "quantity": str(a.quantity), "unitPrice": str(a.unit_price), "fee": str(a.fee),
             "currency": a.currency, "type": a.type, "dataSource": a.data_source,
             "comment": a.comment} for a in selected.activities]
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
        has_errors = bool(selected.errors or blocking_unreadable > 0 or blocking_unresolved or has_stops
                          or "ttf_attribution_failed" in errors
                          or "owned_activity_conflict" in errors)
        blocking = has_errors if settings.dry_run else (blocking_unreadable > 0 or (has_errors and not selected.activities))
        if blocking:
            log.info("Summary: simulated=%s duplicates=%s other_account_notices=%s unreadable_notices=%s created=0",
                     len(selected.activities) if settings.dry_run else 0, selected.duplicates, other_accounts, unreadable)
            return 1
        if settings.dry_run:
            log.info("Summary: simulated=%s duplicates=%s corrections=%s other_account_notices=%s unreadable_notices=%s created=0",
                     len(selected.activities), duplicates, review_counts.get("would correct", 0), other_accounts, unreadable)
            return 0
        # Corrections have exact readback before ordinary additive imports.
        for activity in selected.activities:
            notice_source.verify(settings, acquired)
            ghostfolio.import_activities(settings, token, [activity])
            created += 1
        log.info("Summary: simulated=0 duplicates=%s corrections=%s other_account_notices=%s unreadable_notices=%s created=%s",
                 duplicates, corrected, other_accounts, unreadable, created)
        return int(has_errors)
    except Exception as exc:
        # Pinned IBKR app.main catches unforeseen failures. Keep confirmed counts
        # here and omit unexpected exception text, which can contain credentials.
        message = outcome.redacted_failure(exc)
        errors.add(message.split()[0])
        log.error("%s document=%s", message, document_id)
        if os.environ.get("NOTICE_COVERAGE") == "1" and message in ("notice_source_unavailable", "notice_unreadable"):
            log.error("Notice coverage: incomplete=True; source acquisition failed")
        log.info("Summary: simulated=0 duplicates=%s corrections=%s other_account_notices=%s unreadable_notices=%s created=%s",
                 duplicates, corrected, other_accounts, unreadable, created)
        return 1
    finally:
        log.info("Creation cut-off summary: excluded_rows=%s excluded_documents=%s",
                 excluded_rows, excluded_documents)
        log.info("Review summary: conforming=%s corrections=%s migrations=%s held=%s deferred=%s "
                 "would_correct=%s counts_available=%s counts_can_overlap=yes",
                 review_counts.get("already consistent", 0), corrected,
                 review_counts.get("reference migrations", 0), len(held),
                 review_counts.get("automatic work deferred", 0), review_counts.get("would correct", 0),
                 bool(review_counts))
        if review_state is not None:
            activity_review.close_review(review_state)


def main(*, invalid_schedule: bool = False) -> int:
    """Finalize once, including simulation (IBKR app.py:584)."""
    # IBKR f9a2b11 app.py:962-969 and 798-808.
    revision = os.environ.get("APP_REVISION", "")
    commit = revision[:12] if re.fullmatch(r"[0-9a-f]{40}", revision) else "unknown"
    log.info("ghostfolio-boursedirect-sync version %s — commit %s",
             os.environ.get("APP_VERSION") or "dev", commit)
    if not os.environ.get("DRY_RUN", "").strip():
        log.warning("DRY_RUN not set: simulation, nothing written")
    errors: set[str] = set()
    actions: dict[str, set[str]] = {}
    code = run_sync(errors, invalid_schedule=invalid_schedule, actions=actions)
    code = int(bool(code or errors & outcome.FAILURE_CODES))
    outcome.log_operational_result(errors, code)
    for reason in errors & outcome.ACTION_INSTRUCTIONS.keys():
        if reason not in actions:
            actions[reason] = {reason}
    protected = [Path(value) for value in (os.environ.get("MAPPING_FILE", ""),
                 os.environ.get("ACTIVITY_REVIEW_FILE", ""), os.environ.get("NOTICE_DIR", ""),
                 os.environ.get("NOTICE_WAIVER_FILE", "")) if value]
    context = activity_review.fingerprint([os.environ.get(key, "") for key in
        ("GHOST_HOST", "GHOST_ACCOUNT_NAME", "BD_ACCOUNT_REF", "PAPERLESS_URL")])
    plan = action_notifications.plan_action_notification(actions,
        os.environ.get("ACTIVITY_REVIEW_FILE") or None, context, inputs=protected,
        mode="coverage" if os.environ.get("NOTICE_COVERAGE") == "1" else "normal")
    if not code and not plan["due"]:
        log.info("Notification result: not required")
        return code
    try:
        settings = config.load_notification_config()
        if settings is None:
            log.warning("Notification result: disabled; configure APPRISE_URLS")
            return code
        summary = outcome.notification_summary(errors)
        details = [f"Action required: {reason} count={count}. {outcome.ACTION_INSTRUCTIONS[reason]}"
                   for reason, count in sorted(plan["document"]["groups"].items())]
        if not code:
            details.extend(f"Action cleared: {reason} count=0." for reason in plan["cleared"])
        if details:
            summary = "\n".join(([outcome.failure_summary(errors & outcome.FAILURE_CODES)] if code else []) + details)
        status = notify.send_notification(settings, notify.NOTIFY_TITLE, summary)
        if status == "sent":
            log.info("Failure notification sent" if code else "Action notification sent")
            if not code:
                action_notifications.confirm_action_notification(plan)
            log.info("Notification result: sent")
        elif status == "timeout":
            log.warning("Failure notification unconfirmed (timeout; not retried)")
            log.warning("Notification result: timeout, delivery unconfirmed")
        else:
            log.warning("Failure notification not delivered")
            log.warning("Notification result: failed")
    except Exception:
        log.warning("Failure notification could not be sent")
        log.warning("Notification result: invalid configuration or failed")
    return code

"""One simulated notice run; pinned ibkr ghostfolio.py:459 supplies the log format."""

import hashlib
import json
import logging
import os
from collections import Counter

from ghostfolio_boursedirect_sync import config, ghostfolio, notices, paperless, sync
from ghostfolio_boursedirect_sync.models import Activity, Notice, Trade

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    document_id: int | None = None
    created = 0
    other_accounts = unreadable = duplicates = 0
    try:
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
                log.error("%s document=%s", exc, document_id)
                unreadable += 1
                continue
            if notice.account_ref != settings.bd_account_ref:
                other_accounts += 1
                continue
            if notice.custody_fees:
                log.warning("custody_fee_ignored document=%s rows=%s", document_id, notice.custody_fees)
            if notice.trades:
                matching.append((document_id, notice))
        if not matching:
            log.info("Summary: simulated=0 duplicates=0 other_account_notices=%s "
                     "unreadable_notices=%s created=0", other_accounts, unreadable)
            return int(unreadable > 0)
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
        selected = sync.select_account_activities(candidates, existing)
        duplicates = selected.duplicates
        # Pinned IBKR ibkr.py:127 and ghostfolio.py:459 expose native DEBUG evidence.
        # BD binds originals instead of a Flex window; decimal strings stay exact.
        log.debug("LAB_EVIDENCE %s", json.dumps({"kind": "source", "value": source}))
        log.debug("LAB_EVIDENCE %s", json.dumps({"kind": "preview", "value": [
            {"accountId": a.account_id, "symbol": a.symbol, "date": a.date,
             "quantity": str(a.quantity), "unitPrice": str(a.unit_price), "fee": str(a.fee),
             "currency": a.currency, "type": a.type, "dataSource": a.data_source,
             "comment": a.comment} for a in selected.activities]}))
        for code in selected.errors:
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
        has_errors = bool(selected.errors or unreadable > 0 or unresolved)
        blocking = has_errors if settings.dry_run else (unreadable > 0 or (has_errors and not selected.activities))
        if blocking:
            log.info("Summary: simulated=%s duplicates=%s other_account_notices=%s unreadable_notices=%s created=0",
                     len(selected.activities) if settings.dry_run else 0, selected.duplicates, other_accounts, unreadable)
            return 1
        if settings.dry_run:
            log.info("Summary: simulated=%s duplicates=%s other_account_notices=%s unreadable_notices=%s created=0",
                     len(selected.activities), selected.duplicates, other_accounts, unreadable)
            return 0
        # Confirm each row before a later SELL can depend on its quantity.
        for activity in selected.activities:
            ghostfolio.import_activities(settings, token, [activity])
            created += 1
        log.info("Summary: simulated=0 duplicates=%s other_account_notices=%s unreadable_notices=%s created=%s",
                 selected.duplicates, other_accounts, unreadable, created)
        return int(has_errors)
    except RuntimeError as exc:
        # Package RuntimeErrors contain fixed codes/field names only.
        log.error("%s document=%s", exc, document_id)
        log.info("Summary: simulated=0 duplicates=%s other_account_notices=%s unreadable_notices=%s created=%s",
                 duplicates, other_accounts, unreadable, created)
        return 1

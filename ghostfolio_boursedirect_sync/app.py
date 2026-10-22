"""One simulated BUY run; pinned ibkr ghostfolio.py:459 supplies the log format."""

import hashlib
import json
import logging
import os
from collections import Counter

from ghostfolio_boursedirect_sync import config, ghostfolio, notices, paperless, sync
from ghostfolio_boursedirect_sync.models import Activity, Buy, Notice

log = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    document_id: int | None = None
    try:
        settings = config.load()
        level = os.environ.get("LOG_LEVEL", "INFO")
        if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            raise RuntimeError("invalid_configuration LOG_LEVEL")
        # HTTP-library debug logs can include credentials. Keep their level fixed.
        log.setLevel(level)
        if not settings.dry_run:
            raise RuntimeError("invalid_configuration financial import is not available")
        log.info("DRY RUN")
        mapping = sync.load_mapping(settings.mapping_file)
        other_accounts = 0
        matching: list[tuple[int, Notice]] = []
        source: list[dict[str, int | str]] = []
        for document_id in paperless.document_ids(settings):
            pdf = paperless.original_pdf(settings, document_id)
            source.append({"id": document_id, "sha256": hashlib.sha256(pdf).hexdigest()})
            notice = notices.parse_text(notices.extract_text(pdf))
            if notice.account_ref != settings.bd_account_ref:
                other_accounts += 1
                continue
            matching.append((document_id, notice))
        # IBKR app.py:151 verifies the source before any target-account lookup.
        token = ghostfolio.exchange_token(settings)
        account_id = ghostfolio.find_account(settings, token)
        existing = ghostfolio.read_activities(settings, token)
        candidates: list[Activity] = []
        documents: dict[str, int] = {}
        for document_id, notice in matching:
            namespace = sync.notice_namespace(notice)
            ranks: Counter[Buy] = Counter()
            for buy in notice.buys:
                rank = ranks[buy]
                ranks[buy] += 1
                activity = sync.activity(buy, mapping, account_id, settings.bd_account_ref, namespace, rank)
                candidates.append(activity)
                documents.setdefault(activity.comment, document_id)
        selected = sync.select_account_activities(candidates, existing)
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
                    "[DRY RUN] document=%s date=%s type=%s symbol=%s quantity=%s "
                    "unitPrice=%s fee=%s currency=%s accountId=%s dataSource=%s comment=%s",
                    documents[activity.comment], activity.date, activity.type, activity.symbol,
                    activity.quantity, activity.unit_price, activity.fee, activity.currency,
                    activity.account_id, activity.data_source, activity.comment,
            )
        log.info("Summary: simulated=%s duplicates=%s other_account_notices=%s created=0",
                 len(selected.activities), selected.duplicates, other_accounts)
        return int(bool(selected.errors))
    except RuntimeError as exc:
        # Package RuntimeErrors contain fixed codes/field names only.
        log.error("%s document=%s", exc, document_id)
        return 1

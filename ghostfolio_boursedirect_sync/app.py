"""One simulated BUY run; pinned ibkr ghostfolio.py:459 supplies the log format."""

import logging
import os
from collections import Counter

from ghostfolio_boursedirect_sync import config, ghostfolio, notices, paperless, sync
from ghostfolio_boursedirect_sync.models import Buy

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
        token = ghostfolio.exchange_token(settings)
        account_id = ghostfolio.find_account(settings, token)
        simulated = other_accounts = 0
        for document_id in paperless.document_ids(settings):
            pdf = paperless.original_pdf(settings, document_id)
            notice = notices.parse_text(notices.extract_text(pdf))
            if notice.account_ref != settings.bd_account_ref:
                other_accounts += 1
                continue
            ranks: Counter[Buy] = Counter()
            for buy in notice.buys:
                rank = ranks[buy]
                ranks[buy] += 1
                activity = sync.activity(buy, mapping, account_id, settings.bd_account_ref, pdf, rank)
                log.info(
                    "[DRY RUN] document=%s date=%s type=%s symbol=%s quantity=%s "
                    "unitPrice=%s fee=%s currency=%s accountId=%s dataSource=%s comment=%s",
                    document_id, activity.date, activity.type, activity.symbol,
                    activity.quantity, activity.unit_price, activity.fee, activity.currency,
                    activity.account_id, activity.data_source, activity.comment,
                )
                simulated += 1
        log.info("Summary: simulated=%s other_account_notices=%s created=0", simulated, other_accounts)
        return 0
    except RuntimeError as exc:
        # Package RuntimeErrors contain fixed codes/field names only.
        log.error("%s document=%s", exc, document_id)
        return 1

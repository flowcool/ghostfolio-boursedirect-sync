"""ENV-only configuration, adapted from pinned ibkr config.py:62-142."""

import json
import logging
import os
import re
from datetime import date
from typing import TypedDict
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ghostfolio_boursedirect_sync.models import Settings


def validate_origin(value: str, setting: str) -> str:
    """Validate configured destinations before sending any credential."""
    try:
        parts = urlsplit(value)
        valid_port = parts.port is None or parts.port > 0
    except ValueError:
        raise RuntimeError(f"invalid_configuration {setting}") from None
    if (
        not valid_port
        or parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or "?" in value
        or "#" in value
        or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == "\\" for c in value)
    ):
        raise RuntimeError(f"invalid_configuration {setting}")
    return value.rstrip("/")


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise RuntimeError(f"invalid_configuration {name}")
    return value


def load() -> Settings:
    """BD permits only the exact modes absent, 1 and 0."""
    raw_cutoff = os.environ.get("IMPORT_CREATE_FROM", "")
    cutoff = None
    if raw_cutoff:
        try:
            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw_cutoff) is None:
                raise ValueError
            cutoff = date.fromisoformat(raw_cutoff)
        except ValueError:
            raise RuntimeError("invalid_configuration IMPORT_CREATE_FROM") from None
    coverage = os.environ.get("NOTICE_COVERAGE", "0")
    if coverage not in ("0", "1"):
        raise RuntimeError("invalid_configuration NOTICE_COVERAGE")
    mode = os.environ.get("DRY_RUN", "1")
    if mode not in ("0", "1"):
        raise RuntimeError("invalid_configuration DRY_RUN")
    # BD rejects invalid optional settings before any service access (spec ENV).
    load_notification_config()
    token = os.environ.get("GHOST_TOKEN") or None
    access = os.environ.get("GHOST_ACCESS_TOKEN") or None
    if bool(token) == bool(access):
        raise RuntimeError("invalid_configuration GHOST_TOKEN or GHOST_ACCESS_TOKEN")
    for credential in (token, access):
        if credential is not None and re.fullmatch(r"[\x21-\x7e]+", credential) is None:
            raise RuntimeError("invalid_configuration Ghostfolio token")
    account = required("BD_ACCOUNT_REF")
    if re.fullmatch(r"[A-Za-z0-9]+", account) is None:
        raise RuntimeError("invalid_configuration BD_ACCOUNT_REF")
    done_tag = os.environ.get("PAPERLESS_DONE_TAG", "ghostfolio-done").strip()
    if not done_tag or any(ord(c) < 32 or ord(c) == 127 for c in done_tag):
        raise RuntimeError("invalid_configuration PAPERLESS_DONE_TAG")
    review_file = os.environ.get("ACTIVITY_REVIEW_FILE", "")
    profile = os.environ.get("ACTIVITY_RECONCILIATION", "off")
    if profile not in ("off", "conservative", "balanced", "permissive"):
        raise RuntimeError("invalid_configuration ACTIVITY_RECONCILIATION")
    if profile != "off" and not review_file:
        raise RuntimeError("invalid_configuration ACTIVITY_REVIEW_FILE")
    timezone = os.environ.get("TZ", "")
    if timezone or profile != "off":
        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise RuntimeError("invalid_configuration TZ") from None
    return Settings(
        ghost_host=validate_origin(required("GHOST_HOST"), "GHOST_HOST"),
        ghost_account_name=required("GHOST_ACCOUNT_NAME"),
        bd_account_ref=account,
        paperless_url=validate_origin(required("PAPERLESS_URL"), "PAPERLESS_URL"),
        paperless_token=required("PAPERLESS_TOKEN"),
        ghost_token=token,
        ghost_access_token=access,
        mapping_file=os.environ.get("MAPPING_FILE", ""),
        paperless_done_tag=done_tag,
        dry_run=mode != "0",
        activity_review_file=review_file,
        activity_reconciliation=profile,
        timezone=timezone,
        notice_coverage=coverage == "1",
        import_create_from=cutoff,
    )


NOTIFY_PAYLOAD_MAX = 32 * 1024
APPRISE_URLS_MAX = 10
APPRISE_URL_MAX_LEN = 2048
APPRISE_TIMEOUT_DEFAULT = 10
APPRISE_TIMEOUT_MAX = 30


class NotificationConfigDict(TypedDict):
    urls: list[str]
    timeout: int


def load_notification_config() -> NotificationConfigDict | None:
    """Parse APPRISE_URLS and APPRISE_TIMEOUT; None means notifications are off.

    APPRISE_URLS is a JSON list of Apprise URL strings (blank or [] = off);
    APPRISE_TIMEOUT an integer number of seconds, 1..30 (default 10).
    BD rejects invalid settings with a fixed field name, without their values.
    """
    raw = os.environ.get("APPRISE_URLS", "")
    try:
        urls = (json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None) if raw.strip() else []
    except ValueError:
        urls = None
    raw_timeout = os.environ.get("APPRISE_TIMEOUT", "").strip()
    timeout = APPRISE_TIMEOUT_DEFAULT
    if raw_timeout:
        timeout = int(raw_timeout) if re.fullmatch(r"[0-9]{1,2}", raw_timeout) else 0
    if not 1 <= timeout <= APPRISE_TIMEOUT_MAX:
        raise RuntimeError("invalid_configuration APPRISE_TIMEOUT")
    if (not isinstance(urls, list) or len(urls) > APPRISE_URLS_MAX
            or not all(isinstance(u, str) and u.strip() and len(u) <= APPRISE_URL_MAX_LEN
                       for u in urls)):
        raise RuntimeError("invalid_configuration APPRISE_URLS")
    if not urls:
        return None
    try:
        import apprise
        previous_disable = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        try:
            notifier = apprise.Apprise()
            valid = all(notifier.add(url) for url in urls) and len(notifier) <= APPRISE_URLS_MAX
        finally:
            logging.disable(previous_disable)
        if not valid:
            raise RuntimeError("invalid_configuration APPRISE_URLS")
    except ImportError:
        raise RuntimeError("invalid_configuration APPRISE_URLS") from None
    return {"urls": urls, "timeout": timeout}

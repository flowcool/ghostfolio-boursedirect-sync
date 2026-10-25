"""ENV-only configuration, adapted from pinned ibkr config.py:62-142."""

import os
import re
from urllib.parse import urlsplit

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
    mode = os.environ.get("DRY_RUN", "1")
    if mode not in ("0", "1"):
        raise RuntimeError("invalid_configuration DRY_RUN")
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
    )

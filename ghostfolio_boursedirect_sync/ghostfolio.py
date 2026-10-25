"""Read target accounts. Adapted from pinned ibkr ghostfolio.py:116,189.

Only token exchange uses POST. No financial write exists in this task.
"""

import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import cast

import requests

from ghostfolio_boursedirect_sync.models import (
    ActivityIndex,
    ExistingActivity,
    Settings,
)

INACTIVE_TAGS = {"0c077abd-eca2-4cbb-818c-6cefbf2d169a", "f2e868af-8333-459f-b161-cbc6544c24bd"}
log = logging.getLogger(__name__)


def activity_is_active(value: object) -> bool:
    """IBKR ghostfolio.py:152: validate flags/tags before applying eligibility."""
    if not isinstance(value, dict):
        raise RuntimeError("activities_unavailable")
    account = value.get("account")
    if account is None:
        account = {}
    if not isinstance(account, dict):
        raise RuntimeError("activities_unavailable")
    active = True
    for context in (value, account):
        for flag in ("isDraft", "isExcluded"):
            if flag in context:
                if type(context[flag]) is not bool:
                    raise RuntimeError("activities_unavailable")
                active = active and not context[flag]
        tags = context.get("tags", [])
        if not isinstance(tags, list):
            raise RuntimeError("activities_unavailable")
        for tag in tags:
            if not isinstance(tag, dict) or not isinstance(tag.get("id"), str) or not tag["id"].strip():
                raise RuntimeError("activities_unavailable")
            active = active and tag["id"] not in INACTIVE_TAGS
    return active


def parse_identity(comment: str, kind: str) -> bool:
    """IBKR ghostfolio.py:76; BD v1/v2 remain legacy manual-match evidence."""
    if not comment.startswith("BD#v"):
        return False
    if re.fullmatch(r"BD#v1#[A-Za-z0-9-]+#[0-9a-f]{64}", comment):
        return False
    if re.fullmatch(r"BD#v2#[0-9a-f]{64}#[0-9a-f]{64}", comment):
        return False
    match = re.fullmatch(r"BD#v3#[A-Za-z0-9]+:(BUY|SELL|DIVIDEND):[A-Za-z0-9._-]+", comment)
    if match is None or match[1] != kind:
        raise RuntimeError("invalid_identity")
    return True


def exact_number(value: object) -> Decimal:
    """Reject redaction, booleans and float-rounded adapters at the boundary."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise RuntimeError("activities_unavailable")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise RuntimeError("activities_unavailable")
    return result


def activity_instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("activities_unavailable")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise RuntimeError("activities_unavailable") from None
    if instant.tzinfo is None:
        raise RuntimeError("activities_unavailable")
    return instant


def index_existing_activities(data: object, *, now: datetime | None = None) -> ActivityIndex:
    """IBKR ghostfolio.py:259: complete evidence, global occupancy, active holdings.

    The BD adaptation keeps exact wire numbers in every mode, not only previews.
    Indexing performs no HTTP and never mutates caller-provided JSON.
    """
    if not isinstance(data, dict):
        raise RuntimeError("activities_unavailable")
    raw_rows, count = data.get("activities"), data.get("count")
    if not isinstance(raw_rows, list) or type(count) is not int or count != len(raw_rows):
        raise RuntimeError("activities_unavailable")
    instant = now or datetime.now(UTC)
    rows: list[ExistingActivity] = []
    identities: dict[str, list[ExistingActivity]] = defaultdict(list)
    positions: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    seen_ids: set[str] = set()
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise RuntimeError("activities_unavailable")
        comment = raw.get("comment")
        if comment is None:
            comment = ""
        kind, row_id = raw.get("type"), raw.get("id")
        account_id = raw.get("accountId")
        if account_id is None:
            account_id = ""
        if (not isinstance(comment, str) or not isinstance(kind, str) or not kind.strip()
                or not isinstance(row_id, str) or not row_id.strip() or row_id in seen_ids
                or not isinstance(account_id, str)):
            raise RuntimeError("activities_unavailable")
        seen_ids.add(row_id)
        owned = parse_identity(comment, kind)
        profile = raw["assetProfile"] if "assetProfile" in raw else raw.get("SymbolProfile")
        if kind in ("BUY", "SELL", "DIVIDEND"):
            if (not isinstance(profile, dict)
                    or any(not isinstance(profile.get(key), str) or not profile[key].strip()
                           for key in ("symbol", "dataSource"))):
                raise RuntimeError("activities_unavailable")
        elif not isinstance(profile, dict):
            profile = {}
        profile = cast(dict[str, object], profile)
        symbol = profile.get("symbol", "")
        source = profile.get("dataSource", "")
        isin = profile.get("isin")
        currency = raw.get("currency") or profile.get("currency")
        if (not isinstance(symbol, str) or not isinstance(source, str)
                or not isinstance(currency, str) or not currency.strip()
                or (isin is not None and not isinstance(isin, str))):
            raise RuntimeError("activities_unavailable")
        eligible = activity_is_active(raw)
        day = activity_instant(raw.get("date"))
        row = ExistingActivity(
            row_id, account_id, day, kind, exact_number(raw.get("quantity")),
            exact_number(raw.get("unitPrice")), exact_number(raw.get("fee")),
            currency, symbol, source, comment, isin,
            eligible and day <= instant and source == "YAHOO",
        )
        rows.append(row)
        if owned:
            identities[comment].append(row)
        if row.active and kind in ("BUY", "SELL"):
            key = (account_id, symbol)
            previous = positions[key]
            with localcontext() as context:
                context.prec = max(28, sum(len(v.as_tuple().digits) + abs(cast(int, v.as_tuple().exponent))
                                           for v in (previous, row.quantity)) + 2)
                positions[key] = previous + (-row.quantity if kind == "SELL" else row.quantity)
    return ActivityIndex(tuple(rows), {key: tuple(value) for key, value in identities.items()},
                         dict(positions))


def read_activities(settings: Settings, token: str) -> ActivityIndex:
    """IBKR ghostfolio.py:208: one full GET, count check and no response-URL trust."""
    try:
        response = requests.get(
            f"{settings.ghost_host}/api/v1/activities",
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 60), allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError("activities_unavailable") from None
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"activities_unavailable HTTP {response.status_code}")
    try:
        data: object = json.loads(response.content, parse_float=Decimal)
    except (ValueError, UnicodeError):
        raise RuntimeError("activities_unavailable") from None
    return index_existing_activities(data)


def lookup_symbol(settings: Settings, token: str, isin: str) -> str | None:
    """Approved BD adapter: legacy scripts/community_connect.py:92-100.

    The spec requires exactly one EUR result. Activities use YAHOO, so a
    different provider cannot supply the selected symbol. Never log API bodies.
    """
    try:
        response = requests.get(
            f"{settings.ghost_host}/api/v1/symbol/lookup",
            params={"query": isin}, headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 60), allow_redirects=False,
        )
    except requests.RequestException:
        log.warning("Security lookup failed isin=%s reason=transport", isin)
        return None
    # Pinned IBKR ghostfolio.py:562 reports HTTP failures; BD omits response bodies.
    if not 200 <= response.status_code < 300:
        log.warning("Security lookup failed isin=%s HTTP %s", isin, response.status_code)
        return None
    try:
        body: object = response.json()
    except ValueError:
        log.warning("Security lookup failed isin=%s reason=invalid_response", isin)
        return None
    items = body.get("items") if isinstance(body, dict) else None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        log.warning("Security lookup failed isin=%s reason=invalid_response", isin)
        return None
    eur = [item for item in items if item.get("currency") == "EUR"]
    if len(eur) != 1 or eur[0].get("dataSource") != "YAHOO":
        return None
    symbol = eur[0].get("symbol")
    if (not isinstance(symbol, str) or not symbol.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in symbol)):
        log.warning("Security lookup failed isin=%s reason=invalid_response", isin)
        return None
    return symbol


def exchange_token(settings: Settings) -> str:
    if settings.ghost_token is not None:
        return settings.ghost_token
    try:
        response = requests.post(
            f"{settings.ghost_host}/api/v1/auth/anonymous",
            json={"accessToken": settings.ghost_access_token},
            timeout=(10, 30),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError("invalid_configuration Ghostfolio authentication") from None
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"invalid_configuration HTTP {response.status_code}")
    try:
        body: object = response.json()
    except ValueError:
        raise RuntimeError("invalid_configuration Ghostfolio authentication") from None
    token = body.get("authToken") if isinstance(body, dict) else None
    if not isinstance(token, str) or re.fullmatch(r"[\x21-\x7e]+", token) is None:
        raise RuntimeError("invalid_configuration Ghostfolio authentication")
    return token


def find_account(settings: Settings, token: str) -> str:
    try:
        response = requests.get(
            f"{settings.ghost_host}/api/v1/account",
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 120),
            allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError("invalid_configuration Ghostfolio accounts") from None
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"invalid_configuration HTTP {response.status_code}")
    try:
        body: object = response.json()
    except ValueError:
        raise RuntimeError("invalid_configuration Ghostfolio accounts") from None
    accounts = body.get("accounts") if isinstance(body, dict) else body
    if not isinstance(accounts, list) or any(not isinstance(a, dict) for a in accounts):
        raise RuntimeError("invalid_configuration Ghostfolio accounts")
    matches = [a for a in accounts if a.get("name") == settings.ghost_account_name]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), str) or not matches[0]["id"]:
        raise RuntimeError("invalid_configuration GHOST_ACCOUNT_NAME")
    try:
        active = activity_is_active({"account": matches[0]})
    except RuntimeError:
        raise RuntimeError("invalid_configuration GHOST_ACCOUNT_NAME") from None
    if not active:
        raise RuntimeError("invalid_configuration GHOST_ACCOUNT_NAME")
    account_id: str = matches[0]["id"]
    return account_id

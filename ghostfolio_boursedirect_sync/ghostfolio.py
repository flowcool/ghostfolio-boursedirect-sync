"""Read target accounts. Adapted from pinned ibkr ghostfolio.py:116,189.

Only token exchange uses POST. No financial write exists in this task.
"""

import re

import requests

from ghostfolio_boursedirect_sync.models import Settings


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
    account_id: str = matches[0]["id"]
    return account_id

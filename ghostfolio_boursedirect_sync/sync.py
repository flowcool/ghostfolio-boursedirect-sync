"""Pure mapping and BUY conversion; pinned ibkr sync.py:58 and ghostfolio.py:64."""

import hashlib
from pathlib import Path

import yaml

from ghostfolio_boursedirect_sync.models import Activity, Buy


def load_mapping(path: str) -> dict[str, str]:
    if not path:
        return {}
    try:
        data: object = yaml.safe_load(Path(path).read_text())
    except (OSError, ValueError, yaml.YAMLError):
        raise RuntimeError("invalid_mapping") from None
    if not isinstance(data, dict) or not isinstance(data.get("symbol_mapping"), dict):
        raise RuntimeError("invalid_mapping")
    raw = data["symbol_mapping"]
    if any(not isinstance(k, str) or not isinstance(v, str) or not v.strip() for k, v in raw.items()):
        raise RuntimeError("invalid_mapping")
    return dict(raw)


def activity(buy: Buy, mapping: dict[str, str], account_id: str, source_account: str,
             pdf: bytes, rank: int) -> Activity:
    symbol = mapping.get(buy.isin)
    if not symbol:
        raise RuntimeError("unresolved_security")
    namespace = hashlib.sha256(pdf).hexdigest()[:16]
    content = f"{buy.date}|{buy.isin}|{buy.quantity}|{buy.unit_price}|{buy.fee}|{rank}"
    key = hashlib.sha256(content.encode()).hexdigest()[:16]
    return Activity(
        account_id=account_id, symbol=symbol, date=f"{buy.date}T00:00:00+00:00",
        quantity=buy.quantity, unit_price=buy.unit_price, fee=buy.fee,
        comment=f"BD#v3#{source_account}:BUY:{namespace}.{key}",
    )

"""Immutable records. Money stays Decimal through the simulation boundary."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Settings:
    ghost_host: str
    ghost_account_name: str
    bd_account_ref: str
    paperless_url: str
    paperless_token: str = field(repr=False)
    ghost_token: str | None = field(repr=False)
    ghost_access_token: str | None = field(repr=False)
    mapping_file: str
    dry_run: bool


@dataclass(frozen=True)
class Buy:
    date: date
    isin: str
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal


@dataclass(frozen=True)
class Notice:
    account_ref: str
    buys: tuple[Buy, ...]


@dataclass(frozen=True)
class Activity:
    account_id: str
    symbol: str
    date: str
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal
    comment: str
    type: str = "BUY"
    currency: str = "EUR"
    data_source: str = "YAHOO"


@dataclass(frozen=True)
class ExistingActivity:
    id: str
    account_id: str
    date: datetime
    type: str
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal
    currency: str
    symbol: str
    data_source: str
    comment: str
    isin: str | None
    active: bool


@dataclass(frozen=True)
class ActivityIndex:
    rows: tuple[ExistingActivity, ...]
    identities: dict[str, tuple[ExistingActivity, ...]]
    positions: dict[tuple[str, str], Decimal]


@dataclass(frozen=True)
class Selection:
    activities: tuple[Activity, ...]
    duplicates: int
    errors: tuple[str, ...]

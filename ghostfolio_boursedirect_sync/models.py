"""Immutable records. Money stays Decimal through the simulation boundary."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal


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
    paperless_done_tag: str
    dry_run: bool
    activity_review_file: str = ""
    activity_reconciliation: str = "off"
    timezone: str = ""
    notice_coverage: bool = False
    import_create_from: date | None = None
    notice_dir: str = ""
    notice_waiver_file: str = ""
    notice_waivers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class LegacyNoticeEvidence:
    account_ref: str
    fields: tuple[tuple[str, str], ...]
    occurrence: int


@dataclass(frozen=True)
class Trade:
    date: date
    isin: str
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal
    type: Literal["BUY", "SELL", "DIVIDEND"] = "BUY"
    brokerage: Decimal | None = None
    legacy: LegacyNoticeEvidence | None = field(default=None, compare=False, hash=False, repr=False)


@dataclass(frozen=True)
class TTF:
    date: date
    isin: str
    amount: Decimal


@dataclass(frozen=True)
class NoticeStop:
    code: Literal["share_count_change", "unknown_operation"]
    isin: str | None
    date: date | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Notice:
    account_ref: str
    trades: tuple[Trade, ...]
    custody_fees: int = 0
    inferred_brokerages: int = 0
    ttf_rows: tuple[TTF, ...] = ()
    stops: tuple[NoticeStop, ...] = ()


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
    isin: str | None = None
    brokerage: Decimal | None = None
    legacy: LegacyNoticeEvidence | None = field(default=None, compare=False, hash=False, repr=False)


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
    tags: tuple[str, ...] = ()
    comment_is_null: bool = False


@dataclass(frozen=True)
class ActivityIndex:
    rows: tuple[ExistingActivity, ...]
    identities: dict[str, tuple[ExistingActivity, ...]]
    positions: dict[tuple[str, str], Decimal]
    raw_rows: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Selection:
    activities: tuple[Activity, ...]
    duplicates: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class ReviewResult:
    held: set[str]
    blocked_accounts: set[str]
    corrected: int
    migrations: int
    codes: set[str]
    counts: dict[str, int]


DocumentReference = int | str


@dataclass(frozen=True)
class SourceDocument:
    reference: DocumentReference
    pdf: bytes | None
    digest: str
    code: str = ""
    copies: int = 1


@dataclass(frozen=True)
class FolderSnapshot:
    documents: tuple[SourceDocument, ...]
    files: int
    ignored: int
    evidence: tuple[tuple[str, tuple[int, ...], str], ...]
    root: tuple[int, ...]


@dataclass(frozen=True)
class Source:
    documents: tuple[SourceDocument, ...]
    snapshot: FolderSnapshot | None = None

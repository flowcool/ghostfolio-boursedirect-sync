"""BD statement adaptation approved in statement-cash-balance, decisions 1–2."""

import re
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, localcontext
from itertools import pairwise

from ghostfolio_boursedirect_sync.models import Statement, StatementMovement
from ghostfolio_boursedirect_sync.notices import ACCOUNT

TITLE = re.compile(r"^\s*RELEV[ÉE] DE COMPTE\s*$", re.I | re.M)
BALANCE = re.compile(r"^\s*Solde au\s*:\s*(\d{2}/\d{2}/\d{4})\b[^\n]*", re.M)
DAY = re.compile(r"^\s*(\d{2}/\d{2}/\d{4})\s+")
AMOUNT = re.compile(r"(?:[0-9]{1,3}(?: [0-9]{3})+|[0-9]+),[0-9]{2}")


def is_statement(text: str) -> bool:
    """Classify without reading amounts, including when cash is not managed."""
    return TITLE.search(text) is not None and len(BALANCE.findall(text)) == 2


def _date(value: str) -> date:
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        raise RuntimeError("statement_unreadable") from None


def _amount(line: str, debit_column: int, credit_column: int) -> Decimal | None:
    """Ignore quantity and price; only the cash columns can contain cash."""
    field = line[debit_column:].strip()
    if not field:
        return None
    if AMOUNT.fullmatch(field) is None:
        raise RuntimeError("statement_unreadable")
    value = Decimal(field.replace(" ", "").replace(",", "."))
    return value if len(line.rstrip()) > credit_column else value.copy_negate()


def parse_text(text: str) -> Statement:
    """Read a single EUR statement and require exact cent reconciliation."""
    if not is_statement(text):
        raise RuntimeError("statement_unreadable")
    account = account_ref(text)
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines)
               if re.fullmatch(r"\s*Date\s+Désignation\s+Débit \(€\)\s+Crédit \(€\)\s*", line)]
    balances = [i for i, line in enumerate(lines) if BALANCE.fullmatch(line)]
    if len(headers) != 1 or len(balances) != 2 or not headers[0] < balances[0] < balances[1]:
        raise RuntimeError("statement_unreadable")
    header = lines[headers[0]]
    debit, credit = header.index("Débit"), header.index("Crédit")
    days = [_date(BALANCE.findall(lines[i])[0]) for i in balances]
    amounts = [_amount(lines[i], debit, credit) for i in balances]
    opening, closing = amounts
    if opening is None or closing is None or days[0] >= days[1]:
        raise RuntimeError("statement_unreadable")
    movements = []
    movement_day = None
    movement_amount = None
    totals_seen = False
    for line in lines[balances[0] + 1:balances[1]]:
        if not line.strip():
            continue
        if re.fullmatch(r"\s*Cumul mouvements\s*:.*", line):
            totals_seen = True
            continue
        if totals_seen:
            raise RuntimeError("statement_unreadable")
        day = DAY.match(line)
        if day is not None:
            if movement_day is not None:
                movements.append(StatementMovement(movement_day, movement_amount or Decimal(0)))
            movement_day, movement_amount = _date(day[1]), None
        if movement_day is None or not days[0] < movement_day <= days[1]:
            raise RuntimeError("statement_unreadable")
        amount = _amount(line, debit, credit)
        if amount is not None:
            if movement_amount is not None:
                raise RuntimeError("statement_unreadable")
            movement_amount = amount
    if movement_day is not None:
        movements.append(StatementMovement(movement_day, movement_amount or Decimal(0)))
    with localcontext() as context:
        context.prec = max(28, sum(len(str(v)) for v in (opening, closing, *(m.amount for m in movements))) + 8)
        if opening + sum((m.amount for m in movements), Decimal(0)) != closing:
            raise RuntimeError("statement_unreadable")
    return Statement(account, days[0], opening, days[1], closing, tuple(movements))


def account_ref(text: str) -> str:
    """Apply the notice account rule without reading another account's amounts."""
    accounts = list(ACCOUNT.finditer(text))
    if len(accounts) != 1 or len(re.findall(r"\bCOMPTE\s+N[°º]", text, re.I)) != 1:
        raise RuntimeError("statement_unreadable")
    return accounts[0][1].replace(" ", "")


def validate_chain(statements: Sequence[Statement]) -> None:
    """Require consecutive periods and balances for a single source account."""
    ordered = sorted(statements, key=lambda statement: statement.closing_date)
    for previous, current in pairwise(ordered):
        if (current.account_ref != previous.account_ref
                or current.opening_date != previous.closing_date
                or current.opening_balance != previous.closing_balance):
            raise RuntimeError("statement_unreadable")

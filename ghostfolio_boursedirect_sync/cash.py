"""Statement cash adaptation approved in statement-cash-balance, decision 3."""

from collections.abc import Sequence
from decimal import Decimal, localcontext

from ghostfolio_boursedirect_sync import statements, sync
from ghostfolio_boursedirect_sync.models import CashBalance, Notice, Statement


def calculate(source: Sequence[Statement], notices: Sequence[Notice], account: str) -> CashBalance:
    """Use reconciled statements and checked source cash, independent of imports."""
    selected = {statement for statement in source if statement.account_ref == account}
    if not selected:
        raise RuntimeError("cash_unavailable")
    try:
        statements.validate_chain(list(selected))
    except RuntimeError:
        raise RuntimeError("cash_unavailable") from None
    latest = max(selected, key=lambda statement: statement.closing_date)
    amounts = [latest.closing_balance]
    seen: dict[str, Notice] = {}
    count = 0
    for notice in notices:
        if notice.account_ref != account:
            continue
        later = [trade for trade in notice.trades if trade.date > latest.closing_date]
        if not later:
            continue
        key = sync.notice_namespace(notice)
        if key in seen:
            if seen[key].ttf_rows != notice.ttf_rows:
                raise RuntimeError("cash_unavailable")
            continue
        seen[key] = notice
        _, failed = sync.attribute_ttf_rows(notice)
        if failed:
            raise RuntimeError("cash_unavailable")
        for trade in later:
            if trade.net_cash is None:
                raise RuntimeError("cash_unavailable")
            amounts.append(trade.net_cash)
        amounts.extend(tax.amount.copy_negate() for tax in notice.ttf_rows if tax.date > latest.closing_date)
        count += 1
    with localcontext() as context:
        context.prec = max(28, sum(len(str(value)) for value in amounts) + 8)
        amount = sum(amounts, Decimal(0))
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            raise RuntimeError("cash_unavailable")
        return CashBalance(latest.closing_date, count, amount.quantize(Decimal("0.01")))

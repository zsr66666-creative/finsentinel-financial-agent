"""Deterministic financial calculations. Values stay Decimal until serialization."""

from decimal import Decimal, InvalidOperation


def _decimal(value, name):
    if value is None:
        raise ValueError(f"{name} is missing")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} is not numeric") from exc


def calc_growth(current, previous):
    current = _decimal(current, "current")
    previous = _decimal(previous, "previous")
    if previous == 0:
        raise ValueError("previous value is zero; growth is undefined")
    if previous < 0:
        raise ValueError("previous value is negative; use absolute change and classify profit direction")
    return (current - previous) / previous * Decimal("100")


def calc_gross_margin(revenue, cost):
    revenue = _decimal(revenue, "revenue")
    cost = _decimal(cost, "cost")
    if revenue == 0:
        raise ValueError("revenue is zero; gross margin is undefined")
    return (revenue - cost) / revenue * Decimal("100")


def _average_balance(opening, closing):
    opening = _decimal(opening, "opening balance")
    closing = _decimal(closing, "closing balance")
    average = (opening + closing) / Decimal("2")
    if average == 0:
        raise ValueError("average balance is zero; turnover is undefined")
    return average


def calc_receivables_turnover(revenue, opening_receivables, closing_receivables):
    """Calculate revenue divided by average accounts receivable."""
    revenue = _decimal(revenue, "revenue")
    return revenue / _average_balance(opening_receivables, closing_receivables)


def calc_inventory_turnover(cost, opening_inventory, closing_inventory):
    """Calculate cost of revenue divided by average inventory."""
    cost = _decimal(cost, "cost")
    return cost / _average_balance(opening_inventory, closing_inventory)


def calc_cash_flow_quality(operating_cash_flow, consolidated_net_profit):
    """Return operating cash flow divided by consolidated net profit.

    Non-positive consolidated profit is intentionally rejected because the
    ratio should not be presented as a normal cash-flow quality score then.
    """
    cash_flow = _decimal(operating_cash_flow, "operating cash flow")
    profit = _decimal(consolidated_net_profit, "consolidated net profit")
    if profit <= 0:
        raise ValueError("consolidated net profit is non-positive; quality ratio is undefined")
    return cash_flow / profit

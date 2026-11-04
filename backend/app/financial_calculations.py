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

from decimal import Decimal

import pytest

from app.financial_calculations import (
    calc_cash_flow_quality,
    calc_growth,
    calc_gross_margin,
    calc_inventory_turnover,
    calc_receivables_turnover,
)


def test_growth_preserves_decimal_precision():
    assert calc_growth("174504335921.25", "124503174115.60").quantize(Decimal("0.01")) == Decimal("40.16")


def test_growth_handles_decline():
    assert calc_growth(80, 100) == Decimal("-20")


def test_growth_rejects_zero_and_negative_baselines():
    with pytest.raises(ValueError, match="zero"):
        calc_growth(3, 0)
    with pytest.raises(ValueError, match="negative"):
        calc_growth(3, -1)


def test_growth_rejects_missing_values():
    with pytest.raises(ValueError, match="missing"):
        calc_growth(None, 1)


def test_gross_margin_and_zero_revenue():
    assert calc_gross_margin(100, 60) == Decimal("40")
    with pytest.raises(ValueError, match="zero"):
        calc_gross_margin(0, 1)


def test_receivables_turnover_uses_average_balance():
    assert calc_receivables_turnover("120", "40", "80") == Decimal("2")


def test_inventory_turnover_uses_cost_not_revenue():
    assert calc_inventory_turnover("90", "30", "60") == Decimal("2")


def test_turnover_rejects_missing_period_or_zero_average():
    with pytest.raises(ValueError, match="missing"):
        calc_inventory_turnover("90", None, "60")
    with pytest.raises(ValueError, match="zero"):
        calc_receivables_turnover("90", "0", "0")


def test_cash_flow_quality_requires_positive_consolidated_profit():
    assert calc_cash_flow_quality("30", "100") == Decimal("0.3")
    with pytest.raises(ValueError, match="non-positive"):
        calc_cash_flow_quality("100", "-1")

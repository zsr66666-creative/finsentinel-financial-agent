"""Versioned, deterministic screening rules for research alerts."""

from decimal import Decimal, InvalidOperation


RULE_VERSION = "v1"


def _number(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _alert(rule_id, title, company_id, period, values, formula, evidence_ids, severity="medium"):
    return {
        "id": f"{rule_id}-{company_id}-{period}",
        "company_id": company_id,
        "rule_id": rule_id,
        "rule_version": RULE_VERSION,
        "period": period,
        "title": title,
        "severity": severity,
        "status": "pending",
        "trigger_values": {key: str(value) for key, value in values.items()},
        "formula": formula,
        "evidence_ids": list(evidence_ids),
    }


def evaluate_rules(metrics, company_id, period, evidence_ids):
    """Evaluate only rules with complete, valid inputs; never invent values."""
    alerts = []
    profit_growth = _number(metrics.get("net_profit_growth"))
    if profit_growth is not None and profit_growth <= Decimal("-20"):
        alerts.append(_alert("profit_decline", "归母净利润同比下降", company_id, period, {"net_profit_growth": profit_growth}, "net_profit_growth ≤ -20%", evidence_ids))

    margin_change = _number(metrics.get("gross_margin_change_pp"))
    if margin_change is not None and margin_change <= Decimal("-3"):
        alerts.append(_alert("gross_margin_decline", "毛利率下降", company_id, period, {"gross_margin_change_pp": margin_change}, "gross_margin_change_pp ≤ -3 个百分点", evidence_ids))

    revenue_growth = _number(metrics.get("revenue_growth"))
    for name, label, key in (("inventory_growth_gap", "存货增速高于营业收入", "inventory_growth"), ("receivables_growth_gap", "应收账款增速高于营业收入", "receivables_growth")):
        growth = _number(metrics.get(key))
        if growth is not None and revenue_growth is not None and growth >= Decimal("20") and growth - revenue_growth >= Decimal("10"):
            alerts.append(_alert(name, label, company_id, period, {key: growth, "revenue_growth": revenue_growth}, f"{key} ≥ 20% 且 {key} - revenue_growth ≥ 10 个百分点", evidence_ids))

    profit = _number(metrics.get("consolidated_net_profit"))
    cash_flow = _number(metrics.get("operating_cash_flow"))
    if profit is not None and cash_flow is not None and profit > 0 and cash_flow < 0:
        alerts.append(_alert("cash_flow_quality", "经营现金流为负而合并净利润为正", company_id, period, {"consolidated_net_profit": profit, "operating_cash_flow": cash_flow}, "合并净利润 > 0 且经营现金流净额 < 0", evidence_ids, "high"))
    return alerts

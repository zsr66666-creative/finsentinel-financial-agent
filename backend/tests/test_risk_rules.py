from app.risk_rules import evaluate_rules


def test_profit_decline_rule_emits_versioned_alert():
    alerts = evaluate_rules({"net_profit_growth": "-25"}, company_id="c1", period="2025", evidence_ids=["e1"])
    assert alerts[0]["rule_id"] == "profit_decline"
    assert alerts[0]["rule_version"] == "v1"
    assert alerts[0]["severity"] == "medium"


def test_cash_flow_rule_detects_positive_profit_and_negative_cash_flow():
    alerts = evaluate_rules({"consolidated_net_profit": "10", "operating_cash_flow": "-2"}, "c1", "2025", ["e1"])
    assert any(alert["rule_id"] == "cash_flow_quality" for alert in alerts)


def test_missing_or_invalid_comparison_does_not_create_alert():
    result = evaluate_rules({"inventory_growth": None, "revenue_growth": "10"}, "c1", "2025", [])
    assert result == []


def test_inventory_rule_requires_ten_point_growth_gap():
    assert evaluate_rules({"inventory_growth": "25", "revenue_growth": "16"}, "c1", "2025", ["e1"]) == []
    alerts = evaluate_rules({"inventory_growth": "25", "revenue_growth": "10"}, "c1", "2025", ["e1"])
    assert alerts[0]["rule_id"] == "inventory_growth_gap"

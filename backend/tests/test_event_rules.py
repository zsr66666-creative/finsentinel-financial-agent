from app.risk_rules import evaluate_event_rule


def test_announcement_event_requires_evidence_and_stays_review_only():
    alert = evaluate_event_rule("litigation", "c1", "2025FY", ["e1"], amount="1000000", description="待披露进展")
    assert alert["rule_id"] == "announcement_litigation"
    assert alert["status"] == "pending"
    assert alert["severity"] == "medium"
    assert alert["evidence_ids"] == ["e1"]


def test_unknown_event_or_missing_evidence_is_not_alerted():
    assert evaluate_event_rule("unknown", "c1", "2025FY", ["e1"]) is None
    assert evaluate_event_rule("impairment", "c1", "2025FY", []) is None

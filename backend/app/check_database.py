"""Print and validate the Day 4 SQLite seed contents."""

from .database import create_database


def check_database() -> dict:
    store = create_database()
    companies = store.all("companies")
    filings = store.all("filings")
    metrics = store.all("financial_metrics")
    evidence = store.all("evidence_spans")
    assert len(companies) == 1, f"expected 1 company, got {len(companies)}"
    assert len(filings) == 1, f"expected 1 filing, got {len(filings)}"
    metric_names = {metric["metric"] for metric in metrics}
    assert {"revenue", "net_profit_attributable", "inventory"}.issubset(metric_names)
    assert len(evidence) == 3, f"expected 3 evidence rows, got {len(evidence)}"
    assert all(m["company_id"] == companies[0]["id"] for m in metrics)
    assert all(m["source_ids"] for m in metrics)
    assert all(isinstance(m["value"], (int, float, str)) for m in metrics)
    result = {"companies": len(companies), "filings": len(filings), "metrics": len(metrics), "evidence": len(evidence)}
    print("database_ok", result)
    for metric in metrics:
        print(metric["metric"], metric["value"], metric["unit"], metric["period"], metric["source_ids"])
    store.close()
    return result


if __name__ == "__main__":
    check_database()

from app.evaluation import recall_at_k
from app.retrieval import expand_query, search_chunks


def rows():
    return [
        {"id": "a", "company_id": "c1", "period": "2024", "date": "2024-12-01", "document_type": "annual_report", "page": 10, "paragraph": 1, "text": "营业收入增长"},
        {"id": "b", "company_id": "c2", "period": "2024", "date": "2024-12-01", "document_type": "annual_report", "page": 11, "paragraph": 1, "text": "营业收入增长"},
        {"id": "future", "company_id": "c1", "period": "2025", "date": "2025-12-01", "document_type": "annual_report", "page": 12, "paragraph": 1, "text": "营业收入增长"},
    ]


def test_search_filters_company_period_and_as_of_before_ranking():
    result = search_chunks(rows(), "营业收入", company_id="c1", period="2024", as_of="2024-12-31")
    assert result["items"][0]["id"] == "a"
    assert [item["id"] for item in result["items"]] == ["a"]
    assert result["items"][0]["page_no"] == 10


def test_empty_query_returns_no_results():
    assert search_chunks(rows(), "", company_id="c1")["items"] == []


def test_recall_at_five_uses_gold_evidence_ids():
    cases = [{"id": "q1", "gold_evidence_ids": ["a", "b"]}, {"id": "q2", "gold_evidence_ids": ["c"]}]
    assert recall_at_k(cases, {"q1": ["a", "x"], "q2": ["c"]}) == 0.75


def test_query_expansion_removes_question_fillers_and_adds_financial_synonyms():
    expanded = expand_query("立讯精密2026年上半年归母净利润是多少？")
    assert "归属于上市公司股东的净利润" in expanded
    assert "是多少" not in expanded

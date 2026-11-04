"""Run the Week 08 BM25 evaluation against locally extracted PDF pages."""

import json
import glob
from pathlib import Path

from app.evaluation import recall_at_k
from app.retrieval import merge_page_spans, search_chunks


def run():
    chunks = []
    for filename in glob.glob("data/derived/documents/*.json"):
        document = json.loads(Path(filename).read_text(encoding="utf-8"))
        for page in document.get("pages", []):
            spans = merge_page_spans(page.get("spans", []))
            for index, span in enumerate(spans):
                chunks.append({
                    "id": f"{document['id']}-p{page['page']}-m{index}",
                    "company_id": f"cn-{document['company_code']}",
                    "period": document["report_period"],
                    "date": document.get("published_at"),
                    "document_type": document.get("report_type"),
                    "page": page["page"],
                    "paragraph": span.get("paragraph_start", index + 1),
                    "text": span.get("text", ""),
                })
    cases = [json.loads(line) for line in Path("data/evals/golden_questions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    retrieved, details = {}, []
    for case in cases:
        result = search_chunks(chunks, case["question"], company_id=case["company_id"], period=case["period"], top_k=5)
        ids = [item["chunk_id"] for item in result["items"]]
        retrieved[case["id"]] = ids
        gold = set(case.get("gold_evidence_ids", []))
        hits = sorted(gold.intersection(ids))
        details.append({"case_id": case["id"], "question": case["question"], "gold_evidence_ids": sorted(gold), "retrieved_ids": ids, "hits": hits, "hit": bool(hits), "retrieval_mode": result["retrieval_mode"], "warnings": result["warnings"], "miss_reason": None if hits else "query_or_chunk_mismatch"})
    output = {"run_id": "week08-real-bm25-001", "corpus_version": "week7-8-v1", "top_k": 5, "case_count": len(cases), "hit_count": sum(item["hit"] for item in details), "recall_at_5": recall_at_k(cases, retrieved, 5), "details": details}
    Path("data/evals/retrieval-run-week08.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: output[key] for key in ("case_count", "hit_count", "recall_at_5")}, ensure_ascii=False))


if __name__ == "__main__":
    run()

"""Small, reproducible retrieval evaluation helpers."""


def recall_at_k(cases, retrieved_by_case, k=5):
    scores = []
    for case in cases:
        gold = set(case.get("gold_evidence_ids", []))
        if not gold:
            continue
        found = set(retrieved_by_case.get(case["id"], [])[:k])
        scores.append(len(gold & found) / len(gold))
    return sum(scores) / len(scores) if scores else None

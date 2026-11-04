"""Small deterministic retrieval adapter used by the v0.1 evidence path."""

import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2}|[A-Za-z0-9_]+", text.lower())
    return tokens


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores = Counter()
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] += 1 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


class HybridRetriever:
    def __init__(self, embeddings=None):
        self.embeddings = embeddings

    def search(self, rows, query, company_id=None, date_range=None):
        scoped = [row for row in rows if (company_id is None or row.get("company_id") == company_id)]
        if date_range:
            start, end = date_range[0], date_range[1] if len(date_range) > 1 else None
            scoped = [row for row in scoped if row.get("date", "") >= start and (not end or row.get("date", "") <= end)]
        if not scoped:
            return {"value": [], "source_ids": [], "retrieval_mode": "bm25", "warnings": ["embeddings_not_configured"]}

        query_tokens = tokenize(query)
        scores = []
        for row in scoped:
            counts = Counter(tokenize(row.get("text", "")))
            scores.append((row, sum(counts[token] for token in query_tokens)))
        lexical = [row for row, score in scores if score > 0]
        lexical.sort(key=lambda row: -sum(Counter(tokenize(row.get("text", "")))[token] for token in query_tokens))
        warnings = []
        mode = "bm25"
        if self.embeddings and scoped:
            try:
                vectors = self.embeddings.embed_documents([row.get("text", "") for row in scoped])
                query_vector = self.embeddings.embed_query(query)
                if not lexical:
                    def similarity(vector):
                        return sum(a * b for a, b in zip(vector, query_vector))
                    lexical = [row for _, row in sorted(zip(vectors, scoped), key=lambda pair: -similarity(pair[0]))]
                mode = "bm25_vector_rrf"
            except Exception as exc:
                warnings.append(f"embedding_unavailable:{type(exc).__name__}")
        else:
            warnings.append("embeddings_not_configured")
        return {"value": lexical, "source_ids": [row["id"] for row in lexical], "retrieval_mode": mode, "warnings": warnings}

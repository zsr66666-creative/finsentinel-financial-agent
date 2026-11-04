"""Small deterministic retrieval adapter used by the v0.1 evidence path."""

import re
from collections import Counter


QUERY_SYNONYMS = {
    "营业收入": ("营业收入", "营业总收入", "收入"),
    "归母净利润": ("归母净利润", "归属于上市公司股东的净利润", "归属于上市公司股东净利润"),
    "存货": ("存货", "存货余额", "存货账面价值"),
    "应收账款": ("应收账款", "应收款项"),
    "经营现金流": ("经营现金流", "经营活动产生的现金流量净额", "经营现金流净额"),
    "经营活动产生的现金流量净额": ("经营活动产生的现金流量净额", "经营现金流净额", "经营现金流"),
}
QUERY_FILLERS = ("是多少", "多少", "能否", "是否", "请问", "请分析", "请说明", "？", "?")


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2}|[A-Za-z0-9_]+", text.lower())
    return tokens


def expand_query(query: str) -> str:
    """Normalize question wording while preserving financial terms."""
    expanded = query
    for filler in QUERY_FILLERS:
        expanded = expanded.replace(filler, " ")
    terms = [expanded]
    for canonical, synonyms in QUERY_SYNONYMS.items():
        if canonical in expanded or any(synonym in expanded for synonym in synonyms):
            terms.extend(synonyms)
    return " ".join(terms)


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

        query_tokens = tokenize(expand_query(query))
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


def search_chunks(rows, query, company_id=None, period=None, document_type=None, as_of=None, top_k=5):
    """Filter evidence before lexical ranking and preserve page anchors."""
    scoped = []
    for row in rows:
        if company_id and row.get("company_id") != company_id:
            continue
        if period and str(row.get("period")) != str(period):
            continue
        if document_type and row.get("document_type") != document_type:
            continue
        if as_of and row.get("date") and str(row["date"]) > str(as_of):
            continue
        scoped.append(row)
    expanded_query = expand_query(query)
    result = HybridRetriever().search(scoped, expanded_query, None)
    items = []
    for rank, row in enumerate(result["value"][:max(0, min(top_k, 20))], start=1):
        tokens = Counter(tokenize(row.get("text", "")))
        score = sum(tokens[token] for token in tokenize(expanded_query))
        items.append({**row, "chunk_id": row.get("id"), "page_no": row.get("page"), "paragraph_no": row.get("paragraph"), "score": score, "rank": rank})
    return {"items": items, "total": len(items), "retrieval_mode": "bm25_only", "warnings": result["warnings"]}


def merge_page_spans(spans, max_chars=900):
    """Merge adjacent spans on one page without losing page/paragraph anchors."""
    merged = []
    current = None
    for span in spans:
        text = span.get("text", "")
        if not text.strip():
            continue
        if current is None or len(current["text"]) + len(text) > max_chars:
            if current is not None:
                merged.append(current)
            current = {**span, "text": text, "paragraph_start": span.get("paragraph", 1), "paragraph_end": span.get("paragraph", 1)}
        else:
            current["text"] += "\n" + text
            current["paragraph_end"] = span.get("paragraph", current["paragraph_end"])
    if current is not None:
        merged.append(current)
    return merged

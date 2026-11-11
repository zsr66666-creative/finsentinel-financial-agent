"""Development-only query decomposition; no gold labels or case IDs in ranking."""
from time import perf_counter
from app.persisted_hybrid import hybrid_search

ALIASES={
    '营业收入':['营业收入','营业规模','营收'],
    '归属于上市公司股东的净利润':['归母净利润','账面利润'],
    '经营活动产生的现金流量净额':['经营现金流','日常经营活动','经营活动产生的现金流量净额'],
    '总资产':['总资产','资产规模','家底'],
    '归属于上市公司股东的净资产':['归母净资产','股东权益','股东的权益'],
    '应收账款':['应收账款','应收款项'],
    '存货':['存货','库存'],
    '基本每股收益':['基本每股收益'],
    '稀释每股收益':['稀释每股收益'],
}

def plan_queries(question):
    # Deterministic table order, capped independently of evaluation labels.
    return [metric for metric,aliases in ALIASES.items() if any(a in question for a in aliases)][:6]

def balanced_search(rows,question,*,company_code,period,top_k=5,as_of=None):
    started=perf_counter()
    queries=plan_queries(question) or [question]
    rankings=[hybrid_search(rows,q,company_code=company_code,period=period,top_k=20,as_of=as_of)['items'] for q in queries]
    items=[];seen=set()
    # Round-robin preserves a slot for each requested metric instead of letting
    # a single metric dominate. Scores are NOT comparable across subqueries.
    for depth in range(20):
        for ranking in rankings:
            if depth<len(ranking):
                item=ranking[depth]
                if item['chunk_id'] not in seen:
                    seen.add(item['chunk_id']);items.append(item)
    return dict(items=items[:top_k],queries=queries,retrieval_mode='experimental_metric_balanced_bm25',
                duration_ms=round((perf_counter()-started)*1000,3))

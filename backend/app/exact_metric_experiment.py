"""Development-only exact financial-row preference; no gold-ID features."""
import re
from time import perf_counter
from app.metric_query_experiment import plan_queries, balanced_search

def numeric_label(content, metric):
    # Remove PDF line-wrap whitespace only; require the complete row label
    # before the first digit, not a substring of a different financial item.
    prefix=re.split(r'\d',content,maxsplit=1)[0]
    label=re.sub(r'\s|[（(][^）)]*[）)]','',prefix).strip('：:')
    return label==metric and bool(re.search(r'\d',content))

def exact_search(rows,question,*,company_code,period,top_k=5):
    started=perf_counter()
    fallback=balanced_search(rows,question,company_code=company_code,period=period,top_k=20)
    metrics=plan_queries(question)
    scoped=[r for r in rows if r['company_code']==company_code and r['period']==period]
    rankings=[]
    for metric in metrics:
        matches=[r for r in scoped if numeric_label(r['text'],metric)]
        matches.sort(key=lambda r:(not r.get('explicit_consolidated_page',False),r['chunk_id']))
        rankings.append(matches)
    items=[];seen=set()
    for depth in range(max((len(r) for r in rankings),default=0)):
        for ranking in rankings:
            if depth<len(ranking) and ranking[depth]['chunk_id'] not in seen:
                row=ranking[depth];seen.add(row['chunk_id'])
                items.append(dict(chunk_id=row['chunk_id'],provenance=row,exact_label=True))
    items.extend(r for r in fallback['items'] if r['chunk_id'] not in seen)
    return dict(items=items[:top_k],queries=metrics,retrieval_mode='experimental_exact_metric',
                duration_ms=round((perf_counter()-started)*1000,3))

"""BM25/RRF on the SAME persisted span IDs as the vector candidate corpus."""
from collections import Counter
from datetime import date
from math import log
from time import perf_counter
from sqlalchemy import text
from app.retrieval import tokenize, expand_query, reciprocal_rank_fusion

def hybrid_search(rows, query, *, company_code, period, vector_search=None, top_k=5, as_of=None):
    if not company_code or not period or type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError('scope and top_k 1..20 required')
    if as_of: date.fromisoformat(as_of)
    started=perf_counter()
    scoped={r['chunk_id']:r for r in rows if r.get('company_code')==company_code
            and r.get('period')==period and (not as_of or
            (r.get('published_at') and r['published_at']<=as_of))}
    tokens=Counter(tokenize(expand_query(query)))
    if not scoped or not tokens:
        return dict(items=[],total=0,retrieval_mode='bm25_only',warnings=['empty_scope_or_query'],duration_ms=0)
    documents={key:Counter(tokenize(r.get('text',''))) for key,r in scoped.items()}
    lengths={key:sum(words.values()) for key,words in documents.items()}
    average=sum(lengths.values())/len(lengths) or 1
    scores={}
    for key,words in documents.items():
        score=0
        for term in tokens:
            frequency=words[term]
            df=sum(term in doc for doc in documents.values())
            idf=log(1+(len(documents)-df+0.5)/(df+0.5))
            if frequency:
                score+=idf*frequency*2.2/(frequency+1.2*(0.25+0.75*lengths[key]/average))
        if score>0: scores[key]=score
    # Candidate depth is frozen independently of output K for RRF comparison.
    lexical=sorted(scores,key=lambda key:(-scores[key],key))[:20]
    vectors=[]; warnings=[]; mode='bm25_only'
    if vector_search is None:
        warnings.append('vector_not_configured')
    else:
        try:
            result=vector_search()
            vectors=list(dict.fromkeys(r['chunk_id'] for r in result['items'] if r['chunk_id'] in scoped))[:20]
            if vectors: mode='bm25_vector_rrf'
            else: warnings.append('vector_empty')
        except Exception as exc:
            warnings.append(f'vector_unavailable:{type(exc).__name__}')
    ranking=reciprocal_rank_fusion([lexical,vectors]) if vectors else [(key,None) for key in lexical]
    items=[dict(chunk_id=key,provenance=scoped[key],rrf_score=score,bm25_score=scores.get(key),
                bm25_rank=lexical.index(key)+1 if key in lexical else None,
                vector_rank=vectors.index(key)+1 if key in vectors else None)
           for key,score in ranking[:top_k]]
    return dict(items=items,total=len(items),retrieval_mode=mode,warnings=warnings,
                duration_ms=round((perf_counter()-started)*1000,3))

def search_persisted(engine, query, vector, *, model, company_code, period, top_k=5, as_of=None):
    from app.pgvector_search import search_vectors
    # Read the same imported spans; do not splice legacy merged -m IDs into -s IDs.
    with engine.connect() as conn:
        rows=conn.execute(text('''SELECT chunk_id, provenance FROM document_chunk_embeddings
            WHERE model=:model AND dimensions=512
            AND provenance->>'company_code'=:company AND provenance->>'period'=:period'''),
            dict(model=model,company=company_code,period=period)).mappings().all()
    corpus=[{**r['provenance'],'chunk_id':r['chunk_id']} for r in rows if r['provenance']]
    call=None if vector is None else lambda: search_vectors(engine,vector,model=model,
        company_code=company_code,period=period,top_k=20,as_of=as_of)
    return hybrid_search(corpus,query,company_code=company_code,period=period,
                         top_k=top_k,as_of=as_of,vector_search=call)

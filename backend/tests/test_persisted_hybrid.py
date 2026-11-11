from app.persisted_hybrid import hybrid_search

ROWS = [dict(chunk_id='a', text='存货减值', company_code='002475',period='2026H1'),
        dict(chunk_id='b', text='收入增长', company_code='002475',period='2026H1'),
        dict(chunk_id='other',text='存货减值',company_code='other',period='2026H1')]

def test_fusion_shares_ids_and_rejects_foreign_results():
    result=hybrid_search(ROWS,'存货',company_code='002475',period='2026H1',
        vector_search=lambda: dict(items=[{'chunk_id':'b'},{'chunk_id':'a'},{'chunk_id':'other'}]))
    assert result['retrieval_mode']=='bm25_vector_rrf'
    assert result['items'][0]['chunk_id']=='a'
    assert {r['chunk_id'] for r in result['items']}=={'a','b'}
    assert result['items'][0]['bm25_rank']==1
    assert result['items'][0]['vector_rank']==2

def test_timeout_fallback_and_empty_scope():
    def broken(): raise TimeoutError('secret error detail')
    result=hybrid_search(ROWS,'存货',company_code='002475',period='2026H1',vector_search=broken)
    assert result['retrieval_mode']=='bm25_only'
    assert result['warnings']==['vector_unavailable:TimeoutError']
    assert [r['chunk_id'] for r in result['items']]==['a']
    assert hybrid_search(ROWS,'存货',company_code='absent',period='2026H1',vector_search=broken)['items']==[]

def test_future_and_unknown_dates_excluded_and_irrelevant_empty():
    assert hybrid_search(ROWS,'存货',company_code='002475',period='2026H1',as_of='2026-12-31')['items']==[]
    assert hybrid_search(ROWS,'zzzz',company_code='002475',period='2026H1')['items']==[]

from datetime import date

from app.retrieval import HybridRetriever, tokenize, reciprocal_rank_fusion


def evidence(key, text, company='c1', published='2025-04-01'):
    return {'id':key,'text':text,'company_id':company,'date':published,'document_type':'annual_report'}


def test_filters_precede_ranking_and_irrelevant_hits_are_not_fabricated():
    rows=[evidence('inventory','存货增加并计提跌价准备'), evidence('profit','净利润增长'), evidence('wrong-company','存货存货存货','c2'), evidence('future','存货跌价',published='2026-01-01')]
    result=HybridRetriever().search(rows, '存货跌价', 'c1', ['2025-01-01','2025-12-31'])
    assert result['source_ids']==['inventory']
    assert result['retrieval_mode']=='bm25'
    assert 'embeddings_not_configured' in result['warnings']
    assert HybridRetriever().search(rows,'zzzz','c1')['value']==[]


def test_rrf_uses_ranks_not_incompatible_raw_score_scales():
    result=reciprocal_rank_fusion([['a','b'],['b','c']])
    assert result[0][0]=='b'
    assert len({r[0] for r in result})==3


def test_embedding_failure_falls_back_without_hiding_degradation():
    class Unavailable:
        def embed_documents(self,texts): raise TimeoutError('offline')
        def embed_query(self,text): raise TimeoutError('offline')
    result=HybridRetriever(embeddings=Unavailable()).search([evidence('a','存货跌价')],'存货','c1')
    assert result['retrieval_mode']=='bm25'
    assert 'embedding_unavailable:TimeoutError' in result['warnings']


def test_hybrid_calls_actual_injected_embedding_interface_and_filters():
    class Embedder:
        def embed_documents(self,texts): return [[1.0,0.0] if '减值' in t else [0.0,1.0] for t in texts]
        def embed_query(self,text): return [1.0,0.0]
    result=HybridRetriever(embeddings=Embedder()).search([evidence('a','资产减值'),evidence('b','收入增长')],'损失','c1')
    assert result['retrieval_mode']=='bm25_vector_rrf'
    assert result['source_ids'][0]=='a'


def test_empty_scope_never_calls_embedding_api():
    class Never:
        def embed_query(self,text): raise AssertionError('empty scope')
    assert HybridRetriever(embeddings=Never()).search([], '存货','c1')['source_ids']==[]


def test_chinese_bigrams_and_financial_identifiers():
    assert '存货' in tokenize('存货减值 revenue_2025')
    assert 'revenue_2025' in tokenize('存货减值 revenue_2025')

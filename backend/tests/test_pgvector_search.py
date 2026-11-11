import pytest
from app.pgvector_search import search_vectors

class NeverConnect:
    def connect(self):
        raise AssertionError('invalid request must not reach database')

@pytest.mark.parametrize('vector,k', [([1],5),([float('nan')]*512,5),([0.0]*512,5),([1.0]+[0.0]*511,0)])
def test_invalid_queries_rejected_before_database(vector,k):
    with pytest.raises(ValueError):
        search_vectors(NeverConnect(), vector, company_code='002475', period='2026H1', model='test@1', top_k=k)

def test_missing_scope_rejected():
    with pytest.raises(ValueError):
        search_vectors(NeverConnect(), [1.0]+[0.0]*511, company_code='', period='2026H1', model='test@1')

def test_postgres_exact_ranking_and_scope():
    import os, json
    from contextlib import nullcontext
    from sqlalchemy import create_engine, text
    url=os.getenv('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TEST_POSTGRES_URL unavailable; PostgreSQL search not measured')
    engine=create_engine(url)
    try:
        with engine.connect() as conn:
            transaction=conn.begin()
            try:
                conn.execute(text('CREATE TEMP TABLE document_chunk_embeddings (chunk_id text, model text, dimensions int, embedding vector(512), provenance jsonb)'))
                for key,company,period,published,vector in [
                    ('hit','002475','2026H1','2026-08-01',[1.0]+[0.0]*511),
                    ('wrong-company','other','2026H1','2026-08-01',[1.0]+[0.0]*511),
                    ('wrong-period','002475','2025FY','2026-08-01',[1.0]+[0.0]*511),
                    ('future','002475','2026H1','2027-01-01',[1.0]+[0.0]*511)]:
                    conn.execute(text('INSERT INTO document_chunk_embeddings VALUES (:id,\'test@1\',512,CAST(:v AS vector),CAST(:p AS jsonb))'),dict(id=key,v=json.dumps(vector),p=json.dumps(dict(company_code=company,period=period,published_at=published))))
                class Bound:
                    def connect(self): return nullcontext(conn)
                result=search_vectors(Bound(),[1.0]+[0.0]*511,company_code='002475',period='2026H1',model='test@1',as_of='2026-12-31')
                assert [r['chunk_id'] for r in result['items']]==['hit']
                assert result['items'][0]['cosine_distance']==pytest.approx(0)
                assert search_vectors(Bound(),[1.0]+[0.0]*511,company_code='absent',period='2026H1',model='test@1')['items']==[]
            finally:
                transaction.rollback()
    finally:
        engine.dispose()

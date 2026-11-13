import json
from fastapi.testclient import TestClient

from app.main import create_app


def test_vector_search_contract_rejects_wrong_dimension_before_database():
    client = TestClient(create_app(database_url='sqlite:///:memory:', data_mode='synthetic_demo'))
    response = client.post('/api/v1/evidence/search/vector', json={
        'query': '应收账款', 'vector': [1.0], 'model': 'BAAI/bge-small-zh-v1.5@v1',
        'company_code': '002475', 'period': '2026H1',
    })
    assert response.status_code == 422


def test_vector_search_contract_hides_database_errors(monkeypatch):
    app = create_app(database_url='sqlite:///:memory:', data_mode='synthetic_demo')
    def fail(*args, **kwargs):
        raise RuntimeError('secret connection detail')
    monkeypatch.setattr('app.main.search_persisted', fail)
    client = TestClient(app)
    response = client.post('/api/v1/evidence/search/vector', json={
        'query': '应收账款', 'vector': [1.0] + [0.0] * 511,
        'model': 'BAAI/bge-small-zh-v1.5@v1', 'company_code': '002475',
        'period': '2026H1', 'top_k': 5,
    })
    assert response.status_code == 503
    assert response.json()['detail'] == 'vector_search_unavailable'
    assert 'secret' not in response.text


def test_vector_search_contract_preserves_scope_and_metadata(monkeypatch):
    app = create_app(database_url='sqlite:///:memory:', data_mode='synthetic_demo')
    observed = {}
    def fake(engine, query, vector, **kwargs):
        observed.update(query=query, vector=vector, kwargs=kwargs)
        return {'items': [{'chunk_id': 'c', 'vector_rank': 1}], 'total': 1,
                'retrieval_mode': 'bm25_vector_rrf', 'warnings': [], 'duration_ms': 1.2}
    monkeypatch.setattr('app.main.search_persisted', fake)
    client = TestClient(app)
    response = client.post('/api/v1/evidence/search/vector', json={
        'query': '应收账款', 'vector': [1.0] + [0.0] * 511,
        'model': 'BAAI/bge-small-zh-v1.5@v1', 'company_code': '002475',
        'period': '2026H1', 'top_k': 3, 'as_of': '2026-12-31',
    })
    assert response.status_code == 200
    assert response.json()['data_mode'] == 'reviewed_real_pdf'
    assert observed['kwargs'] == dict(model='BAAI/bge-small-zh-v1.5@v1', company_code='002475', period='2026H1', top_k=3, as_of='2026-12-31')

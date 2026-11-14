import math
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.online_query import MODEL_ID, QueryServiceError, validate_embedding


def payload(**changes):
    return dict(query='应收账款是多少？', company_code='002475', period='2026H1', top_k=5, **changes)


def test_embedding_contract_rejects_mismatched_model_and_bad_vectors():
    valid = {'model': MODEL_ID, 'vector': [1.0] + [0.0] * 511, 'encoding_ms': 1.0}
    assert len(validate_embedding(valid)[0]) == 512
    for patch in [{'model': 'other'}, {'vector': [1.0]}, {'vector': [0.0] * 512}, {'vector': [math.nan] * 512}, {'vector': [True] * 512}, {'encoding_ms': -1}]:
        with pytest.raises(QueryServiceError):
            validate_embedding({**valid, **patch})


def test_text_search_validates_before_encoding(monkeypatch):
    client = TestClient(create_app(database_url='sqlite:///:memory:'))
    def unexpected(*args):
        pytest.fail('encoding must not run for invalid requests')
    monkeypatch.setattr('app.main.encode_online_query', unexpected)
    for value in ['', '   ', 'x' * 501]:
        body = payload(); body['query'] = value
        assert client.post('/api/v1/evidence/search/text', json=body).status_code == 422
    assert client.post('/api/v1/evidence/search/text', json={**payload(), 'vector': [1]}).status_code == 422


def test_text_search_preserves_model_scope_and_candidate_boundary(monkeypatch):
    vector = [1.0] + [0.0] * 511
    monkeypatch.setattr('app.main.encode_online_query', lambda query: (vector, 2.5))
    observed = {}
    def retrieve(engine, query, supplied_vector, **kwargs):
        observed.update(query=query, vector=supplied_vector, **kwargs)
        return dict(items=[], total=0, warnings=[], retrieval_mode='bm25_vector_rrf', duration_ms=1.0)
    monkeypatch.setattr('app.main.search_persisted', retrieve)
    client = TestClient(create_app(database_url='sqlite:///:memory:'))
    response = client.post('/api/v1/evidence/search/text', json=payload())
    assert response.status_code == 200
    assert observed['model'] == MODEL_ID
    assert observed['company_code'] == '002475' and observed['period'] == '2026H1'
    assert observed['vector'] == vector
    assert response.json()['encoding_ms'] == 2.5
    assert response.json()['answer_status'] == 'candidates_only'


def test_service_errors_do_not_fallback_or_leak(monkeypatch):
    def fail(query):
        raise QueryServiceError('secret path', status_code=503)
    monkeypatch.setattr('app.main.encode_online_query', fail)
    client = TestClient(create_app(database_url='sqlite:///:memory:'))
    response = client.post('/api/v1/evidence/search/text', json=payload())
    assert response.status_code == 503
    assert response.json()['detail'] == 'query_encoder_unavailable'
    assert 'secret' not in response.text


def test_encoder_client_timeout_releases_capacity(monkeypatch):
    from app import online_query
    monkeypatch.setenv('QUERY_ENCODER_ENABLED', '1')
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert url == 'http://127.0.0.1:8081/encode'
            assert kwargs['timeout'] == (1, 8)
            assert self.trust_env is False
            raise TimeoutError('sensitive downstream error')
    monkeypatch.setattr(online_query.requests, 'Session', Session)
    for _ in range(2):
        with pytest.raises(QueryServiceError) as error:
            online_query.encode_online_query('问题')
        assert error.value.status_code == 503
    assert online_query._slots.acquire(False)
    try:
        with pytest.raises(QueryServiceError) as error:
            online_query.encode_online_query('问题')
        assert error.value.status_code == 429
    finally:
        online_query._slots.release()

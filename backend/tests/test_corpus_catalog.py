import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.corpus_catalog import list_scopes
from app.main import create_app
from app.online_query import MODEL_ID


def test_catalog_only_advertises_actual_fixed_model_text_and_pages():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE document_chunk_embeddings (model TEXT, dimensions INTEGER, provenance TEXT)'))
        for period, page, model, content in [('2024FY', 60, MODEL_ID, '真实原文'), ('2024FY', 63, MODEL_ID, '另一页'),
                                              ('2023FY', 5, 'another-model', '不可混入'), ('2022FY', 1, MODEL_ID, '')]:
            c.execute(text('INSERT INTO document_chunk_embeddings VALUES (:model,512,:p)'),
                      dict(model=model, p=json.dumps(dict(company_code='002475', period=period, document_id=period,
                          document_sha256='a'*64, page=page, text=content, source_status='unreviewed',
                          coverage=dict(kind='selected_financial_and_risk_pages', total_pages=100, pages=[1, 60, 63])))))
    result = list_scopes(engine)
    assert result['model'] == MODEL_ID and result['total'] == 1
    scope = result['items'][0]
    assert scope['period'] == '2024FY' and scope['chunk_count'] == 2
    assert scope['documents'][0]['pages'] == [60, 63]
    assert scope['documents'][0]['total_pages'] == 100
    assert scope['documents'][0]['coverage_kind'] == 'selected_pages'
    assert 'artifact_path' not in json.dumps(result)


def test_legacy_scope_is_fragments_not_full_report():
    engine = create_engine('sqlite:///:memory:')
    assert list_scopes(engine)['items'] == []
    with engine.begin() as c:
        c.execute(text('CREATE TABLE document_chunk_embeddings (model TEXT, dimensions INTEGER, provenance TEXT)'))
        c.execute(text('INSERT INTO document_chunk_embeddings VALUES (:model,512,:p)'),
                  dict(model=MODEL_ID, p=json.dumps(dict(company_code='002475', period='2026H1', page=60, text='原文',
                      document_id='002475-2026H1', document_sha256='b'*64, source_status='local_pdf_hash_matched'))))
    document = list_scopes(engine)['items'][0]['documents'][0]
    assert document['coverage_kind'] == 'indexed_fragments' and document['total_pages'] is None


def test_scope_api_empty_and_sanitized_failure(monkeypatch):
    client = TestClient(create_app(database_url='sqlite:///:memory:'))
    response = client.get('/api/v1/evidence/scopes')
    assert response.status_code == 200 and response.json()['total'] == 0
    def fail(engine): raise RuntimeError('secret database path')
    monkeypatch.setattr('app.main.list_scopes', fail)
    response = client.get('/api/v1/evidence/scopes')
    assert response.status_code == 503
    assert response.json()['detail'] == 'evidence_scopes_unavailable'
    assert 'secret' not in response.text

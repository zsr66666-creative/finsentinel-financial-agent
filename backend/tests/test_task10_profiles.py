import json

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.online_query import MODEL_ID


def test_planned_company_is_not_a_real_profile_before_indexing():
    client = TestClient(create_app(database_url='sqlite:///:memory:'))
    for code in ('002555', '002230'):
        assert client.get('/api/v1/companies/' + code).status_code == 404


def test_indexed_company_profile_uses_real_identity_without_demo_metrics():
    app = create_app(database_url='sqlite:///:memory:')
    client = TestClient(app)
    with app.state.store.engine.begin() as c:
        c.execute(text('CREATE TABLE document_chunk_embeddings (model TEXT, dimensions INTEGER, provenance TEXT)'))
        for code in ('002555', '002230'):
            p = dict(company_code=code, period='2024FY', document_id=code, document_sha256='a'*64,
                     page=2, text='source text fixture', source_status='official_pdf_hash_verified_unreviewed')
            c.execute(text('INSERT INTO document_chunk_embeddings VALUES (:model,512,:p)'), dict(model=MODEL_ID, p=json.dumps(p)))
    for code, name, industry in [('002555', '三七互娱', '互联网游戏'), ('002230', '科大讯飞', '人工智能')]:
        response = client.get('/api/v1/companies/' + code)
        assert response.status_code == 200
        profile = response.json()
        assert profile['name'] == name and profile['industry'] == industry
        assert profile['data_mode'] == 'real_pdf_candidates'
        assert profile['indexed_scopes'][0]['period'] == '2024FY'
        assert 'metrics' not in profile and 'alerts' not in profile
        assert client.get('/api/v1/companies/' + code + '/metrics').status_code == 404
    existing = client.get('/api/v1/companies/002475').json()
    assert existing['data_mode'] == 'synthetic_demo'
    assert len(client.get('/api/v1/companies').json()['items']) == 24


def test_registry_uses_business_categories_not_unverified_qualification_claims():
    from app.research_companies import RESEARCH_COMPANIES
    assert RESEARCH_COMPANIES['002555']['legal_name'] == '三七互娱网络科技集团股份有限公司'
    assert RESEARCH_COMPANIES['002230']['legal_name'] == '科大讯飞股份有限公司'
    assert all('certified' not in value for value in RESEARCH_COMPANIES.values())

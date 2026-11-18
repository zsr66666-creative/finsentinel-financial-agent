from sqlalchemy import inspect
from fastapi.testclient import TestClient

from app.main import create_app
import app.main as main_module
import scripts.task8_online_acceptance as acceptance


def test_task8_acceptance_app_can_connect_without_creating_database_schema(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'false')
    monkeypatch.delenv('CORPUS_PATH', raising=False)
    app = create_app(
        database_url='sqlite:///:memory:',
        data_mode='real_corpus',
        create_schema=False,
    )
    try:
        assert inspect(app.state.store.engine).get_table_names() == []
    finally:
        app.state.store.close()


def test_read_only_store_rejects_writes(tmp_path):
    from app.store import Store

    url = f'sqlite:///{tmp_path / "readonly.sqlite"}'
    writer = Store(url)
    writer.close()
    store = Store(url, create_schema=False, read_only=True)
    try:
        try:
            store.put('companies', {'id': 'x', 'name': 'x'})
        except Exception:
            pass
        else:
            raise AssertionError('read-only store accepted a write')
    finally:
        store.close()


def test_acceptance_has_an_in_process_api_client_for_protected_deployment(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'false')
    monkeypatch.setenv('QUERY_ENCODER_ENABLED', '1')
    vector = [1.0] + [0.0] * 511
    monkeypatch.setattr(main_module, 'encode_online_query', lambda query: (vector, 1.25))
    monkeypatch.setattr(main_module, 'search_persisted', lambda *args, **kwargs: {
        'items': [{
            'chunk_id': '002475-2026H1-p63-s4',
            'provenance': {'company_code': '002475', 'period': '2026H1'},
        }],
        'total': 1,
        'warnings': [],
        'retrieval_mode': 'bm25_vector_rrf',
        'duration_ms': 1.0,
    })
    client_factory = getattr(acceptance, '_create_in_process_api_client', None)
    assert callable(client_factory), 'deployment acceptance needs an isolated in-process API client'
    with client_factory('sqlite:///:memory:') as client:
        response = client.post('/api/v1/evidence/search/text', json={
            'query': '应收账款是多少？', 'company_code': '002475', 'period': '2026H1', 'top_k': 5,
        })
    assert response.status_code == 200
    assert response.json()['answer_status'] == 'candidates_only'
    assert response.json()['items'][0]['chunk_id'] == '002475-2026H1-p63-s4'


def test_in_process_acceptance_refuses_to_disable_auth_inside_production_process(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    try:
        with acceptance._create_in_process_api_client('sqlite:///:memory:'):
            pass
    except RuntimeError as exc:
        assert str(exc) == 'in_process_acceptance_requires_isolated_auth_disabled_process'
    else:
        raise AssertionError('acceptance must not change production auth behavior')


def test_task8_protected_api_rejects_anonymous_mutation(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('AUTH_ORIGIN', 'https://example.test')
    app = create_app(database_url='sqlite:///:memory:')
    try:
        response = TestClient(app).post('/api/v1/evidence/search/text', json={
            'query': 'receivables', 'company_code': '002475', 'period': '2026H1', 'top_k': 5,
        })
    finally:
        app.state.store.close()
    assert response.status_code == 403
    assert response.json()['detail'] == 'origin_invalid'


def test_installer_uses_isolated_acceptance_and_keeps_live_api_protected():
    from pathlib import Path

    installer = Path(__file__).resolve().parents[2] / 'deploy/ecs/install-task8-offline.sh'
    source = installer.read_text(encoding='utf-8')
    assert '--in-process-api' in source
    assert '--api-url http://127.0.0.1:8000' not in source
    assert '--api-url http://127.0.0.1 ' not in source
    assert "--comparison-query '立讯精密" in source
    assert "s.post('http://127.0.0.1:8000/api/v1/evidence/compare'" not in source
    assert "DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql'" in source
    assert 'systemctl show finsentinel-backend -p Environment' not in source
    assert "response.code in (401, 403)" in source
    assert 'origin_invalid' in source

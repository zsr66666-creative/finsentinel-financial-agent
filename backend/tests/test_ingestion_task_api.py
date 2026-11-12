from fastapi.testclient import TestClient
from app.main import create_app
from app.migrations import migrate_ingestion_up

PATH='/api/v1/admin/source-ingestion/tasks'
BODY=dict(source_url='https://static.cninfo.com.cn/a.pdf',company_code='002475',report_period='2024FY',report_type='annual')

def test_admin_task_auth_idempotency_and_retry(monkeypatch):
    monkeypatch.setenv('INGESTION_ADMIN_TOKEN','test-token-which-is-long-enough-123')
    app=create_app('sqlite:///:memory:',data_mode='real_corpus')
    migrate_ingestion_up(app.state.store.engine)
    headers={'Authorization':'Bearer test-token-which-is-long-enough-123','Idempotency-Key':'request-1'}
    with TestClient(app) as c:
        assert c.post(PATH,json=BODY).status_code==401
        # SQLite must not silently stand in for production queue concurrency.
        assert c.post(PATH,json=BODY,headers=headers).status_code==503
        assert c.post(PATH,json={**BODY,'source_url':'https://evil.test/a.pdf'},headers=headers).status_code==422
        assert c.get(PATH+'/missing',headers={'Authorization':'Bearer wrong'}).status_code==401

def test_disabled_without_token(monkeypatch):
    monkeypatch.delenv('INGESTION_ADMIN_TOKEN',raising=False)
    with TestClient(create_app('sqlite:///:memory:',data_mode='real_corpus')) as c:
        response=c.post(PATH,json=BODY)
        assert response.status_code==503
        assert 'token' not in response.text.lower()

def test_postgres_http_lifecycle(monkeypatch):
    import os
    import pytest
    from uuid import uuid4
    from sqlalchemy import create_engine,text,update
    from app.ingestion.task_queue import tasks
    url=os.getenv('TEST_POSTGRES_URL')
    if not url:pytest.skip('dedicated PostgreSQL URL required')
    admin=create_engine(url);schema='api_test_'+uuid4().hex
    with admin.begin() as c:c.execute(text(f'CREATE SCHEMA {schema}'))
    engine=create_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    try:
        migrate_ingestion_up(engine)
        monkeypatch.setenv('INGESTION_ADMIN_TOKEN','test-token-which-is-long-enough-123')
        app=create_app('sqlite:///:memory:',data_mode='real_corpus')
        app.state.store.engine.dispose();app.state.store.engine=engine
        headers={'Authorization':'Bearer test-token-which-is-long-enough-123','Idempotency-Key':'request-1'}
        with TestClient(app) as c:
            first=c.post(PATH,json=BODY,headers=headers)
            assert first.status_code==202,first.text
            task=first.json();assert task['status']=='pending'
            assert 'lease_token' not in task and 'artifact_path' not in task
            assert c.post(PATH,json=BODY,headers=headers).json()['id']==task['id']
            assert c.post(PATH,json={**BODY,'report_period':'2023FY'},headers=headers).status_code==409
            assert c.get(PATH+'/'+task['id'],headers=headers).status_code==200
            assert c.get(PATH+'/'+str(uuid4()),headers=headers).status_code==404
            assert c.post(PATH+'/'+task['id']+'/retry',headers=headers).status_code==409
            with engine.begin() as conn:conn.execute(update(tasks).where(tasks.c.id==task['id']).values(status='failed',attempts=1))
            retry=c.post(PATH+'/'+task['id']+'/retry',headers=headers)
            assert retry.status_code==200 and retry.json()['attempts']==1
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()

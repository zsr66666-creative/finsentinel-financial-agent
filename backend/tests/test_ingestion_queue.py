from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine, inspect
from app.ingestion.task_queue import enqueue_task, claim_task, heartbeat, finish_task, retry_task, QueueConflict
from app.migrations import migrate_ingestion_up, migrate_down

NOW=datetime(2026,11,12,tzinfo=timezone.utc)
REQUEST=dict(source_url='https://static.cninfo.com.cn/a.pdf',company_code='002475',report_period='2026H1',report_type='half_year')

@pytest.fixture
def engine():
    engine=create_engine('sqlite://')
    assert migrate_ingestion_up(engine)==['003_source_ingestion_tasks']
    assert migrate_ingestion_up(engine)==[]
    yield engine
    engine.dispose()

def test_idempotency_and_conflict(engine):
    a=enqueue_task(engine,REQUEST,'key',now=NOW)
    assert enqueue_task(engine,REQUEST,'key',now=NOW)['id']==a['id']
    with pytest.raises(QueueConflict):
        enqueue_task(engine,{**REQUEST,'report_period':'2025FY'},'key',now=NOW)

def test_lease_expiry_and_stale_completion(engine):
    enqueue_task(engine,REQUEST,'key',now=NOW)
    a=claim_task(engine,NOW)
    assert a['attempts']==1 and claim_task(engine,NOW) is None
    assert heartbeat(engine,a['id'],a['lease_token'],NOW+timedelta(seconds=10))
    assert not heartbeat(engine,a['id'],a['lease_token'],NOW+timedelta(seconds=200))
    assert claim_task(engine,NOW+timedelta(seconds=200)) is None
    b=claim_task(engine,NOW+timedelta(seconds=231))
    assert b['attempts']==2
    assert not finish_task(engine,a['id'],a['lease_token'],{},now=NOW+timedelta(seconds=232))
    assert finish_task(engine,b['id'],b['lease_token'],{},now=NOW+timedelta(seconds=232))

def test_retry_budget_and_rollback(engine):
    enqueue_task(engine,REQUEST,'key',now=NOW,max_attempts=1)
    a=claim_task(engine,NOW)
    assert finish_task(engine,a['id'],a['lease_token'],{'error_code':'timeout','retryable':True},now=NOW)
    with pytest.raises(QueueConflict): retry_task(engine,a['id'],NOW)
    assert claim_task(engine,NOW+timedelta(days=1)) is None
    assert migrate_down(engine,'003_source_ingestion_tasks')
    assert 'source_ingestion_tasks' not in inspect(engine).get_table_names()

def test_failed_task_manual_retry_keeps_budget(engine):
    enqueue_task(engine,REQUEST,'key',now=NOW)
    a=claim_task(engine,NOW)
    assert finish_task(engine,a['id'],a['lease_token'],{'error_code':'temporary'},now=NOW)
    assert claim_task(engine,NOW+timedelta(seconds=100)) is None
    assert retry_task(engine,a['id'],NOW)['id']==a['id']
    b=claim_task(engine,NOW)
    assert b['attempts']==2
    with pytest.raises(QueueConflict):retry_task(engine,b['id'],NOW)

def test_postgresql_concurrent_claim_and_expired_token():
    import os
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    from sqlalchemy import text
    from app.ingestion.task_queue import metadata
    url=os.getenv('TEST_POSTGRES_URL')
    if not url:pytest.skip('TEST_POSTGRES_URL not configured; PostgreSQL concurrency not measured')
    admin=create_engine(url)
    schema='queue_test_'+uuid4().hex
    with admin.begin() as conn:conn.execute(text(f'CREATE SCHEMA {schema}'))
    isolated=create_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    try:
        metadata.create_all(isolated)
        enqueue_task(isolated,REQUEST,'key',now=NOW)
        barrier=Barrier(2)
        def claim():
            barrier.wait(timeout=10)
            return claim_task(isolated,NOW)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:claim(),range(2)))
        owners=[r for r in results if r is not None]
        assert len(owners)==1
        a=owners[0]
        assert claim_task(isolated,NOW+timedelta(seconds=181)) is None
        b=claim_task(isolated,NOW+timedelta(seconds=212))
        assert b['attempts']==2 and b['lease_token']!=a['lease_token']
        assert not finish_task(isolated,a['id'],a['lease_token'],{},now=NOW+timedelta(seconds=213))
        assert finish_task(isolated,b['id'],b['lease_token'],{},now=NOW+timedelta(seconds=213))
    finally:
        isolated.dispose()
        with admin.begin() as conn:conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()

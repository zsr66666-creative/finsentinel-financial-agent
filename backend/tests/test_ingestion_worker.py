import hashlib
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from app.migrations import migrate_ingestion_up,migrate_artifacts_up,migrate_down
from app.ingestion.task_queue import enqueue_task,tasks,retry_task
from app.ingestion.worker import run_once,worker_metadata,documents

NOW=datetime(2026,11,12,tzinfo=timezone.utc)
REQUEST=dict(source_url='https://static.cninfo.com.cn/a.pdf',company_code='002475',report_period='2026H1',report_type='half_year')

def test_resume_after_parser_failure_and_duplicate_content(tmp_path):
    engine=create_engine('sqlite://')
    migrate_ingestion_up(engine); worker_metadata.create_all(engine)
    calls=[]
    def download(url,path):
        calls.append(url); path.write_bytes(b'%PDF-fixture')
        return dict(requested_url=url,final_url=url,acquired_at=NOW.isoformat(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def fail(*args):raise ValueError('private parser error')
    def parse(source,meta,directory):
        import json
        json.dumps(meta)  # Real parser persists metadata in JSON.
        assert 'lease_token' not in meta
        return {'sha256':meta['sha256'],'pages':[]}
    task=enqueue_task(engine,REQUEST,'a',now=NOW)
    assert run_once(engine,tmp_path,downloader=download,parser=fail,now=NOW)
    with engine.connect() as c:
        row=c.execute(select(tasks)).mappings().one()
        assert row['status']=='failed' and row['stage']=='downloaded'
    retry_task(engine,task['id'],NOW)
    run_once(engine,tmp_path,downloader=download,parser=parse,now=NOW)
    assert len(calls)==1
    enqueue_task(engine,REQUEST,'b',now=NOW)
    run_once(engine,tmp_path,downloader=download,parser=parse,now=NOW)
    with engine.connect() as c:
        assert len(c.execute(select(documents)).all())==1
        assert all(r['status']=='success' for r in c.execute(select(tasks)).mappings())
    assert len(list((tmp_path/'blobs').glob('*.pdf')))==1
    enqueue_task(engine,REQUEST,'changed',now=NOW)
    def changed(url,path):
        path.write_bytes(b'%PDF-changed')
        return dict(requested_url=url,final_url=url,acquired_at=NOW.isoformat(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    run_once(engine,tmp_path,downloader=changed,parser=parse,now=NOW)
    with engine.connect() as c:assert len(c.execute(select(documents)).all())==2
    assert len(list((tmp_path/'blobs').glob('*.pdf')))==2

def test_artifact_migration_is_versioned_and_reversible():
    engine=create_engine('sqlite://')
    migrate_ingestion_up(engine)
    assert migrate_artifacts_up(engine)==['004_ingestion_artifacts']
    assert migrate_artifacts_up(engine)==[]
    with pytest.raises(ValueError):migrate_down(engine,'003_source_ingestion_tasks')
    assert migrate_down(engine,'004_ingestion_artifacts')

def test_process_timeout_terminates_child(tmp_path,monkeypatch):
    from app.ingestion.worker import bounded_stage
    from app.ingestion.source_policy import DownloadError
    state={'alive':True,'terminated':False}
    class Process:
        pid=123;exitcode=None
        def start(self):pass
        def is_alive(self):return state['alive']
        def join(self,*args):pass
        def terminate(self):state.update(alive=False,terminated=True)
        def close(self):pass
    class Context:
        def Process(self,**kwargs):return Process()
    monkeypatch.setattr('app.ingestion.worker.multiprocessing.get_context',lambda *a:Context())
    with pytest.raises(DownloadError,match='stage_timeout'):
        bounded_stage('download',(),tmp_path,lambda:True,timeout=0)
    assert state['terminated']

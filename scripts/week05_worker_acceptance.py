"""Isolated PostgreSQL fault acceptance, including real process termination."""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import create_engine,select,text,event
from app.ingestion import worker
from app.ingestion.task_queue import enqueue_task,tasks,retry_task
from app.migrations import migrate_ingestion_up,migrate_artifacts_up

NOW=datetime(2026,11,12,tzinfo=timezone.utc)
URL='https://static.cninfo.com.cn/finalpage/2025-04-26/1223326862.PDF'
REQUEST=dict(source_url=URL,company_code='002475',report_period='2024FY',report_type='annual')

def engine_for(schema):
    return create_engine(os.environ['TEST_POSTGRES_URL'],connect_args={'options':f'-csearch_path={schema}'})

def fixture_download(root):
    def download(url,path):
        with (root/'downloads.log').open('a') as f:f.write('download\n')
        payload=(root/'fixture.pdf').read_bytes(); path.write_bytes(payload)
        return dict(requested_url=url,final_url=url,acquired_at=NOW.isoformat(),sha256=hashlib.sha256(payload).hexdigest())
    return download

def fixture_parse(root):
    def parse(path,meta,directory):
        with (root/'parses.log').open('a') as f:f.write('parse\n')
        return dict(sha256=meta['sha256'],pages=[])
    return parse

def child(args):
    engine=engine_for(args.schema)
    original=worker.checkpoint
    def checkpoint(engine,task,stage,values,now):
        original(engine,task,stage,values,now)
        if stage==args.kill_stage:os._exit(79)
    worker.checkpoint=checkpoint
    worker.run_once(engine,args.root,downloader=fixture_download(args.root),parser=fixture_parse(args.root),now=NOW)

def main(args):
    admin=create_engine(os.environ['TEST_POSTGRES_URL'])
    schema='worker_test_'+uuid4().hex
    with admin.begin() as c:c.execute(text(f'CREATE SCHEMA {schema}'))
    engine=engine_for(schema); results=[]
    args.root.mkdir(parents=True,exist_ok=True)
    import pymupdf
    d=pymupdf.open();d.new_page().insert_text((72,72),'Isolated worker recovery fixture');d.save(args.root/'fixture.pdf');d.close()
    try:
        migrate_ingestion_up(engine);migrate_artifacts_up(engine)
        for stage in ('downloaded','parsed'):
            enqueue_task(engine,REQUEST,stage,now=NOW)
            before_downloads=len((args.root/'downloads.log').read_text().splitlines()) if (args.root/'downloads.log').exists() else 0
            before_parses=len((args.root/'parses.log').read_text().splitlines()) if (args.root/'parses.log').exists() else 0
            # Use a distinct report period so the second case cannot reuse first case parse.
            if stage=='parsed':
                with engine.begin() as c:c.execute(tasks.update().where(tasks.c.idempotency_key==stage).values(report_period='2023FY'))
            p=subprocess.run([sys.executable,__file__,'--root',str(args.root),'--schema',schema,'--kill-stage',stage],timeout=20)
            assert p.returncode==79
            with engine.connect() as c:
                row=c.execute(select(tasks).where(tasks.c.idempotency_key==stage)).mappings().one()
                assert row['status']=='running' and row['stage']==stage
            assert worker.run_once(engine,args.root,downloader=fixture_download(args.root),parser=fixture_parse(args.root),now=NOW+timedelta(seconds=181)) is False
            assert worker.run_once(engine,args.root,downloader=fixture_download(args.root),parser=fixture_parse(args.root),now=NOW+timedelta(seconds=212))
            assert len((args.root/'downloads.log').read_text().splitlines())==before_downloads+1
            assert len((args.root/'parses.log').read_text().splitlines())==before_parses+1
            with engine.connect() as c:
                row=c.execute(select(tasks).where(tasks.c.idempotency_key==stage)).mappings().one()
                assert row['status']=='success' and row['attempts']==2
            results.append(dict(check='process_exit_after_'+stage,passed=True))
        # Fail after artifact INSERT but before task success UPDATE; both must roll back.
        req={**REQUEST,'report_period':'2022FY'}
        task=enqueue_task(engine,req,'rollback',now=NOW)
        def fault(conn,cursor,statement,parameters,context,executemany):
            if statement.startswith('UPDATE source_ingestion_tasks') and 'document_id=' in statement:
                raise RuntimeError('injected final update failure')
        event.listen(engine,'before_cursor_execute',fault)
        worker.run_once(engine,args.root,downloader=fixture_download(args.root),parser=fixture_parse(args.root),now=NOW)
        event.remove(engine,'before_cursor_execute',fault)
        with engine.connect() as c:
            assert len(c.execute(select(worker.documents)).all())==2
            assert c.execute(select(tasks.c.status).where(tasks.c.id==task['id'])).scalar_one()=='failed'
        retry_task(engine,task['id'],NOW)
        def no_call(*a):raise AssertionError('checkpoint should be reused')
        worker.run_once(engine,args.root,downloader=no_call,parser=no_call,now=NOW)
        with engine.connect() as c:
            assert len(c.execute(select(worker.documents)).all())==3
            assert c.execute(select(tasks.c.status).where(tasks.c.id==task['id'])).scalar_one()=='success'
        results.append(dict(check='atomic_artifact_and_success_rollback',passed=True))
        # Real official download and real isolated parser, no injected transport.
        task=enqueue_task(engine,{**REQUEST,'report_period':'official-network-check'},'network')
        worker.run_once(engine,args.root)
        with engine.connect() as c:
            row=dict(c.execute(select(tasks).where(tasks.c.id==task['id'])).mappings().one())
            assert row['status']=='success',row['error_code']
            artifact=c.execute(select(worker.documents.c.artifact_path).where(worker.documents.c.id==row['document_id'])).scalar_one()
        parsed=json.loads(Path(artifact).read_text(encoding='utf-8'))
        assert parsed['total_pages']>0 and parsed['pages']
        results.append(dict(check='official_download_real_parser',passed=True,requested_url=row['requested_url'],
            final_url=row['final_url'],sha256=row['sha256'],acquired_at=row['acquired_at'].isoformat(),
            total_pages=parsed['total_pages'],extracted_pages=len(parsed['pages'])))
        version=None
        with engine.connect() as c:version=c.execute(text('SELECT version()')).scalar_one()
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
    report=dict(checks=results,postgres_version=version,limitations=[
        'local PostgreSQL, not ECS deployment','recovery lease time advanced explicitly',
        'single-worker acceptance, not throughput or memory-limit verification',
        'abrupt worker exit injected after committed phase; not mid-syscall power failure'])
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{len(results)}/{len(results)} acceptance checks passed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--schema');p.add_argument('--kill-stage');p.add_argument('--output',type=Path)
    args=p.parse_args()
    child(args) if args.schema else main(args)

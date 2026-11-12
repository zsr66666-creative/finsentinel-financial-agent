"""Single-worker phase recovery; production stages run in bounded subprocesses."""
import argparse
import hashlib
import json
import multiprocessing
import os
import logging
from pathlib import Path
import shutil
import time
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import MetaData,Table,Column,String,select,update
from app.ingestion.task_queue import tasks,claim_task,heartbeat,owner,finish_task
from app.ingestion.source_policy import download_pdf,DownloadError

worker_metadata=MetaData()
documents=Table('ingestion_artifacts',worker_metadata,
    Column('id',String(64),primary_key=True),Column('sha256',String(64),nullable=False),
    Column('company_code',String(200),nullable=False),Column('report_period',String(200),nullable=False),
    Column('report_type',String(200),nullable=False),Column('artifact_path',String(2048),nullable=False))

def hash_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def child_stage(kind,args,result_path):
    try:
        if kind=='download':result=download_pdf(*args)
        else:
            from app.ingestion.pipeline import ingest_pdf
            result=ingest_pdf(*args)
        Path(result_path).write_text(json.dumps({'result':result}),encoding='utf-8')
    except Exception as exc:
        Path(result_path).write_text(json.dumps({'error':getattr(exc,'code','stage_failed'),
            'retryable':getattr(exc,'retryable',False)}),encoding='utf-8')

def bounded_stage(kind,args,directory,pulse,timeout=120):
    result_path=Path(directory)/('result-'+uuid4().hex+'.json')
    process=multiprocessing.get_context('spawn').Process(target=child_stage,args=(kind,args,str(result_path)))
    started=time.monotonic(); last=started
    try:
        process.start()
        while process.is_alive():
            process.join(.2)
            elapsed=time.monotonic()-started
            if elapsed>=timeout:raise DownloadError('stage_timeout',True)
            if time.monotonic()-last>=30:
                if not pulse():raise DownloadError('lease_lost')
                last=time.monotonic()
        if process.exitcode!=0 or not result_path.exists():raise DownloadError('stage_process_failed',True)
        data=json.loads(result_path.read_text(encoding='utf-8'))
        if 'error' in data:raise DownloadError(data['error'],data['retryable'])
        return data['result']
    finally:
        if process.pid is not None:
            if process.is_alive():process.terminate(); process.join(3)
            if process.is_alive():process.kill(); process.join(3)
            process.close()
        result_path.unlink(missing_ok=True)

def checkpoint(engine,task,stage,values,now):
    with engine.begin() as c:
        if c.execute(update(tasks).where(owner(task['id'],task['lease_token'],now())).values(stage=stage,**values)).rowcount!=1:
            raise DownloadError('lease_lost')

def run_once(engine,artifact_root,downloader=None,parser=None,now=None):
    current=(lambda:now) if now else (lambda:datetime.now(timezone.utc))
    task=claim_task(engine,current())
    if task is None:return False
    root=Path(artifact_root).resolve(); root.mkdir(parents=True,exist_ok=True)
    work=root/(task['id']+'-'+uuid4().hex); work.mkdir()
    pulse=lambda:heartbeat(engine,task['id'],task['lease_token'],current())
    try:
        blob=root/'blobs'/f"{task['sha256']}.pdf" if task['sha256'] else None
        if blob is None or not blob.exists() or hash_file(blob)!=task['sha256']:
            path=work/'source.pdf'
            result=downloader(task['source_url'],path) if downloader else bounded_stage('download',(task['source_url'],path),work,pulse)
            digest=hash_file(path)
            if digest!=result['sha256']:raise DownloadError('download_hash_mismatch')
            blob=root/'blobs'/f'{digest}.pdf'; blob.parent.mkdir(exist_ok=True)
            if blob.exists():
                if hash_file(blob)!=digest:raise DownloadError('blob_corrupt')
            else:
                try:os.link(path,blob)
                except FileExistsError:
                    if hash_file(blob)!=digest:raise DownloadError('blob_corrupt')
            values={k:result[k] for k in ('requested_url','final_url')}
            values.update(sha256=digest,acquired_at=datetime.fromisoformat(result['acquired_at']),artifact_path=str(blob))
            checkpoint(engine,task,'downloaded',values,current); task.update(values)
        from app.ingestion.pipeline import fitz
        parser_version='pymupdf-'+fitz.VersionBind
        identity=hashlib.sha256(json.dumps([task[k] for k in ('company_code','report_period','report_type','sha256')]).encode()).hexdigest()
        parsed=root/'parsed'/parser_version/(identity+'.json'); parsed.parent.mkdir(parents=True,exist_ok=True)
        valid=False
        if parsed.exists():
            try:
                existing=json.loads(parsed.read_text(encoding='utf-8'))
                valid=existing['sha256']==task['sha256'] and existing['parser_version']==parser_version
            except (ValueError,KeyError):pass
        if not valid:
            meta={k:task[k] for k in ('company_code','report_period','report_type','source_url','sha256','requested_url','final_url')}
            meta.update(id=identity,acquired_at=task['acquired_at'].isoformat())
            result=parser(blob,meta,work) if parser else bounded_stage('parse',(blob,meta,work),work,pulse)
            if result['sha256']!=task['sha256']:raise DownloadError('parse_hash_mismatch')
            result['parser_version']=parser_version
            temp=work/'parsed.json'; temp.write_text(json.dumps(result),encoding='utf-8')
            os.replace(temp,parsed)
        checkpoint(engine,task,'parsed',{},current)
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert=pg_insert if engine.dialect.name=='postgresql' else sqlite_insert
        with engine.begin() as c:
            owned=c.execute(select(tasks.c.id).where(owner(task['id'],task['lease_token'],current())).with_for_update()).first()
            if not owned:raise DownloadError('lease_lost')
            c.execute(insert(documents).values(id=identity,sha256=task['sha256'],company_code=task['company_code'],
                report_period=task['report_period'],report_type=task['report_type'],artifact_path=str(parsed)).on_conflict_do_nothing())
            updated=c.execute(update(tasks).where(owner(task['id'],task['lease_token'],current())).values(status='success',stage='committed',
                document_id=identity,finished_at=current(),lease_token=None,lease_until=None,retryable=False))
            if updated.rowcount!=1:raise DownloadError('lease_lost')
    except Exception as exc:
        finish_task(engine,task['id'],task['lease_token'],dict(error_code=getattr(exc,'code','worker_stage_failed'),
            retryable=getattr(exc,'retryable',False)),now=current())
    finally:
        try:shutil.rmtree(work)
        except OSError:logging.getLogger(__name__).warning('worker temporary cleanup failed for task %s',task['id'])
    return True

def main():
    from sqlalchemy import create_engine
    p=argparse.ArgumentParser(); p.add_argument('--once',action='store_true'); p.add_argument('--artifact-root',type=Path,required=True)
    args=p.parse_args(); engine=create_engine(os.environ['DATABASE_URL'])
    if engine.dialect.name!='postgresql':raise ValueError('production worker requires PostgreSQL')
    try:
        while True:
            ran=run_once(engine,args.artifact_root)
            if args.once:break
            if not ran:time.sleep(2)
    finally:engine.dispose()

if __name__=='__main__':main()

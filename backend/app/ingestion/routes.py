"""Disabled-by-default authenticated administration of source tasks."""
import os
import secrets
from threading import Lock
from time import monotonic
from uuid import UUID
from fastapi import APIRouter,Depends,Header,HTTPException
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import select,func
from sqlalchemy.exc import SQLAlchemyError
from app.ingestion.source_policy import check_url,DownloadError
from app.ingestion.task_queue import tasks,enqueue_task,retry_task,QueueConflict

class SourceTaskRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_url:str=Field(min_length=1,max_length=2048)
    company_code:str=Field(pattern=r'^\d{6}$')
    report_period:str=Field(pattern=r'^\d{4}(FY|H1|Q[1-4])$')
    report_type:str=Field(pattern=r'^(annual|half_year|quarterly|announcement)$')

    @field_validator('source_url')
    @classmethod
    def official(cls,value):
        try:check_url(value)
        except DownloadError:raise ValueError('invalid official source') from None
        return value

def build_router(store):
    router=APIRouter(prefix='/api/v1/admin/source-ingestion/tasks')
    lock=Lock(); writes=[]
    def authorize(authorization:str|None=Header(default=None)):
        expected=os.getenv('INGESTION_ADMIN_TOKEN','')
        if len(expected)<32:raise HTTPException(503,'source_ingestion_disabled')
        if not authorization or not secrets.compare_digest(authorization.encode(),('Bearer '+expected).encode()):
            raise HTTPException(401,'unauthorized')
    def engine():
        value=getattr(store,'engine',None)
        if value is None or value.dialect.name!='postgresql':raise HTTPException(503,'source_queue_unavailable')
        return value
    def rate_limit():
        with lock:
            now=monotonic();writes[:]=[t for t in writes if now-t<60]
            if len(writes)>=10:raise HTTPException(429,'source_write_rate_limit')
            writes.append(now)
    def public(row):
        return {k:row[k] for k in ('id','status','stage','attempts','max_attempts','created_at','started_at',
            'finished_at','next_attempt_at','company_code','report_period','report_type','source_url',
            'final_url','acquired_at','sha256','document_id','error_code')}
    def valid_id(value):
        try:UUID(value)
        except ValueError:raise HTTPException(404,'task_not_found') from None

    @router.post('',status_code=202,dependencies=[Depends(authorize)])
    def enqueue(body:SourceTaskRequest,idempotency_key:str=Header(alias='Idempotency-Key',min_length=1,max_length=200)):
        rate_limit();e=engine()
        try:
            # A shared transaction advisory lock serializes capacity + enqueue.
            # enqueue_task uses a separate connection; lock is held through completion.
            with e.begin() as c:
                from sqlalchemy import text
                c.execute(text('SELECT pg_advisory_xact_lock(572005)'))
                existing=c.execute(select(tasks.c.id).where(tasks.c.idempotency_key==idempotency_key)).first()
                count=c.execute(select(func.count()).select_from(tasks).where(tasks.c.status.in_(['pending','running']))).scalar_one()
                if not existing and count>=100:raise HTTPException(429,'source_queue_full')
                return public(enqueue_task(e,body.model_dump(),idempotency_key))
        except QueueConflict:raise HTTPException(409,'idempotency_conflict') from None
        except SQLAlchemyError:raise HTTPException(503,'source_queue_unavailable') from None

    @router.get('/{task_id}',dependencies=[Depends(authorize)])
    def get_task(task_id:str):
        valid_id(task_id);e=engine()
        try:
            with e.connect() as c:row=c.execute(select(tasks).where(tasks.c.id==task_id)).mappings().first()
            if row is None:raise HTTPException(404,'task_not_found')
            return public(row)
        except SQLAlchemyError:raise HTTPException(503,'source_queue_unavailable') from None

    @router.post('/{task_id}/retry',dependencies=[Depends(authorize)])
    def retry(task_id:str):
        valid_id(task_id);rate_limit();e=engine()
        try:
            with e.connect() as c:
                if not c.execute(select(tasks.c.id).where(tasks.c.id==task_id)).first():raise HTTPException(404,'task_not_found')
            return public(retry_task(e,task_id))
        except QueueConflict:raise HTTPException(409,'task_not_retryable') from None
        except SQLAlchemyError:raise HTTPException(503,'source_queue_unavailable') from None
    return router

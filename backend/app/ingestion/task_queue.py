"""Durable queue primitives. PostgreSQL is required for concurrent workers."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import (MetaData, Table, Column, String, Integer, DateTime, Boolean,
                        CheckConstraint, select, update, or_, and_)
from app.ingestion.pipeline import validate_source_url

metadata=MetaData()
tasks=Table('source_ingestion_tasks',metadata,
    Column('id',String(36),primary_key=True),
    *[Column(k,String(2048 if k.endswith('url') else 200),nullable=False) for k in
      ('source_url','company_code','report_period','report_type','idempotency_key','request_sha256')],
    Column('status',String(16),nullable=False),Column('stage',String(16),nullable=False),
    Column('attempts',Integer,nullable=False),Column('max_attempts',Integer,nullable=False),
    Column('retryable',Boolean,nullable=False),Column('lease_token',String(36)),
    *[Column(k,DateTime(timezone=True)) for k in ('next_attempt_at','lease_until','created_at','started_at','finished_at','acquired_at')],
    *[Column(k,String(2048)) for k in ('requested_url','final_url','sha256','artifact_path','document_id','error_code')],
    CheckConstraint("status IN ('pending','running','success','failed')",name='ck_ingestion_status'),
    CheckConstraint("stage IN ('queued','downloaded','parsed','committed')",name='ck_ingestion_stage'),
    CheckConstraint('attempts >= 0 AND max_attempts BETWEEN 1 AND 3 AND attempts <= max_attempts',name='ck_ingestion_attempts'))
from sqlalchemy import Index
Index('uq_ingestion_idempotency',tasks.c.idempotency_key,unique=True)
Index('ix_ingestion_ready',tasks.c.status,tasks.c.next_attempt_at,tasks.c.created_at)

class QueueConflict(ValueError):
    pass

def clock(value=None):
    value=value or datetime.now(timezone.utc)
    if value.tzinfo is None: raise ValueError('timezone-aware time required')
    return value

def enqueue_task(engine,request,idempotency_key,*,now=None,max_attempts=3):
    now=clock(now)
    keys=('source_url','company_code','report_period','report_type')
    if set(request)!=set(keys) or any(not isinstance(request[k],str) or not request[k].strip() for k in keys):
        raise ValueError('exact nonempty request fields required')
    if not isinstance(idempotency_key,str) or not 1<=len(idempotency_key)<=200 or type(max_attempts)is not int or not 1<=max_attempts<=3:
        raise ValueError('invalid idempotency key or attempt budget')
    validate_source_url(request['source_url'],resolve=False)
    digest=hashlib.sha256(json.dumps(request,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    values=dict(request,id=str(uuid4()),idempotency_key=idempotency_key,request_sha256=digest,
                status='pending',stage='queued',attempts=0,max_attempts=max_attempts,retryable=False,created_at=now)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if engine.dialect.name=='postgresql' else sqlite_insert
    with engine.begin() as conn:
        conn.execute(insert(tasks).values(**values).on_conflict_do_nothing(index_elements=['idempotency_key']))
        row=conn.execute(select(tasks).where(tasks.c.idempotency_key==idempotency_key)).mappings().one()
        if row['request_sha256']!=digest or row['max_attempts']!=max_attempts:
            raise QueueConflict('idempotency conflict')
        return dict(row)

def claim_task(engine,now=None):
    now=clock(now)
    with engine.begin() as conn:
        # Reclaim expired owners, retaining phase checkpoints and retry budget.
        expired=select(tasks).where(tasks.c.status=='running',tasks.c.lease_until<=now)
        if engine.dialect.name=='postgresql': expired=expired.with_for_update(skip_locked=True)
        for row in conn.execute(expired).mappings():
            conn.execute(update(tasks).where(tasks.c.id==row['id'],tasks.c.lease_token==row['lease_token']).values(
                status='failed',retryable=True,error_code='worker_lease_expired',finished_at=now,
                lease_token=None,lease_until=None,next_attempt_at=now+timedelta(seconds=30 if row['attempts']==1 else 120)))
        eligible=or_(tasks.c.status=='pending',and_(tasks.c.status=='failed',tasks.c.retryable.is_(True),tasks.c.next_attempt_at<=now))
        query=select(tasks).where(eligible,tasks.c.attempts<tasks.c.max_attempts).order_by(tasks.c.created_at,tasks.c.id).limit(1)
        if engine.dialect.name=='postgresql': query=query.with_for_update(skip_locked=True)
        row=conn.execute(query).mappings().first()
        if row is None:return None
        values=dict(status='running',attempts=row['attempts']+1,lease_token=str(uuid4()),
            lease_until=now+timedelta(seconds=180),started_at=now,finished_at=None,next_attempt_at=None,error_code=None)
        conn.execute(update(tasks).where(tasks.c.id==row['id']).values(**values))
        return {**row,**values}

def owner(task_id,token,now):
    return and_(tasks.c.id==task_id,tasks.c.status=='running',tasks.c.lease_token==token,tasks.c.lease_until>now)

def heartbeat(engine,task_id,token,now=None):
    now=clock(now)
    with engine.begin() as conn:
        return conn.execute(update(tasks).where(owner(task_id,token,now)).values(lease_until=now+timedelta(seconds=180))).rowcount==1

def finish_task(engine,task_id,token,result,*,now=None):
    now=clock(now)
    allowed={'error_code','retryable','requested_url','final_url','acquired_at','sha256','artifact_path','document_id'}
    if set(result)-allowed: raise ValueError('unknown completion fields')
    with engine.begin() as conn:
        query=select(tasks).where(owner(task_id,token,now)).with_for_update()
        row=conn.execute(query).mappings().first()
        if row is None:return False
        failed=bool(result.get('error_code'))
        values={**result,'status':'failed' if failed else 'success','finished_at':now,
                'lease_token':None,'lease_until':None,'retryable':bool(failed and result.get('retryable')),
                'next_attempt_at':None}
        if not failed:values['stage']='committed'
        if failed and values['retryable'] and row['attempts']<row['max_attempts']:
            values['next_attempt_at']=now+timedelta(seconds=30 if row['attempts']==1 else 120)
        conn.execute(update(tasks).where(owner(task_id,token,now)).values(**values))
        return True

def retry_task(engine,task_id,now=None):
    now=clock(now)
    with engine.begin() as conn:
        row=conn.execute(select(tasks).where(tasks.c.id==task_id).with_for_update()).mappings().first()
        if row is None or row['status']!='failed' or row['attempts']>=row['max_attempts']:
            raise QueueConflict('task not retryable within budget')
        conn.execute(update(tasks).where(tasks.c.id==task_id).values(status='pending',next_attempt_at=now))
        return {**row,'status':'pending','next_attempt_at':now}

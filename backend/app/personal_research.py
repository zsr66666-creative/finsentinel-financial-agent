"""Durable owner-scoped research records; schema changes are explicit CLI actions."""
import hashlib
import json
import time
from urllib.parse import urlencode
from uuid import uuid4
from sqlalchemy import MetaData, Table, Column, String, Text, Float, JSON, UniqueConstraint, ForeignKey, select, func, text, inspect
from app.auth.service import Accounts, users
from app.corpus_catalog import list_scopes

metadata=MetaData()
favorites=Table('personal_research_favorites',metadata,
    Column('id',String(36),primary_key=True),Column('owner_id',String(36),ForeignKey(users.c.id),nullable=False,index=True),
    Column('identity',String(64),nullable=False),Column('kind',String(10),nullable=False),
    Column('company_code',String(100),nullable=False),Column('period',String(40)),Column('chunk_id',String(200)),
    Column('note',Text,nullable=False),Column('snapshot',JSON,nullable=False),
    Column('created_at',Float,nullable=False),Column('updated_at',Float,nullable=False),
    UniqueConstraint('owner_id','identity'))
history=Table('personal_research_history',metadata,
    Column('id',String(36),primary_key=True),Column('owner_id',String(36),ForeignKey(users.c.id),nullable=False,index=True),
    Column('kind',String(10),nullable=False),Column('company_code',String(100)),Column('period',String(40)),
    Column('query',Text,nullable=False),Column('created_at',Float,nullable=False))
VERSION='007_personal_research'

def validate_schema(c):
    inspector=inspect(c)
    for table in metadata.tables.values():
        if table.name not in inspector.get_table_names():raise ValueError('research_schema_missing')
        if set(table.c.keys())!={column['name'] for column in inspector.get_columns(table.name)}:raise ValueError('research_schema_mismatch')
        if not any(fk['constrained_columns']==['owner_id'] and fk['referred_table']=='account_users' for fk in inspector.get_foreign_keys(table.name)):raise ValueError('research_owner_constraint_missing')

def check_research_library(engine):
    with engine.connect() as c:
        validate_schema(c)
        if not c.execute(text('SELECT 1 FROM schema_migrations WHERE name=:n'),{'n':VERSION}).first():raise ValueError('research_schema_unversioned')
    return True

def migrate_research_library(engine):
    from app.migrations import _ensure_version_table
    with engine.begin() as c:
        if engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(572016)'))
        if 'account_users' not in inspect(c).get_table_names():raise ValueError('accounts_schema_required')
        _ensure_version_table(c)
        version=c.execute(text('SELECT 1 FROM schema_migrations WHERE name=:n'),{'n':VERSION}).first()
        existing=set(inspect(c).get_table_names()) & set(metadata.tables)
        if version:
            if existing!=set(metadata.tables):raise ValueError('research_schema_mismatch')
            validate_schema(c)
            return []
        if existing:raise ValueError('unversioned_research_tables')
        metadata.create_all(c)
        c.execute(text('INSERT INTO schema_migrations(name,applied_at) VALUES (:n,:t)'),{'n':VERSION,'t':str(time.time())})
    return [VERSION]

class ResearchLibrary:
    def __init__(self,store):self.store=store;self.engine=getattr(store,"engine",None)
    def scope(self,company,period=None):
        scopes=[s for s in list_scopes(self.engine)['items'] if s['company_code']==company and (period is None or s['period']==period)]
        fixture=self.store.get('companies',company)
        if not scopes and (period is not None or not fixture):raise ValueError('scope_not_found')
        return dict(company_code=company,company_name=scopes[0]['company_name'] if scopes else fixture.get('name',company),period=period)
    def snapshot(self,kind,company,period,chunk):
        if kind=='company':
            if chunk:raise ValueError('invalid_chunk')
            return self.scope(company,period)
        if kind!='evidence' or not chunk:raise ValueError('invalid_favorite')
        if not inspect(self.engine).has_table('document_chunk_embeddings'):raise ValueError('evidence_not_found')
        with self.engine.connect() as c:
            row=c.execute(text('SELECT provenance,text_sha256 FROM document_chunk_embeddings WHERE chunk_id=:id'),{'id':chunk}).mappings().first()
        if not row:raise ValueError('evidence_not_found')
        p=json.loads(row['provenance']) if isinstance(row['provenance'],str) else row['provenance']
        if not p or p.get('company_code')!=company or (period and p.get('period')!=period) or not isinstance(p.get('text'),str) or not p['text'].strip():raise ValueError('evidence_scope_invalid')
        return {k:p.get(k) for k in ('company_code','period','text','page','document_id','document_sha256','source_url','source_status')} | {'text_sha256':row['text_sha256']}
    @staticmethod
    def public(row):
        result={k:v for k,v in row.items() if k not in ('owner_id','identity')}
        if 'query' in result:
            params={'q':result['query']}
            if result.get('company_code'):params['company']=result['company_code']
            if result.get('period'):params['period']=result['period']
            result['href']=('/evidence?' if result['kind']=='search' else '/compare?')+urlencode(params)
        return result
    def listing(self,owner,history=False,offset=0,limit=30,kind=None,company_code=None,period=None,chunk_id=None):
        if offset<0 or not 1<=limit<=100:raise ValueError('invalid_pagination')
        table=globals()['history'] if history else favorites
        filters=[table.c.owner_id==owner]
        for name,value in (('kind',kind),('company_code',company_code),('period',period),('chunk_id',chunk_id)):
            if value is not None and name in table.c:filters.append(table.c[name]==value)
        with self.engine.connect() as c:
            total=c.execute(select(func.count()).select_from(table).where(*filters)).scalar()
            rows=c.execute(select(table).where(*filters).order_by(table.c.created_at.desc(),table.c.id.desc()).offset(offset).limit(limit)).mappings()
            return {'items':[self.public(r) for r in rows],'total':total}
    def favorite(self,owner,*,kind,company_code,period=None,chunk_id=None,note=None):
        if note is not None and len(note)>1000:raise ValueError('note_too_long')
        snap=self.snapshot(kind,company_code,period,chunk_id)
        period=snap.get('period')
        identity=hashlib.sha256(json.dumps([kind,company_code,period,chunk_id]).encode()).hexdigest()
        with Accounts(self.engine).transaction() as c:
            old=c.execute(select(favorites).where(favorites.c.owner_id==owner,favorites.c.identity==identity)).mappings().first()
            if old:
                # Repeated favorite never silently overwrites an existing private note or snapshot.
                return self.public(old)
            if c.execute(select(func.count()).select_from(favorites).where(favorites.c.owner_id==owner)).scalar()>=500:raise ValueError('favorites_limit')
            now=time.time();row=dict(id=str(uuid4()),owner_id=owner,identity=identity,kind=kind,company_code=company_code,period=period,chunk_id=chunk_id,note=note or '',snapshot=snap,created_at=now,updated_at=now)
            c.execute(favorites.insert().values(**row))
        return self.public(row)
    def note(self,owner,ident,note):
        if len(note)>1000:raise ValueError('note_too_long')
        with Accounts(self.engine).transaction() as c:
            row=c.execute(select(favorites).where(favorites.c.owner_id==owner,favorites.c.id==ident)).mappings().first()
            if not row:raise ValueError('not_found')
            row=dict(row,note=note,updated_at=time.time());c.execute(favorites.update().where(favorites.c.owner_id==owner,favorites.c.id==ident).values(note=note,updated_at=row['updated_at']))
        return self.public(row)
    def remove(self,owner,ident,history_record=False):
        table=history if history_record else favorites
        with Accounts(self.engine).transaction() as c:
            if not c.execute(table.delete().where(table.c.owner_id==owner,table.c.id==ident)).rowcount:raise ValueError('not_found')
    def record(self,owner,*,kind,query,company_code=None,period=None):
        query=query.strip()
        if kind not in ('search','compare') or not 1<=len(query)<=1000 or (period and not company_code) or (kind=='search' and (not company_code or not period)):raise ValueError('invalid_history')
        if company_code:self.scope(company_code,period)
        row=dict(id=str(uuid4()),owner_id=owner,kind=kind,query=query,company_code=company_code,period=period,created_at=time.time())
        with Accounts(self.engine).transaction() as c:
            c.execute(history.insert().values(**row))
            old=list(c.execute(select(history.c.id).where(history.c.owner_id==owner).order_by(history.c.created_at.desc(),history.c.id.desc()).offset(200)).scalars())
            if old:c.execute(history.delete().where(history.c.owner_id==owner,history.c.id.in_(old)))
        return self.public(row)
    def clear(self,owner):
        with Accounts(self.engine).transaction() as c:c.execute(history.delete().where(history.c.owner_id==owner))

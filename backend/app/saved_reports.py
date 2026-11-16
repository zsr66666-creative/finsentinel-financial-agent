"""Immutable private report snapshots; schema changes are explicit operator actions."""
import hashlib
import json
import os
import time
from uuid import uuid4
from sqlalchemy import MetaData, Table, Column, String, Text, Float, ForeignKey, select, func, text, inspect
from app.auth.service import Accounts, users
from app.verified_financials import company_comparisons, DEFAULT_ARTIFACT_ROOT
from app.research_export import export_research, render_research

metadata=MetaData()
reports=Table('saved_research_reports',metadata,
    Column('id',String(36),primary_key=True),
    Column('owner_id',String(36),ForeignKey(users.c.id),nullable=False,index=True),
    Column('title',String(120),nullable=False),Column('question',Text),
    Column('company_code',String(6),nullable=False),Column('period',String(40),nullable=False),
    Column('statement_scope',String(40),nullable=False),Column('created_at',Float,nullable=False,index=True),
    Column('snapshot_json',Text,nullable=False),Column('snapshot_sha256',String(64),nullable=False))
VERSION='008_saved_research_reports'
MAX_SNAPSHOT_BYTES=2*1024*1024


def validate_schema(c):
    inspector=inspect(c)
    if reports.name not in inspector.get_table_names():raise ValueError('saved_reports_schema_missing')
    if set(reports.c.keys())!={col['name'] for col in inspector.get_columns(reports.name)}:raise ValueError('saved_reports_schema_mismatch')
    if any(col['nullable'] for col in inspector.get_columns(reports.name) if col['name'] not in ('question','id')):raise ValueError('saved_reports_schema_mismatch')
    if inspector.get_pk_constraint(reports.name)['constrained_columns']!=['id']:raise ValueError('saved_reports_primary_key_missing')
    if not any(fk['constrained_columns']==['owner_id'] and fk['referred_table']=='account_users' and fk['referred_columns']==['id'] for fk in inspector.get_foreign_keys(reports.name)):raise ValueError('saved_reports_owner_constraint_missing')
    indexed={tuple(index['column_names']) for index in inspector.get_indexes(reports.name)}
    if not {('owner_id',),('created_at',)}<=indexed:raise ValueError('saved_reports_indexes_missing')


def check_saved_reports(engine):
    with engine.connect() as c:
        validate_schema(c)
        if 'schema_migrations' not in inspect(c).get_table_names() or not c.execute(text('SELECT 1 FROM schema_migrations WHERE name=:n'),{'n':VERSION}).first():raise ValueError('saved_reports_schema_unversioned')
    return True


def migrate_saved_reports(engine):
    from app.migrations import _ensure_version_table
    with engine.begin() as c:
        if engine.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(572017)'))
        if 'account_users' not in inspect(c).get_table_names():raise ValueError('accounts_schema_required')
        _ensure_version_table(c)
        version=c.execute(text('SELECT 1 FROM schema_migrations WHERE name=:n'),{'n':VERSION}).first()
        if version:validate_schema(c);return []
        if reports.name in inspect(c).get_table_names():raise ValueError('unversioned_saved_reports_table')
        metadata.create_all(c)
        validate_schema(c)
        c.execute(text('INSERT INTO schema_migrations(name,applied_at) VALUES (:n,:t)'),{'n':VERSION,'t':str(time.time())})
    return [VERSION]


class SavedReports:
    def __init__(self,store):self.engine=getattr(store,'engine',None)
    @staticmethod
    def public(row,detail=False):
        result={k:v for k,v in row.items() if k not in ('owner_id','snapshot_json')}
        if detail:result['snapshot']=json.loads(row['snapshot_json'])
        return result
    def listing(self,owner,offset=0,limit=30):
        if offset<0 or not 1<=limit<=100:raise ValueError('invalid_pagination')
        with self.engine.connect() as c:
            total=c.execute(select(func.count()).select_from(reports).where(reports.c.owner_id==owner)).scalar()
            rows=c.execute(select(reports).where(reports.c.owner_id==owner).order_by(reports.c.created_at.desc(),reports.c.id.desc()).offset(offset).limit(limit)).mappings()
            return {'items':[self.public(row) for row in rows],'total':total}
    def create(self,owner,*,company_code,title,period='2024FY',statement_scope='consolidated',question=None):
        title=title.strip()
        if company_code not in ('002555','002230') or period!='2024FY' or statement_scope!='consolidated':raise ValueError('unsupported_saved_report_scope')
        if not 1<=len(title)<=120 or (question is not None and len(question)>1000):raise ValueError('invalid_saved_report_text')
        if any(ord(char)<32 and char not in '\n\r\t' for value in (title,question or '') for char in value):raise ValueError('invalid_saved_report_text')
        try:
            source=company_comparisons(self.engine,company_code,period,statement_scope,os.getenv('INGESTION_ARTIFACT_ROOT',DEFAULT_ARTIFACT_ROOT))
            report=json.loads(export_research(self.engine,source,'json'))
            report.update(saved_title=title,saved_question=question,saved_snapshot=True)
            snapshot=render_research(report,'json')
        except Exception as exc:raise SourceUnavailable() from exc
        encoded=snapshot.encode('utf-8')
        if len(encoded)>MAX_SNAPSHOT_BYTES:raise ValueError('saved_report_snapshot_too_large')
        row=dict(id=str(uuid4()),owner_id=owner,title=title,question=question,company_code=company_code,period=period,statement_scope=statement_scope,created_at=time.time(),snapshot_json=snapshot,snapshot_sha256=hashlib.sha256(encoded).hexdigest())
        with Accounts(self.engine).transaction() as c:
            if not c.execute(select(users.c.id).where(users.c.id==owner)).first():raise ValueError('authentication_required')
            if c.execute(select(func.count()).select_from(reports).where(reports.c.owner_id==owner)).scalar()>=200:raise ValueError('saved_reports_limit')
            c.execute(reports.insert().values(**row))
        return self.public(row)
    def _row(self,owner,ident):
        with self.engine.connect() as c:
            row=c.execute(select(reports).where(reports.c.owner_id==owner,reports.c.id==ident)).mappings().first()
            if not row:raise ValueError('not_found')
            return dict(row)
    def detail(self,owner,ident):return self.public(self._row(owner,ident),True)
    def export(self,owner,ident,format='json'):
        row=self._row(owner,ident)
        return row['snapshot_json'] if format=='json' else render_research(json.loads(row['snapshot_json']),format)
    def remove(self,owner,ident):
        with Accounts(self.engine).transaction() as c:
            if not c.execute(reports.delete().where(reports.c.owner_id==owner,reports.c.id==ident)).rowcount:raise ValueError('not_found')


class SourceUnavailable(Exception):pass

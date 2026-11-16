"""Disposable PostgreSQL acceptance: migration, isolation, immutable export and persistence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from app.auth.service import Accounts,migrate_accounts
from app.financial_reviews import migrate_reviews
from app.saved_reports import SavedReports,migrate_saved_reports,check_saved_reports,reports


def accept(engine):
    if engine.dialect.name!='postgresql':raise ValueError('PostgreSQL required')
    schema='saved_reports_accept_'+uuid4().hex
    with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated=create_engine(engine.url,connect_args={'options':'-csearch_path='+schema})
    replay=None
    try:
        migrate_accounts(isolated);migrate_reviews(isolated)
        assert migrate_saved_reports(isolated)==['008_saved_research_reports']
        assert migrate_saved_reports(isolated)==[];check_saved_reports(isolated)
        accounts=Accounts(isolated);suffix=uuid4().hex[:12]
        alice=accounts.create_user('saved_a_'+suffix,'isolated password','viewer','Alice')['id']
        bob=accounts.create_user('saved_b_'+suffix,'isolated password','viewer','Bob')['id']
        class Source:
            def __init__(self,db):self.engine=db
        service=SavedReports(Source(isolated))
        saved=service.create(alice,company_code='002555',title='Frozen report',question='Private question')
        assert service.listing(bob)['total']==0
        for read in (service.detail,service.export,service.remove):
            try:read(bob,saved['id'])
            except ValueError as exc:assert str(exc)=='not_found'
            else:raise AssertionError('owner isolation failure')
        original=service.export(alice,saved['id'])
        replay=create_engine(engine.url,connect_args={'options':'-csearch_path='+schema})
        durable=SavedReports(Source(replay))
        assert durable.export(alice,saved['id'])==original
        assert durable.detail(alice,saved['id'])['question']=='Private question'
        assert '证据不足' in durable.export(alice,saved['id'],'markdown')
        # Fill with existing server-derived bytes, then exercise concurrent cap enforcement.
        with isolated.begin() as c:
            template=dict(c.execute(reports.select()).mappings().first())
            c.execute(reports.insert(),[template|{'id':str(uuid4())} for _ in range(198)])
        def create(_):
            try:service.create(alice,company_code='002555',title='Cap test');return True
            except ValueError as exc:assert str(exc)=='saved_reports_limit';return False
        with ThreadPoolExecutor(max_workers=4) as pool:created=list(pool.map(create,range(4)))
        assert sum(created)==1 and service.listing(alice)['total']==200
        assert len(service.listing(alice,offset=1,limit=100)['items'])==100
        service.remove(alice,saved['id']);assert service.listing(alice)['total']==199
    finally:
        if replay is not None:replay.dispose()
        isolated.dispose()
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    result={'status':'passed','isolated_schema_removed':True,'checks':['migration_idempotence','owner_isolation','fresh_connection_persistence','frozen_export','concurrent_owner_cap','pagination','owner_scoped_delete']}
    print(json.dumps(result));return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    engine=create_engine(os.environ['DATABASE_URL'])
    try:args.output.write_text(json.dumps(accept(engine),indent=2)+'\n',encoding='utf-8')
    finally:engine.dispose()

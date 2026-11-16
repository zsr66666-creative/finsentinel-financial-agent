"""Research library persistence/isolation/concurrency in a disposable PostgreSQL schema."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from app.auth.service import Accounts,migrate_accounts
from app.personal_research import ResearchLibrary,migrate_research_library,check_research_library


def accept(engine):
    if engine.dialect.name!='postgresql':raise ValueError('PostgreSQL required')
    schema='research_accept_'+uuid4().hex
    with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated=create_engine(engine.url,connect_args={'options':'-csearch_path='+schema})
    replay=None
    try:
        migrate_accounts(isolated)
        assert migrate_research_library(isolated)==['007_personal_research']
        assert migrate_research_library(isolated)==[]
        check_research_library(isolated)
        accounts=Accounts(isolated)
        alice=accounts.create_user('research_alice','isolated password','viewer','Alice')['id']
        bob=accounts.create_user('research_bobby','isolated password','viewer','Bob')['id']
        class Source:
            def __init__(self,db):self.engine=db
            def get(self,table,key):return {'name':'Isolated company'} if key=='000001' else None
        service=ResearchLibrary(Source(isolated))
        def favorite(_):return service.favorite(alice,kind='company',company_code='000001')['id']
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(favorite,range(8)))
        assert len(set(ids))==1 and service.listing(alice)['total']==1
        assert service.listing(bob)['total']==0
        try:service.note(bob,ids[0],'forbidden')
        except ValueError as exc:assert str(exc)=='not_found'
        else:raise AssertionError('owner isolation failure')
        service.note(alice,ids[0],'Durable note')
        replay=create_engine(engine.url,connect_args={'options':'-csearch_path='+schema})
        assert ResearchLibrary(Source(replay)).listing(alice)['items'][0]['note']=='Durable note'
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda i:service.record(alice,kind='compare',query='query '+str(i)),range(205)))
        assert service.listing(alice,history=True)['total']==200
        service.record(bob,kind='compare',query='compare company revenue')
        service.clear(alice)
        assert service.listing(alice,history=True)['total']==0 and service.listing(bob,history=True)['total']==1
    finally:
        if replay is not None:replay.dispose()
        isolated.dispose()
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    result={'status':'passed','isolated_schema_removed':True,'checks':['migration_idempotence','concurrent_favorite_uniqueness','owner_isolation','fresh_connection_persistence','concurrent_history_cap','owner_scoped_clear']}
    print(json.dumps(result));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    engine=create_engine(os.environ['DATABASE_URL'])
    try:args.output.write_text(json.dumps(accept(engine),indent=2)+'\n')
    finally:engine.dispose()

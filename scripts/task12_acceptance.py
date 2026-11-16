"""Task12 ECS acceptance: real source checks plus isolated PostgreSQL review writes.

Never labels automated checks as a production human decision. Production POSTs
are unauthorized probes only; all successful test decisions live in a temporary
schema that is removed in finally.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4
import requests
from sqlalchemy import create_engine, text
from app.financial_reviews import migrate_reviews, review_state, submit_review, snapshot_fingerprint, ReviewConflict
from app.research_export import export_research
from app.verified_financials import company_comparisons, DEFAULT_ARTIFACT_ROOT
from scripts.task11_acceptance import EXPECTED, verify_result


def database_check(engine, artifact_root):
    assert engine.dialect.name=='postgresql', 'ECS persistence acceptance requires PostgreSQL'
    comparisons=[company_comparisons(engine,code,artifact_root=artifact_root) for code in EXPECTED]
    for comparison in comparisons:verify_result(comparison,comparison['company_code'])
    with engine.connect() as c:
        before=c.execute(text('SELECT count(*) FROM financial_reviews')).scalar_one()
        vectors=c.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
    schema='task12_accept_'+uuid4().hex
    with engine.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated=create_engine(engine.url,connect_args={'options':'-csearch_path='+schema})
    try:
        assert migrate_reviews(isolated)==['005_financial_reviews'] and migrate_reviews(isolated)==[]
        comparison=comparisons[0];row=comparison['items'][0]
        body=dict(metric=row['metric'],fingerprint=snapshot_fingerprint(row),expected_review_id=None,
            idempotency_key='accept-'+uuid4().hex,decision='confirmed',reason='AUTOMATED ISOLATED TEST: not a human review',reviewer='isolated_acceptance')
        first=submit_review(isolated,comparison,body)
        assert submit_review(isolated,comparison,body)==first
        def concurrent(i):
            try:return submit_review(isolated,comparison,dict(body,idempotency_key='race-'+uuid4().hex,expected_review_id=first['id'],decision='needs_evidence'))
            except ReviewConflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(concurrent,range(2)))
        assert sum(r is not None for r in results)==1
        current=next(r for r in results if r is not None)
        replay_engine=create_engine(engine.url,connect_args={'options':'-csearch_path='+schema})
        try:
            state=review_state(replay_engine,comparison)['items'][0]
            assert state['latest']['id']==current['id'] and len(state['history'])==2
        finally:replay_engine.dispose()
        changed=deepcopy(comparison);changed['items'][0]['current_value']='0.00'
        assert review_state(isolated,changed)['items'][0]['review_status']=='pending_human'
        report=json.loads(export_research(isolated,comparison,'json'))
        assert report['items'][0]['review']['review_status']=='needs_evidence'
        assert report['items'][0]['current_value']==row['current_value']
        assert row['difference'] in export_research(isolated,comparison,'markdown')
    finally:
        isolated.dispose()
        with engine.begin() as c:c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    with engine.connect() as c:
        assert before==c.execute(text('SELECT count(*) FROM financial_reviews')).scalar_one(), 'acceptance must not write production decisions'
        assert vectors==c.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
    return dict(real_metrics=6,postgresql_isolated_concurrency='passed',persistence_new_connection='passed',
                temporary_schema_removed=True,production_review_rows=before,vectors_unchanged=vectors)


def api_check(engine,base,host=None,artifact_root=DEFAULT_ARTIFACT_ROOT):
    session=requests.Session();session.trust_env=False
    if host:session.headers['Host']=host
    count=0
    for code in EXPECTED:
        route=base+'/api/v1/companies/'+code
        source=session.get(route+'/financial-comparison',timeout=20);source.raise_for_status();comparison=source.json();verify_result(comparison,code)
        direct=company_comparisons(engine,code,artifact_root=artifact_root);assert comparison==direct
        history=session.get(route+'/financial-reviews',timeout=20);history.raise_for_status();state=history.json()
        assert state==review_state(engine,direct)
        for item,row in zip(state['items'],comparison['items']):assert item['fingerprint']==snapshot_fingerprint(row)
        for format in ('json','markdown'):
            response=session.get(route+'/research-report',params={'format':format},timeout=20);response.raise_for_status()
            assert 'attachment' in response.headers['Content-Disposition']
            if format=='json':
                report=response.json()
                assert report['company_code']==code
                for row,item in zip(comparison['items'],report['items']):
                    assert all(item[k]==row[k] for k in ('current_value','previous_value','difference','evidence','source_sha256'))
            else:
                for row in comparison['items']:assert row['current_value'] in response.text and row['difference'] in response.text
        row=comparison['items'][0]
        unauthorized=session.post(route+'/financial-reviews',json=dict(metric=row['metric'],fingerprint=snapshot_fingerprint(row),
            expected_review_id=None,idempotency_key='unauthorized-'+uuid4().hex,decision='confirmed',reason='unauthorized probe',reviewer='not_written'),timeout=20)
        assert unauthorized.status_code==401, unauthorized.text
        assert session.get(route+'/financial-reviews',params={'statement_scope':'parent'},timeout=20).status_code==422
        count+=1
    legacy=session.post(base+'/api/v1/evidence/compare',json={'question':'立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？'},timeout=20)
    legacy.raise_for_status();assert legacy.json()['status']=='supported' and legacy.json()['claim_true'] is True
    health=session.get(base+'/health',timeout=15);health.raise_for_status();assert health.json()['database']['status']=='connected'
    return dict(companies=count,live_export_formats=['json','markdown'],unauthorized_writes_rejected=True,legacy_comparison='passed')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--database-only',action='store_true')
    parser.add_argument('--migrate',action='store_true');parser.add_argument('--api-url',default='http://127.0.0.1:8000');parser.add_argument('--host-header')
    parser.add_argument('--artifact-root',default=DEFAULT_ARTIFACT_ROOT);args=parser.parse_args()
    engine=create_engine(os.environ['DATABASE_URL'])
    try:
        applied=migrate_reviews(engine) if args.migrate else []
        result=dict(status='passed',migration=applied,database=database_check(engine,args.artifact_root))
        if not args.database_only:result['api']=api_check(engine,args.api_url,args.host_header,args.artifact_root)
        result['limitations']=['Automated writes only in temporary isolated schema; no production human decisions.',
            'Public HTTP/assets checks do not prove browser interaction or actual reviewer identity.']
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))
    finally:engine.dispose()
if __name__=='__main__':main()

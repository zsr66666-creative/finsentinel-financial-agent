from copy import deepcopy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, select
from fastapi.testclient import TestClient
from app.main import create_app
from app.financial_reviews import (migrate_reviews, review_state, submit_review, snapshot_fingerprint, ReviewConflict, ReviewUnavailable, review_table)
from app.research_export import export_research


def metric():
    return dict(metric='revenue',label='营业收入',status='supported',review_status='pending_human',company_code='002555',report_period='2024FY',statement_scope='consolidated',unit='CNY',current_period='2024-01-01/2024-12-31',previous_period='2023-01-01/2023-12-31',current_column='2024 年度',previous_column='2023 年度',period_kind='flow',current_value='9007199254740993.01',previous_value='1.00',difference='9007199254740992.01',change_percent='900719925474099201.00',direction='increase',document_id='a'*64,source_sha256='b'*64,source_url='https://static.cninfo.com.cn/finalpage/2025-01-01/123.PDF',source_validation='pdf_hash_and_statement_contract',evidence=[dict(role=role,page=1,text='原文',evidence_id=role,text_sha256='c'*64,page_text_sha256='d'*64) for role in ('row','statement','columns','unit')])


def comparison(row=None):
    return dict(company_code='002555',period='2024FY',statement_scope='consolidated',status='supported',items=[row or metric()],data_mode='source_verified_financial_contract')


@pytest.fixture
def engine(tmp_path):
    e=create_engine('sqlite:///'+str(tmp_path/'review.db'),connect_args={'check_same_thread':False})
    assert migrate_reviews(e)==['005_financial_reviews']
    assert migrate_reviews(e)==[]
    yield e
    e.dispose()


def request(row=None,**changes):
    return dict(metric='revenue',fingerprint=snapshot_fingerprint(row or metric()),expected_review_id=None,idempotency_key='test-key-00000001',decision='confirmed',reason='已核对原表、口径与单位',reviewer='研究员',**changes)


def test_fingerprint_binds_source_amount_scope_period_and_proofs():
    row=metric(); base=snapshot_fingerprint(row)
    for key,value in [('current_value','1.00'),('statement_scope','parent'),('source_sha256','e'*64),('current_period','2023')]:
        changed=deepcopy(row);changed[key]=value
        assert snapshot_fingerprint(changed)!=base
    changed=deepcopy(row);changed['evidence'][0]['page']=2
    assert snapshot_fingerprint(changed)!=base


def test_append_only_idempotency_conflict_staleness_and_persistence(engine):
    body=request(); first=submit_review(engine,comparison(),body)
    assert first['decision']=='confirmed' and first['identity_assurance']=='self_declared_operator'
    assert submit_review(engine,comparison(),body)==first
    with pytest.raises(ReviewConflict):submit_review(engine,comparison(),{**body,'reason':'不同说明'})
    with pytest.raises(ReviewConflict):submit_review(engine,comparison(),{**body,'idempotency_key':'test-key-00000002'})
    second=submit_review(engine,comparison(),{**body,'idempotency_key':'test-key-00000002','expected_review_id':first['id'],'decision':'rejected'})
    state=review_state(engine,comparison())['items'][0]
    assert state['review_status']=='rejected' and state['latest']['id']==second['id'] and len(state['history'])==2
    assert state['history'][1]['decision']=='confirmed'
    with engine.connect() as c:assert len(c.execute(select(review_table)).all())==2


def test_source_change_never_inherits_human_confirmation(engine):
    first=submit_review(engine,comparison(),request())
    changed=metric();changed['current_value']='2.00'
    state=review_state(engine,comparison(changed))['items'][0]
    assert state['review_status']=='pending_human' and state['latest'] is None and state['history'][0]['id']==first['id']
    with pytest.raises(ReviewConflict):submit_review(engine,comparison(changed),request())
    unavailable={**comparison(),'items':[dict(metric='revenue',label='营业收入',status='needs_review',evidence=[],reason='source_pdf_unavailable')]}
    assert review_state(engine,unavailable)['items'][0]['review_status']=='source_unavailable'
    with pytest.raises(ReviewUnavailable):submit_review(engine,unavailable,request())


def test_concurrent_stale_writes_allow_one_winner(engine):
    def write(i):
        try:return submit_review(engine,comparison(),{**request(),'idempotency_key':f'concurrent-key-{i:04}'})['id']
        except ReviewConflict:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,range(2)))
    assert len([r for r in results if r])==1


def test_export_exact_amounts_pending_and_rejected_notes_escaped(engine):
    pending=export_research(engine,comparison(),'json')
    assert json.loads(pending)['items'][0]['review']['review_status']=='pending_human'
    submit_review(engine,comparison(),{**request(),'decision':'rejected','reason':'<script>alert(1)</script>\n# 假标题 [跳转](https://bad.test)'})
    exported=json.loads(export_research(engine,comparison(),'json'))
    assert exported['items'][0]['current_value']=='9007199254740993.01'
    assert exported['items'][0]['review']['review_status']=='rejected'
    md=export_research(engine,comparison(),'markdown')
    assert '<script>' not in md and '\n# 假标题' not in md and '9007199254740993.01' in md and 'rejected' in md


def test_api_write_disabled_unauthorized_and_server_owns_snapshot(monkeypatch):
    import app.financial_review_routes as routes
    client=TestClient(create_app(database_url='sqlite:///:memory:'))
    migrate_reviews(client.app.state.store.engine)
    monkeypatch.setattr(routes,'company_comparisons',lambda *a,**k:comparison())
    url='/api/v1/companies/002555/financial-reviews'
    monkeypatch.delenv('FINANCIAL_REVIEW_TOKEN',raising=False)
    assert client.post(url,json=request()).status_code==503
    monkeypatch.setenv('FINANCIAL_REVIEW_TOKEN','x'*40)
    assert client.post(url,json=request()).status_code==401
    assert client.post(url,headers={'Authorization':'Bearer '+'x'*40},json={**request(),'current_value':'9.00'}).status_code==422
    response=client.post(url,headers={'Authorization':'Bearer '+'x'*40},json=request())
    assert response.status_code==201,response.text
    assert client.get(url).json()['items'][0]['latest']['id']==response.json()['id']
    report=client.get('/api/v1/companies/002555/research-report?format=markdown')
    assert report.status_code==200 and 'attachment' in report.headers['content-disposition']
    assert 'x'*40 not in report.text

def test_review_browser_preflight_allows_operator_authorization(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS","http://localhost:3000")
    client=TestClient(create_app(database_url='sqlite:///:memory:'))
    response=client.options('/api/v1/companies/002555/financial-reviews',headers={
        'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST',
        'Access-Control-Request-Headers':'authorization,content-type'})
    assert response.status_code==200,response.text
    assert 'authorization' in response.headers['access-control-allow-headers'].lower()

def test_unavailable_export_never_reuses_historical_confirmed_amount(engine):
    submit_review(engine,comparison(),request())
    unavailable={**comparison(),'status':'needs_review','items':[dict(metric='revenue',label='营业收入',status='needs_review',reason='source_pdf_unavailable',evidence=[])]}
    body=json.loads(export_research(engine,unavailable,'json'))
    assert body['items'][0]['review']['review_status']=='source_unavailable'
    assert body['items'][0]['review']['latest'] is None
    assert '9007199254740993.01' not in json.dumps(body)
    assert '9007199254740993.01' not in export_research(engine,unavailable,'markdown')


def test_effective_matching_review_survives_bounded_other_source_history(engine):
    first=submit_review(engine,comparison(),request())
    for index in range(31):
        changed=deepcopy(metric());changed['current_value']=str(index)+'.00'
        submit_review(engine,comparison(changed),{**request(changed),'idempotency_key':f'history-change-{index:04}'})
    state=review_state(engine,comparison())['items'][0]
    assert state['review_status']=='confirmed' and state['latest']['id']==first['id']
    assert len(state['history'])==30 and any(row['id']==first['id'] for row in state['history'])


def test_review_persists_after_engine_restart(engine):
    from sqlalchemy import create_engine
    original=submit_review(engine,comparison(),request())
    restarted=create_engine(engine.url)
    try:assert review_state(restarted,comparison())['items'][0]['latest']==original
    finally:restarted.dispose()

from fastapi.testclient import TestClient
from app.main import create_app
from app.auth.service import Accounts, migrate_accounts
from app.saved_reports import SavedReports, migrate_saved_reports, check_saved_reports


def test_saved_report_auth_and_snapshot(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('AUTH_ORIGIN','http://testserver');monkeypatch.setenv('AUTH_COOKIE_SECURE','false')
    app=create_app('sqlite:///'+str(tmp_path/'reports.db'))
    engine=app.state.store.engine;migrate_accounts(engine)
    from app.financial_reviews import migrate_reviews
    migrate_reviews(engine)
    assert migrate_saved_reports(engine)==['008_saved_research_reports']
    assert migrate_saved_reports(engine)==[];assert check_saved_reports(engine)
    accounts=Accounts(engine)
    def login(name):
        user=accounts.create_user(name,'temporary password','viewer',name)
        accounts.password(user['id'],'temporary password','permanent password')
        client=TestClient(app)
        data=client.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':name,'password':'permanent password'}).json()
        return client,{'Origin':'http://testserver','X-CSRF-Token':data['csrf_token']},user['id']
    alice,headers,aid=login('alice');bob,bheaders,bid=login('bobby')
    endpoint='/api/v1/me/research/reports';body={'company_code':'002555','title':'Saved report','question':'Private note'}
    assert alice.post(endpoint,json=body).status_code==403
    for extra in ({'snapshot':{}},{'owner_id':bid},{'current_value':'123'}):
        assert alice.post(endpoint,headers=headers,json=body|extra).status_code==422
    response=alice.post(endpoint,headers=headers,json=body);assert response.status_code==201,response.text
    saved=response.json();assert 'snapshot' not in saved and len(saved['snapshot_sha256'])==64
    detail=alice.get(endpoint+'/'+saved['id']).json();assert detail['snapshot']['company_code']=='002555'
    assert detail['snapshot']['saved_title']=='Saved report' and detail['snapshot']['saved_question']=='Private note'
    assert detail['snapshot']['items'] and 'owner_id' not in detail
    assert bob.get(endpoint).json()['total']==0
    denied=bob.get(endpoint+'/'+saved['id'])
    assert denied.status_code==404 and denied.headers['cache-control']=='no-store'
    for suffix in ('','/export'):
        assert bob.get(endpoint+'/'+saved['id']+suffix).status_code==404
    assert bob.delete(endpoint+'/'+saved['id'],headers=bheaders).status_code==404
    before=alice.get(endpoint+'/'+saved['id']+'/export').content
    monkeypatch.setattr('app.saved_reports.company_comparisons',lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('private path')))
    assert alice.get(endpoint+'/'+saved['id']+'/export').content==before
    markdown=alice.get(endpoint+'/'+saved['id']+'/export?format=markdown')
    assert markdown.status_code==200 and 'Private note' in markdown.text and 'Saved report' in markdown.text
    assert alice.post(endpoint,headers=headers,json=body).json()['detail']=='saved_report_source_unavailable'
    assert alice.get(endpoint+'?limit=101').status_code==422
    assert alice.get(endpoint).headers['cache-control']=='no-store'
    assert SavedReports(create_app('sqlite:///'+str(tmp_path/'reports.db')).state.store).listing(aid)['total']==1
    assert alice.delete(endpoint+'/'+saved['id'],headers=headers).status_code==204
    assert alice.get(endpoint+'/'+saved['id']).status_code==404


def test_auth_off_private_and_no_implicit_migration(tmp_path,monkeypatch):
    from sqlalchemy import inspect
    monkeypatch.setenv('AUTH_ENABLED','false')
    app=create_app('sqlite:///'+str(tmp_path/'off.db'));client=TestClient(app)
    assert 'saved_research_reports' not in inspect(app.state.store.engine).get_table_names()
    assert client.get('/api/v1/me/research/reports').status_code==401

def test_service_bounds_and_schema_checks(tmp_path,monkeypatch):
    import json
    import pytest
    from uuid import uuid4
    from sqlalchemy import text
    from app.saved_reports import reports
    from app.store import Store
    store=Store('sqlite:///'+str(tmp_path/'bounds.db'));migrate_accounts(store.engine);migrate_saved_reports(store.engine)
    owner=Accounts(store.engine).create_user('bounds','password for tests','viewer','Bounds')['id']
    service=SavedReports(store)
    report={'items':[],'company_code':'002555'}
    monkeypatch.setattr('app.saved_reports.company_comparisons',lambda *a,**kw: {})
    monkeypatch.setattr('app.saved_reports.export_research',lambda *a,**kw:json.dumps(report))
    row=service.create(owner,company_code='002555',title='Bounded')
    with store.engine.begin() as c:
        template=dict(c.execute(reports.select()).mappings().first())
        c.execute(reports.insert(),[template|{'id':str(uuid4())} for _ in range(199)])
    with pytest.raises(ValueError,match='saved_reports_limit'):service.create(owner,company_code='002555',title='Overflow')
    assert service.listing(owner,offset=199,limit=1)['total']==200
    service.remove(owner,row['id'])
    report['large']='x'*(2*1024*1024)
    with pytest.raises(ValueError,match='snapshot_too_large'):service.create(owner,company_code='002555',title='Oversized')
    assert service.listing(owner)['total']==199
    with store.engine.begin() as c:c.execute(text('DROP INDEX ix_saved_research_reports_owner_id'))
    with pytest.raises(ValueError,match='indexes_missing'):check_saved_reports(store.engine)
    with pytest.raises(ValueError,match='indexes_missing'):migrate_saved_reports(store.engine)


def test_http_text_validation(tmp_path,monkeypatch):
    from app.saved_report_routes import CreateReport
    from pydantic import ValidationError
    import pytest
    for payload in ({'title':'   '},{'title':'x'*121},{'title':'bad\x00'},{'title':'OK','question':'bad\x00'},{'title':'OK','question':'x'*1001}):
        with pytest.raises(ValidationError):CreateReport(company_code='002555',**payload)


def test_renderer_keeps_immediate_exports_and_escapes_saved_text():
    from app.research_export import render_research
    report=dict(company_name='Company',company_code='002555',period='2024FY',statement_scope='consolidated',exported_at='frozen',limitations=[],items=[])
    original=render_research(report,'markdown')
    assert '保存时快照' not in original
    saved=render_research(report|{'saved_snapshot':True,'saved_title':'<script>*title*','saved_question':'[x](https://evil)'},'markdown')
    assert '<script>' not in saved and '&lt;script&gt;' in saved and '\\[x\\]' in saved
    assert render_research(report,'markdown')==original


def test_unavailable_store_can_be_wired():
    from fastapi import FastAPI
    from app.saved_report_routes import wire_saved_reports
    app=FastAPI();app.state.auth_enabled=False
    wire_saved_reports(app,object())
    assert TestClient(app).get('/api/v1/me/research/reports').status_code==401


def test_supported_report_freezes_precise_amounts_evidence_and_review(tmp_path,monkeypatch):
    import json
    import hashlib
    from app.store import Store
    from app.financial_reviews import migrate_reviews,submit_review
    from test_task12_reviews import comparison,request
    store=Store('sqlite:///'+str(tmp_path/'precise.db'))
    migrate_accounts(store.engine);migrate_reviews(store.engine);migrate_saved_reports(store.engine)
    owner=Accounts(store.engine).create_user('precise','password for tests','viewer','Precise')['id']
    source=comparison()
    monkeypatch.setattr('app.saved_reports.company_comparisons',lambda *a,**k:source)
    service=SavedReports(store)
    saved=service.create(owner,company_code='002555',title='Precision report',question='Check revenue')
    original=service.export(owner,saved['id'])
    assert hashlib.sha256(original.encode()).hexdigest()==saved['snapshot_sha256']
    item=json.loads(original)['items'][0]
    assert item['current_value']=='9007199254740993.01'
    assert item['source_sha256']=='b'*64 and item['evidence'][0]['page']==1
    assert item['review']['review_status']=='pending_human'
    submit_review(store.engine,source,request())
    assert service.export(owner,saved['id'])==original
    assert '9007199254740993.01' in service.export(owner,saved['id'],'markdown')
    second=service.create(owner,company_code='002555',title='New review snapshot')
    assert service.detail(owner,second['id'])['snapshot']['items'][0]['review']['review_status']=='confirmed'

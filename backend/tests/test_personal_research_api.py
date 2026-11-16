from fastapi.testclient import TestClient
from app.main import create_app
from app.auth.service import Accounts,migrate_accounts
from app.personal_research import migrate_research_library

def test_auth_off_still_private(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','false')
    c=TestClient(create_app('sqlite:///'+str(tmp_path/'off.db')))
    assert c.get('/api/v1/me/research/favorites').status_code==401
    assert c.post('/api/v1/me/research/history',json={'kind':'search','query':'test'}).status_code==401

def test_api_isolation_csrf_validation_and_persistence(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('AUTH_ORIGIN','http://testserver');monkeypatch.setenv('AUTH_COOKIE_SECURE','false')
    url='sqlite:///'+str(tmp_path/'api.db');app=create_app(url)
    migrate_accounts(app.state.store.engine);migrate_research_library(app.state.store.engine)
    app.state.store.put('companies',{'id':'000001','name':'Test'})
    service=Accounts(app.state.store.engine)
    def login(name):
        user=service.create_user(name,'temporary password','viewer',name)
        service.password(user['id'],'temporary password','permanent password')
        client=TestClient(app)
        data=client.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':name,'password':'permanent password'}).json()
        return client,{'Origin':'http://testserver','X-CSRF-Token':data['csrf_token']}
    alice,headers=login('alice');bob,bheaders=login('bobby')
    endpoint='/api/v1/me/research/favorites'
    body={'kind':'company','company_code':'000001'}
    assert alice.post(endpoint,json=body).status_code==403
    assert alice.post(endpoint,headers=headers,json=body|{'user_id':'fake'}).status_code==422
    saved=alice.post(endpoint,headers=headers,json=body).json()
    assert saved['snapshot']['company_name']=='Test'
    assert alice.post(endpoint,headers=headers,json=body).json()['id']==saved['id']
    assert bob.get(endpoint).json()['total']==0
    assert bob.delete(endpoint+'/'+saved['id'],headers=bheaders).status_code==404
    assert bob.post(endpoint+'/'+saved['id']+'/note',headers=bheaders,json={'note':'stolen'}).status_code==404
    assert alice.post(endpoint+'/'+saved['id']+'/note',headers=headers,json={'note':'x'*1001}).status_code==422
    assert alice.get(endpoint+'?limit=101').status_code==422
    assert alice.get(endpoint).headers['cache-control']=='no-store'
    app2=create_app(url);assert 'personal_research_favorites' in __import__('sqlalchemy').inspect(app2.state.store.engine).get_table_names()
    from app.personal_research import ResearchLibrary
    assert ResearchLibrary(app2.state.store).listing(service.list_users()[0]['id'])['total']==1

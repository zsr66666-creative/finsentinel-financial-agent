import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth.service import Accounts,migrate_accounts

@pytest.fixture
def account_client(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('AUTH_ORIGIN','http://testserver');monkeypatch.setenv('AUTH_COOKIE_SECURE','false')
    app=create_app('sqlite:///'+str(tmp_path/'api.db'))
    migrate_accounts(app.state.store.engine)
    service=Accounts(app.state.store.engine)
    service.create_user('admin','temporary password','admin','Admin')
    return TestClient(app),service

def test_auth_boundaries(account_client):
    c,service=account_client
    assert c.get('/api/v1/companies').status_code==401
    assert c.post('/api/v1/auth/login',json={'username':'admin','password':'temporary password'}).status_code==403
    login=c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'temporary password'})
    assert login.status_code==200
    assert 'HttpOnly' in login.headers['set-cookie']
    assert c.get('/api/v1/companies').status_code==403
    csrf=login.json()['csrf_token'];headers={'Origin':'http://testserver','X-CSRF-Token':csrf}
    assert c.post('/api/v1/auth/password',headers=headers,json={'current_password':'temporary password','new_password':'permanent password'}).status_code==204
    assert c.get('/api/v1/auth/session').status_code==401
    login=c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'permanent password'})
    assert login.status_code==200
    assert c.get('/api/v1/companies').status_code==200
    assert c.post('/api/v1/auth/profile',headers={'Origin':'http://testserver'},json={'nickname':'New','avatar':None}).status_code==403
    service.create_user('viewer','temporary password','viewer','Viewer')
    c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'viewer','password':'temporary password'})
    session=c.get('/api/v1/auth/session').json();h={'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}
    c.post('/api/v1/auth/password',headers=h,json={'current_password':'temporary password','new_password':'permanent password'})
    c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'viewer','password':'permanent password'})
    assert c.get('/api/v1/auth/users').status_code==403
    assert c.get('/api/v1/observability').status_code==403

def test_profile_isolation_and_admin_revoke(account_client):
    c,s=account_client
    login=c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'temporary password'}).json()
    h={'Origin':'http://testserver','X-CSRF-Token':login['csrf_token']}
    c.post('/api/v1/auth/password',headers=h,json={'current_password':'temporary password','new_password':'permanent password'})
    login=c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'permanent password'}).json();h['X-CSRF-Token']=login['csrf_token']
    other=s.create_user('other','temporary password','viewer','Other')
    response=c.post('/api/v1/auth/profile',headers=h,json={'nickname':'Changed','avatar':None})
    assert response.status_code==200 and response.json()['nickname']=='Changed'
    assert next(u for u in s.list_users() if u['id']==other['id'])['nickname']=='Other'
    assert response.headers['cache-control']=='no-store'
    assert c.post('/api/v1/auth/users/'+login['user']['id'],headers=h,json={'enabled':False}).json()['detail']=='last_admin'
    assert c.post('/api/v1/auth/logout',headers=h,json={}).status_code==204
    assert c.get('/api/v1/auth/session').status_code==401

def test_login_bounds_and_proxy_headers(account_client):
    c,s=account_client
    for _ in range(10):
        assert c.post('/api/v1/auth/login',headers={'Origin':'http://testserver','X-Forwarded-For':'arbitrary'},json={'username':'unknown','password':'incorrect password'}).status_code==401
    assert c.post('/api/v1/auth/login',headers={'Origin':'http://testserver','X-Forwarded-For':'different'},json={'username':'different','password':'incorrect password'}).status_code==429
    assert c.options('/api/v1/companies').status_code==401
    assert c.get('/health').json()=={'status':'ok'}

def test_unmigrated_auth_database_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('AUTH_ORIGIN','http://testserver');monkeypatch.setenv('AUTH_COOKIE_SECURE','false')
    c=TestClient(create_app('sqlite:///'+str(tmp_path/'missing.db')))
    # A syntactically valid opaque cookie forces a database-backed lookup.
    c.cookies.set('finsentinel_session','untrusted-cookie')
    response=c.get('/api/v1/companies')
    assert response.status_code==503 and response.json()['detail']=='auth_store_unavailable'
    assert c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'temporary password'}).status_code==503

def test_secure_cookie_and_machine_namespace(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('AUTH_ORIGIN','https://testserver');monkeypatch.setenv('AUTH_COOKIE_SECURE','true');monkeypatch.setenv('INGESTION_ADMIN_TOKEN','x'*40)
    app=create_app('sqlite:///'+str(tmp_path/'secure.db'));migrate_accounts(app.state.store.engine)
    app.state.accounts.create_user('admin','temporary password','admin','Admin')
    c=TestClient(app,base_url='https://testserver')
    login=c.post('/api/v1/auth/login',headers={'Origin':'https://testserver'},json={'username':'admin','password':'temporary password'})
    cookie=login.headers['set-cookie']
    assert '__Host-finsentinel_session=' in cookie and 'Secure' in cookie and 'HttpOnly' in cookie and 'Domain=' not in cookie
    c.cookies.clear();headers={'Authorization':'Bearer '+'x'*40}
    assert c.get('/api/v1/auth/users',headers=headers).status_code==401
    assert c.post('/api/v1/companies/002555/financial-reviews',headers=headers,json={}).status_code==403
    assert c.get('/api/v1/admin/source-ingestion/tasks/00000000-0000-0000-0000-000000000000',headers=headers).status_code==503

def test_cors_preflight_cannot_bypass_auth(account_client):
    c,_=account_client
    response=c.options('/api/v1/companies',headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'GET'})
    assert response.status_code==401

def test_health_reports_database_outage(account_client,monkeypatch):
    c,service=account_client
    def unavailable():raise RuntimeError('database offline')
    monkeypatch.setattr(service.engine,'connect',unavailable)
    assert c.get('/health').status_code==503

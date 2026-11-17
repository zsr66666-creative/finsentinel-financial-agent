import json
from datetime import datetime, timezone, timedelta
from app.operations import read_status
from scripts.operations_runner import age_status, disk_status, certificate_status, merge_history

def test_thresholds():
    assert age_status(31*3600, 'backup') == 'warning'
    assert age_status(49*3600, 'backup') == 'critical'
    assert age_status(9*86400, 'restore') == 'warning'
    assert certificate_status(23*3600) == 'critical'
    assert certificate_status(47*3600) == 'warning'
    assert disk_status(3*1024**3, 100*1024**3) == 'critical'

def test_status_rejects_corrupt_and_stale(tmp_path):
    path=tmp_path/'status.json'
    path.write_text('{secret')
    assert read_status(path)['status']=='unknown'
    path.write_text(json.dumps({'schema_version':1,'checked_at':(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat(),'status':'ok','checks':[],'history':[]}))
    assert read_status(path)['status']=='critical'

def test_sanitization(tmp_path):
    path=tmp_path/'status.json'
    path.write_text(json.dumps({'schema_version':1,'checked_at':datetime.now(timezone.utc).isoformat(),'status':'ok','checks':[{'id':'database','label':'postgres://secret','status':'ok','reason':'password=secret','checked_at':datetime.now(timezone.utc).isoformat(),'duration_ms':1}],'history':[]}))
    result=read_status(path)
    assert result['status']=='unknown'
    assert 'secret' not in json.dumps(result)

def test_history_dedup_and_bound():
    check={'id':'database','status':'critical','reason':'check_failed','checked_at':datetime.now(timezone.utc).isoformat()}
    first=merge_history([], [check]); assert len(first)==1
    assert merge_history(first,[check])==first
    check=dict(check,status='ok',reason='check_passed')
    assert len(merge_history(first,[check]))==2
    assert len(merge_history(first*250,[check]))==200

def test_auth_disabled_rejected(monkeypatch):
    from app.main import create_app
    from fastapi.testclient import TestClient
    monkeypatch.setenv('AUTH_ENABLED','false')
    with TestClient(create_app('sqlite:///:memory:')) as client:
        response=client.get('/api/v1/admin/operations')
        assert response.status_code==401


def test_route_admin_and_viewer(monkeypatch,tmp_path):
    from fastapi import FastAPI,Request
    from fastapi.testclient import TestClient
    from app.operations import build_router
    app=FastAPI(); app.state.auth_enabled=True; app.include_router(build_router())
    @app.middleware('http')
    async def session(request:Request,call_next):
        request.state.session={'user':{'role':request.headers.get('x-test-role','viewer')}}
        return await call_next(request)
    monkeypatch.setenv('OPERATIONS_STATUS_FILE',str(tmp_path/'missing'))
    with TestClient(app) as client:
        assert client.get('/api/v1/admin/operations').status_code==403
        response=client.get('/api/v1/admin/operations',headers={'x-test-role':'admin'})
        assert response.status_code==200
        assert response.json()['status']=='unknown'
        assert response.headers['cache-control']=='no-store'
        assert response.headers['x-content-type-options']=='nosniff'


def test_partial_and_check_timestamp_fail_closed(tmp_path):
    from app.operations import LABELS
    path=tmp_path/'status.json'; now=datetime.now(timezone.utc).isoformat()
    data=dict(schema_version=1,checked_at=now,status='ok',checks=[dict(id=k,label=k,status='ok',reason='check_passed',checked_at=now,duration_ms=0) for k in LABELS],history=[])
    path.write_text(json.dumps(data)); assert read_status(path)['status']=='ok'
    data['checks'][0]['checked_at']=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()
    path.write_text(json.dumps(data)); assert read_status(path)['status']=='critical'
    data['checks']=data['checks'][1:]
    path.write_text(json.dumps(data)); assert read_status(path)['status']=='unknown'


def test_safe_metadata_whitelist(tmp_path):
    from app.operations import LABELS
    now=datetime.now(timezone.utc).isoformat()
    data=dict(schema_version=1,checked_at=now,status='ok',checks=[dict(id=k,label=k,status='ok',reason='check_passed',checked_at=now,duration_ms=0) for k in LABELS],history=[])
    checks={row['id']:row for row in data['checks']}
    checks['backup']['last_success_at']=now
    checks['certificate']['expires_at']=now
    checks['disk'].update(free_bytes=123,total_bytes=456,secret='private')
    path=tmp_path/'status.json';path.write_text(json.dumps(data))
    result={row['id']:row for row in read_status(path)['checks']}
    assert result['backup']['last_success_at']==now
    assert result['certificate']['expires_at']==now
    assert result['disk']['free_bytes']==123
    assert 'secret' not in result['disk']
    checks['disk']['free_bytes']=True
    path.write_text(json.dumps(data));assert read_status(path)['status']=='unknown'


def test_status_contract_has_local_backup_and_restore_without_offsite_transfer_state(tmp_path):
    from app.operations import LABELS, aggregate
    now=datetime.now(timezone.utc).isoformat()
    data=dict(schema_version=1,checked_at=now,status='ok',checks=[dict(id=k,label=k,status='ok',reason='check_passed',checked_at=now,duration_ms=0) for k in LABELS],history=[])
    rows={row['id']:row for row in data['checks']}
    path=tmp_path/'status.json';path.write_text(json.dumps(data))

    parsed=read_status(path)
    assert 'offsite_backup' not in LABELS
    assert aggregate(parsed['checks'])=='ok'

    data['checks'].pop()
    path.write_text(json.dumps(data))
    assert read_status(path)['status']=='unknown'

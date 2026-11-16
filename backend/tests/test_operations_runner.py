import json
from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from scripts import operations_runner as runner

def test_private_failure_overrides_last_success(tmp_path):
    for name,value in [('backup.json',{'status':'critical'}),('backup_success.json',{'finished_at':datetime.now(timezone.utc).isoformat()})]:
        (tmp_path/name).write_text(json.dumps(value))
    assert runner.result_age(tmp_path,'backup')==('critical','task_failed')

def test_atomic_writer_permissions_and_symlink(tmp_path):
    target=tmp_path/'state.json'; runner.atomic_json(target,{'ok':True},0o640)
    assert json.loads(target.read_text())=={'ok':True}
    link=tmp_path/'link'
    try: link.symlink_to(target)
    except OSError: pytest.skip('symlink privilege unavailable')
    with pytest.raises(ValueError): runner.atomic_json(link,{'ok':False})
    assert json.loads(target.read_text())=={'ok':True}

def test_checks_do_not_treat_https_tuple_as_status(monkeypatch,tmp_path):
    monkeypatch.setattr(runner,'command',lambda args:'Result=success\nExecMainStatus=0\nExecMainStartTimestampMonotonic=1' if 'show' in args else 'enabled' if 'is-enabled' in args else 'active')
    monkeypatch.setattr(runner,'database_probe',lambda url:None)
    monkeypatch.setattr(runner,'local_https',lambda ip,path:(b'HTTP/1.1 200 OK\r\n\r\n<script src="/_next/static/a.js"></script>',{'notAfter':'Dec 31 23:59:59 2099 GMT'}))
    monkeypatch.setattr(runner.shutil,'disk_usage',lambda path:SimpleNamespace(free=50*1024**3,total=100*1024**3))
    rows=runner.run_checks(tmp_path,'secret','127.0.0.1')
    assert next(x for x in rows if x['id']=='https_health')['status']=='ok'
    assert next(x for x in rows if x['id']=='https_static')['status']=='ok'
    assert len(rows)==18
    assert next(x for x in rows if x['id']=='certificate')['expires_at'].startswith('2099-12-31')
    assert next(x for x in rows if x['id']=='disk')['free_bytes']==50*1024**3
    assert 'secret' not in json.dumps(rows)

def test_database_probe_credentials_not_argv(monkeypatch):
    captured={}
    def fake(args,**kwargs): captured.update(args=args,kwargs=kwargs)
    monkeypatch.setattr(runner.subprocess,'run',fake)
    runner.database_probe('postgresql://secret')
    assert 'secret' not in ' '.join(captured['args'])
    assert captured['kwargs']['input']=='postgresql://secret'
    assert captured['kwargs']['timeout']==6


def test_recovery_metadata_preserves_old_success_during_failure(monkeypatch,tmp_path):
    private=tmp_path/'private';private.mkdir()
    when=datetime.now(timezone.utc).isoformat()
    (private/'backup.json').write_text(json.dumps({'status':'critical'}))
    (private/'backup_success.json').write_text(json.dumps({'finished_at':when}))
    monkeypatch.setattr(runner,'command',lambda args: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(runner,'database_probe',lambda url: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(runner,'local_https',lambda *args: (_ for _ in ()).throw(RuntimeError()))
    rows=runner.run_checks(tmp_path,'','127.0.0.1')
    backup=next(row for row in rows if row['id']=='backup')
    assert backup['status']=='critical'
    assert backup['last_success_at']==when

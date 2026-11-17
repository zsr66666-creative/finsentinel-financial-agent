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
    monkeypatch.delenv('OFFSITE_ENABLED',raising=False)
    monkeypatch.setattr(runner,'command',lambda args:'Result=success\nExecMainStatus=0\nExecMainStartTimestampMonotonic=1' if 'show' in args else 'enabled' if 'is-enabled' in args else 'active')
    monkeypatch.setattr(runner,'database_probe',lambda url:None)
    monkeypatch.setattr(runner,'local_https',lambda ip,path:(b'HTTP/1.1 200 OK\r\n\r\n<script src="/_next/static/a.js"></script>',{'notAfter':'Dec 31 23:59:59 2099 GMT'}))
    monkeypatch.setattr(runner.shutil,'disk_usage',lambda path:SimpleNamespace(free=50*1024**3,total=100*1024**3))
    rows=runner.run_checks(tmp_path,'secret','127.0.0.1')
    assert next(x for x in rows if x['id']=='https_health')['status']=='ok'
    assert next(x for x in rows if x['id']=='https_static')['status']=='ok'
    assert len(rows)==19
    offsite=next(x for x in rows if x['id']=='offsite_backup')
    assert (offsite['status'],offsite['reason'])==('unknown','not_configured')
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


def test_missing_original_failure_emits_safe_diagnostic_without_crashing(capsys):
    runner.print_diagnostic('backup',dict(status='critical',reason='missing_original',missing_sha256='a'*64))
    output=capsys.readouterr().out
    assert 'missing_sha256='+'a'*64 in output
    runner.print_diagnostic('restore',dict(status='critical',reason='restore_failed',error='/private/secret'))
    assert capsys.readouterr().out=='restore: restore_failed\n'


def test_offsite_failure_preserves_local_and_previous_offsite_success(tmp_path,monkeypatch):
    private=tmp_path/'private';private.mkdir()
    finished=datetime.now(timezone.utc).isoformat()
    local_success={'status':'ok','finished_at':finished}
    offsite_success={'status':'ok','reason':'offsite_verified','finished_at':finished,
                     'backup_id':'backup-20261117T120000000000Z-'+'a'*32,'ciphertext_sha256':'a'*64}
    (private/'backup_success.json').write_text(json.dumps(local_success))
    (private/'offsite_backup_success.json').write_text(json.dumps(offsite_success))
    monkeypatch.setattr(runner,'stamp',lambda:finished)

    result=runner.run_offsite_task(tmp_path,private,backup_ok=True,enabled=True,
                                   sync=lambda *args,**kwargs:{'status':'critical','reason':'upload_failed','finished_at':finished})

    assert result['status']=='critical'
    assert json.loads((private/'backup_success.json').read_text())==local_success
    assert json.loads((private/'offsite_backup_success.json').read_text())==offsite_success
    assert json.loads((private/'offsite_backup.json').read_text())=={'status':'critical','reason':'upload_failed','finished_at':finished}


def test_offsite_disabled_is_explicit_without_failure(tmp_path):
    private=tmp_path/'private';private.mkdir()
    assert runner.offsite_recovery(private,enabled=False)=={'status':'unknown','reason':'not_configured'}


def test_offsite_status_exposes_only_fixed_failure_code_and_last_success(tmp_path):
    private=tmp_path/'private';private.mkdir()
    finished=datetime.now(timezone.utc).isoformat()
    (private/'offsite_backup.json').write_text(json.dumps({'status':'critical','reason':'upload_failed','finished_at':finished,'error':'token=secret'}))
    (private/'offsite_backup_success.json').write_text(json.dumps({'status':'ok','finished_at':finished,'ciphertext_sha256':'secret'}))

    result=runner.offsite_recovery(private,enabled=True)

    assert result=={'status':'critical','reason':'upload_failed','last_success_at':finished}

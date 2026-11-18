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


def test_missing_original_failure_emits_safe_diagnostic_without_crashing(capsys):
    runner.print_diagnostic('backup',dict(status='critical',reason='missing_original',missing_sha256='a'*64))
    output=capsys.readouterr().out
    assert 'missing_sha256='+'a'*64 in output
    runner.print_diagnostic('restore',dict(status='critical',reason='restore_failed',error='/private/secret'))
    assert capsys.readouterr().out=='restore: restore_failed\n'


def test_export_journal_result_never_records_windows_pull_or_ciphertext_details(tmp_path,capsys):
    private=tmp_path/'private';private.mkdir()
    local_success={'status':'ok','finished_at':datetime.now(timezone.utc).isoformat()}
    (private/'backup_success.json').write_text(json.dumps(local_success))
    secret_digest='a'*64
    backup_id='backup-20261117T120000000000Z-'+'b'*32

    result=runner.run_encrypted_export(
        tmp_path,private,backup_ok=True,recipient='age1recipient',export_root=tmp_path/'exports',
        exporter=lambda *args,**kwargs:{'status':'ok','reason':'export_verified','backup_id':backup_id,
                                      'ciphertext_sha256':secret_digest,'ciphertext_size':123},
    )
    output=capsys.readouterr().out

    assert result=={'status':'ok','reason':'export_verified'}
    assert output=='encrypted_export: ok export_verified\n'
    assert secret_digest not in output
    assert json.loads((private/'backup_success.json').read_text())==local_success
    assert not list(private.glob('offsite_backup*'))


def test_export_failure_does_not_modify_local_success_and_logs_only_fixed_code(tmp_path,capsys):
    private=tmp_path/'private';private.mkdir()
    local_success={'status':'ok','finished_at':datetime.now(timezone.utc).isoformat()}
    (private/'backup_success.json').write_text(json.dumps(local_success))

    result=runner.run_encrypted_export(
        tmp_path,private,backup_ok=True,recipient='age1recipient',export_root=tmp_path/'exports',
        exporter=lambda *args,**kwargs:{'status':'critical','reason':'encryption_failed','ciphertext_sha256':'secret'},
    )

    assert result=={'status':'critical','reason':'encryption_failed'}
    assert capsys.readouterr().out=='encrypted_export: critical encryption_failed\n'
    assert json.loads((private/'backup_success.json').read_text())==local_success
    assert not list(private.glob('offsite_backup*'))

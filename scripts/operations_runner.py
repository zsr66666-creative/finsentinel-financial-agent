"""Privileged scheduled maintenance. The API never imports this runner."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import time
import uuid
from datetime import datetime, timezone

# Deployment runs from repository root, independently of uvicorn's --app-dir.
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.operations import LABELS, aggregate, parsed_time, stamp


def age_status(seconds, kind):
    if kind=='backup': return 'critical' if seconds>48*3600 else 'warning' if seconds>30*3600 else 'ok'
    return 'warning' if seconds>8*86400 else 'ok'
def certificate_status(seconds): return 'critical' if seconds<24*3600 else 'warning' if seconds<48*3600 else 'ok'
def disk_status(free,total):
    return 'critical' if free<2*1024**3 or free/total<.1 else 'warning' if free<4*1024**3 or free/total<.2 else 'ok'
def merge_history(history, checks):
    rows=list(history); latest={row['check_id']:(row['status'],row['reason']) for row in rows}
    for row in checks:
        key=row['id']; transition=(row['status'],row['reason'])
        if latest.get(key)!=transition:
            rows.append(dict(at=row['checked_at'],check_id=key,status=row['status'],reason=row['reason'])); latest[key]=transition
    return rows[-200:]

def safe_path(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)): raise ValueError('unsafe_path')
    return path

def atomic_json(path, data, mode=0o600):
    path=safe_path(path); safe_path(path.parent)
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
    fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),mode)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            json.dump(data,output,ensure_ascii=True,allow_nan=False); output.flush(); os.fsync(output.fileno())
        os.chmod(temporary,mode)
        if os.name!='nt': os.chown(temporary,path.parent.stat().st_uid,path.parent.stat().st_gid)
        safe_path(path); os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()

@contextlib.contextmanager
def task_lock(root, name):
    import fcntl
    path=safe_path(root/(name+'.lock'))
    fd=os.open(str(path),os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB); yield
    finally: os.close(fd)

def command(args):
    return subprocess.run(args,timeout=3,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=True,text=True).stdout.strip()

def local_https(ip, path):
    # TCP goes to loopback; hostname/IP verification and system CA trust stay enabled.
    import ipaddress
    ipaddress.ip_address(ip)
    context=ssl.create_default_context()
    with socket.create_connection(('127.0.0.1',443),timeout=3) as raw:
        with context.wrap_socket(raw,server_hostname=ip) as secure:
            cert=secure.getpeercert()
            secure.sendall(('GET '+path+' HTTP/1.1\r\nHost: '+ip+'\r\nConnection: close\r\n\r\n').encode('ascii'))
            data=b''; deadline=time.monotonic()+6
            while len(data)<262144:
                if time.monotonic()>deadline: raise TimeoutError()
                secure.settimeout(max(.1,min(3,deadline-time.monotonic())))
                chunk=secure.recv(16384)
                if not chunk: break
                data+=chunk
            if not data.split(b'\r\n',1)[0].split()[1]==b'200': raise ValueError('http_failed')
            return data,cert

def database_probe(url):
    code="import sys; from sqlalchemy import create_engine,text; e=create_engine(sys.stdin.read(),connect_args={'connect_timeout':3,'options':'-c statement_timeout=3000'}); c=e.connect(); c.execute(text('SELECT 1')).scalar_one(); c.close(); e.dispose()"
    subprocess.run(['sudo','-n','-u','finsentinel','/opt/finsentinel/.venv/bin/python','-c',code],input=url,text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=6,check=True)

def result_age(private, kind):
    try:
        latest=json.loads(safe_path(private/(kind+'.json')).read_text(encoding='utf-8'))
        if latest.get('status')!='ok': return 'critical','task_failed'
        data=json.loads(safe_path(private/(kind+'_success.json')).read_text(encoding='utf-8'))
        age=(datetime.now(timezone.utc)-parsed_time(data['finished_at'])).total_seconds()
        if age < -60: raise ValueError()
        status=age_status(age,kind)
        return status, 'check_passed' if status=='ok' else ('backup_expired' if status=='critical' else kind+'_aging')
    except (OSError,ValueError,KeyError,TypeError): return 'unknown','never_completed'

def run_checks(state, database_url, ip):
    checks=[]; started=time.monotonic()
    def probe(key, action):
        before=time.monotonic(); metadata={}
        try:
            if before-started>110: raise TimeoutError()
            value=action(); metadata=value if isinstance(value,dict) else {}; value=(metadata['status'],metadata['reason']) if metadata else value
            status,reason=value if isinstance(value,tuple) and len(value)==2 and isinstance(value[0],str) and value[0] in ('ok','warning','critical','unknown') else ('ok','check_passed')
        except (TimeoutError,subprocess.TimeoutExpired,socket.timeout): status,reason='critical','check_timeout'
        except Exception: status,reason='critical','check_failed'
        checks.append(dict(id=key,label=LABELS[key],status=status,reason=reason,checked_at=stamp(),duration_ms=min(120000,round((time.monotonic()-before)*1000))))
        checks[-1].update({k:v for k,v in metadata.items() if k in ('last_success_at','expires_at','free_bytes','total_bytes')})
    units={'nginx':'nginx','backend':'finsentinel-backend','frontend':'finsentinel-frontend','ingestion_worker':'finsentinel-ingestion-worker','query_encoder':'finsentinel-query-encoder','renewal_timer':'finsentinel-ip-cert-renew.timer','backup_timer':'finsentinel-ops-backup.timer','restore_timer':'finsentinel-ops-restore.timer'}
    for key,unit in units.items():
        def unit_check(unit=unit):
            if command(['systemctl','is-active',unit])!='active': raise ValueError()
            if unit.endswith('.timer') and command(['systemctl','is-enabled',unit])!='enabled': raise ValueError()
        probe(key,unit_check)
    def renewal():
        data=command(['systemctl','show','finsentinel-ip-cert-renew.service','--property=Result','--property=ExecMainStatus','--property=ExecMainStartTimestampMonotonic'])
        values=dict(line.split('=',1) for line in data.splitlines())
        if values.get('ExecMainStartTimestampMonotonic','0')=='0': return 'unknown','never_completed'
        if values.get('Result')!='success' or values.get('ExecMainStatus')!='0': raise ValueError()
    probe('renewal',renewal)
    probe('database',lambda: database_probe(database_url))
    probe('https_health',lambda: local_https(ip,'/health'))
    login=[None]
    def login_probe(): login[0]=local_https(ip,'/login')[0]
    probe('https_login',login_probe)
    def static_probe():
        import re
        if not login[0]: raise ValueError()
        assets=re.findall(rb'(?:src|href)="(/_next/static/[^"<>]+)"',login[0])
        if not assets: raise ValueError()
        local_https(ip,assets[0].decode('ascii'))
    probe('https_static',static_probe)
    def encoder():
        from urllib.request import build_opener,ProxyHandler
        with build_opener(ProxyHandler({})).open('http://127.0.0.1:8081/health',timeout=3) as response:
            if response.status!=200: raise ValueError()
    probe('encoder_health',encoder)
    def disk():
        usage=shutil.disk_usage('/'); status=disk_status(usage.free,usage.total)
        return dict(status=status,reason='check_passed' if status=='ok' else 'disk_critical' if status=='critical' else 'disk_low',free_bytes=usage.free,total_bytes=usage.total)
    probe('disk',disk)
    def certificate():
        _,cert=local_https(ip,'/health'); remaining=ssl.cert_time_to_seconds(cert['notAfter'])-time.time(); status=certificate_status(remaining)
        return dict(status=status,reason='check_passed' if status=='ok' else 'certificate_urgent' if status=='critical' else 'certificate_expiring',expires_at=datetime.fromtimestamp(ssl.cert_time_to_seconds(cert['notAfter']),timezone.utc).isoformat())
    probe('certificate',certificate)
    def recovery(kind):
        status,reason=result_age(state/'private',kind)
        result=dict(status=status,reason=reason)
        try:
            data=json.loads(safe_path(state/'private'/(kind+'_success.json')).read_text(encoding='utf-8'))
            when=parsed_time(data['finished_at'])
            if (when-datetime.now(timezone.utc)).total_seconds()<=60: result['last_success_at']=when.astimezone(timezone.utc).isoformat()
        except (OSError,ValueError,TypeError,KeyError): pass
        return result
    for kind in ('backup','restore'): probe(kind,lambda kind=kind:recovery(kind))
    return checks

def print_diagnostic(task,result):
    diagnostics={'missing_original','backup_failed','restore_failed','restore_cleanup_failed','backup_invalid','disk_full','configuration_missing'}
    detail=result.get('reason')
    if detail in diagnostics: print(task+': '+detail)
    digest=result.get('missing_sha256')
    import re
    if detail=='missing_original' and isinstance(digest,str) and re.fullmatch(r'[0-9a-f]{64}',digest): print('missing_sha256='+digest)

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('task',choices=('backup','restore','check'))
    parser.add_argument('--backup-root',default='/var/backups/finsentinel')
    parser.add_argument('--state-root',default='/var/lib/finsentinel/operations')
    parser.add_argument('--artifact-root',default='/var/lib/finsentinel/ingestion')
    parser.add_argument('--config-path',action='append',default=[])
    args=parser.parse_args(argv)
    if not args.config_path:
        args.config_path=[str(p) for pattern in ('/etc/finsentinel/*.env','/etc/systemd/system/finsentinel-*.service','/etc/systemd/system/finsentinel-*.service.d/*.conf','/etc/systemd/system/finsentinel-ops-*.timer') for p in Path('/').glob(pattern.lstrip('/'))]
        if args.task=='backup' and not args.config_path: raise SystemExit('configuration_missing')
    if os.geteuid()!=0: raise SystemExit('root_required')
    state=safe_path(args.state_root); state.mkdir(mode=0o750,parents=True,exist_ok=True)
    if state.stat().st_uid!=0: raise SystemExit('unsafe_state_owner')
    os.chmod(state,0o750)
    private=safe_path(state/'private'); private.mkdir(mode=0o700,exist_ok=True)
    if private.stat().st_uid!=0: raise SystemExit('unsafe_private_owner')
    os.chmod(private,0o700)
    url=os.getenv('DATABASE_URL','')
    with task_lock(private,'check' if args.task=='check' else 'maintenance'):
        if args.task=='check':
            from app.operations import read_status
            previous=read_status(state/'status.json',enforce_fresh=False)
            checks=run_checks(state,url,os.getenv('OPERATIONS_PUBLIC_IP','120.24.108.60'))
            atomic_json(state/'status.json',dict(schema_version=1,checked_at=stamp(),status=aggregate(checks),checks=checks,history=merge_history(previous['history'],checks)),0o640)
            print('check: '+aggregate(checks))
            return 0
        from scripts.operations_backup import backup,restore
        try:
            result=backup(url,args.backup_root,args.artifact_root,config_paths=args.config_path,source_revision=os.getenv('OPERATIONS_SOURCE_REVISION','unknown')) if args.task=='backup' else restore(url,args.backup_root)
        except Exception: result={'status':'critical','reason':'task_failed','finished_at':stamp()}
        # Never persist library exception text or unreviewed metadata.
        safe=dict(status='ok' if result.get('status')=='ok' else 'critical',reason='check_passed' if result.get('status')=='ok' else 'task_failed',finished_at=stamp())
        atomic_json(private/(args.task+'.json'),safe)
        if safe['status']=='ok': atomic_json(private/(args.task+'_success.json'),safe)
        print_diagnostic(args.task,result)
        print(args.task+': '+safe['status']+' '+safe['reason'])
        return 0 if safe['status']=='ok' else 1

if __name__=='__main__':
    try: raise SystemExit(main())
    except BlockingIOError: raise SystemExit('maintenance_busy')
    except Exception: raise SystemExit('maintenance_failed')

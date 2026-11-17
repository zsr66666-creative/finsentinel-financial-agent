"""Pull and verify age-encrypted recovery points from the restricted ECS SFTP account."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from scripts.verify_offsite_archive import verify_archive

BACKUP_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\Z')
ARCHIVE_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\.tar\.gz\.age\Z')
INDEX_RE = re.compile(r'(backup-\d{8}T\d{12}Z-[0-9a-f]{32}\.tar\.gz\.age)\.json\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
INDEX_KEYS = {'schema_version','backup_id','filename','ciphertext_size','ciphertext_sha256'}
SFTP_TIMEOUT = 90
AGE_TIMEOUT = 1800
STATUS_KEYS = {'ok','critical'}


class PullError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _safe_local_path(path, *, exists=False):
    path=Path(path).absolute()
    if '..' in path.parts or any(part.is_symlink() for part in (path,*path.parents)):
        raise PullError('configuration_invalid')
    if exists and not path.exists():
        raise PullError('configuration_missing')
    return path


def _sftp_base(config):
    try:
        ipaddress.IPv4Address(config['server'])
        if config['username']!='finsentinel-backup-pull' or config['remote_dir']!='/exports':
            raise ValueError()
        known_hosts=_safe_local_path(config['known_hosts'],exists=True)
        ssh_key=_safe_local_path(config['ssh_key'],exists=True)
        _safe_local_path(config['age_identity'],exists=True)
    except (KeyError,TypeError,ValueError):
        raise PullError('configuration_invalid') from None
    return [config.get('sftp_exe','sftp.exe'),'-q','-b','-','-i',str(ssh_key),
            '-oBatchMode=yes','-oIdentitiesOnly=yes','-oStrictHostKeyChecking=yes',
            '-oHostKeyAlgorithms=ssh-ed25519','-oUserKnownHostsFile='+str(known_hosts),
            '-oConnectTimeout=10',f"{config['username']}@{config['server']}"]


def _run_sftp(base, batch, runner):
    try:
        result=runner(base,input=batch,text=True,stdout=subprocess.PIPE,
                      stderr=subprocess.DEVNULL,timeout=SFTP_TIMEOUT,check=True)
    except Exception:
        raise PullError('sftp_unavailable') from None
    if getattr(result,'returncode',0)!=0:
        raise PullError('sftp_unavailable')
    output=getattr(result,'stdout','')
    if not isinstance(output,str) or len(output)>1024*1024:
        raise PullError('remote_listing_invalid')
    return output


def _latest_index(output):
    candidates=[]
    for line in output.splitlines():
        name=line.strip()
        if name.startswith('/exports/'):
            name=name[len('/exports/'):]
        match=INDEX_RE.fullmatch(name)
        if match:
            candidates.append((match.group(1)[:-len('.tar.gz.age')],name))
    if not candidates:
        raise PullError('backup_missing')
    return max(candidates)[1]


def _quote_sftp(value):
    return '"'+str(value).replace('\\','/').replace('"','\\"')+'"'


def _download_one(base, remote_name, stage_name, runner, local_dir):
    token=uuid.uuid4().hex
    local_name=f'.partial-{token}-{stage_name}'
    batch=f'lcd {_quote_sftp(local_dir)}\nget /exports/{remote_name} {local_name}\n'
    _run_sftp(base,batch,runner)
    return local_dir/local_name


def _read_index(path, selected_name):
    if path.stat().st_size>16*1024:
        raise PullError('index_invalid')
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,UnicodeError,ValueError):
        raise PullError('index_invalid') from None
    archive_name=selected_name[:-len('.json')]
    match=INDEX_RE.fullmatch(selected_name)
    expected_id=match.group(1)[:-len('.tar.gz.age')] if match else ''
    if (not isinstance(data,dict) or set(data)!=INDEX_KEYS or data.get('schema_version')!=1
            or data.get('backup_id')!=expected_id or data.get('filename')!=archive_name
            or not BACKUP_RE.fullmatch(str(data.get('backup_id','')))
            or type(data.get('ciphertext_size')) is not int or data['ciphertext_size']<=0
            or not isinstance(data.get('ciphertext_sha256'),str)
            or not SHA_RE.fullmatch(data['ciphertext_sha256'])):
        raise PullError('index_invalid')
    return data


def _hash_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def _read_local_pair(root, archive_name):
    if not ARCHIVE_RE.fullmatch(archive_name):
        raise PullError('local_integrity_failed')
    archive=_safe_local_path(root/archive_name,exists=True)
    index=_safe_local_path(root/(archive_name+'.json'),exists=True)
    if archive.is_symlink() or index.is_symlink() or not archive.is_file() or not index.is_file():
        raise PullError('local_integrity_failed')
    data=_read_index(index,archive_name+'.json')
    if archive.stat().st_size!=data['ciphertext_size'] or _hash_file(archive)!=data['ciphertext_sha256']:
        raise PullError('local_integrity_failed')
    return data


def _prune_local(root):
    pairs=[]
    for archive in root.iterdir():
        if archive.is_symlink() or not ARCHIVE_RE.fullmatch(archive.name):
            continue
        try:
            data=_read_local_pair(root,archive.name)
        except (OSError,ValueError,PullError):
            continue
        pairs.append((data['backup_id'],archive.name))
    pairs.sort()
    for _,name in pairs[:-7]:
        _read_local_pair(root,name)
        (root/(name+'.json')).unlink()
        (root/name).unlink()


def _verify_age_stream(cipher_path, identity, popen, verifier):
    process=None
    outcome={}
    finished=threading.Event()
    try:
        encrypted=cipher_path.open('rb')
        try:
            process=popen(['age','--decrypt','--identity',str(identity)],stdin=encrypted,
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        finally:
            encrypted.close()
        if process.stdout is None:
            raise PullError('decryption_failed')

        def verify_worker():
            try:
                outcome['archive']=verifier(process.stdout)
            except Exception as exc:
                outcome['error']=exc
            finally:
                finished.set()

        worker=threading.Thread(target=verify_worker,daemon=True)
        worker.start()
        deadline=time.monotonic()+AGE_TIMEOUT
        while process.poll() is None:
            if finished.wait(0.05) and 'error' in outcome:
                process.terminate()
                break
            if time.monotonic()>=deadline:
                process.kill()
                raise PullError('decryption_timeout')
        try:
            code=process.wait(timeout=10)
        except Exception:
            process.kill()
            raise PullError('decryption_failed') from None
        worker.join(timeout=10)
        if worker.is_alive():
            process.kill()
            raise PullError('decryption_timeout')
        if code!=0:
            raise PullError('decryption_failed')
        if 'error' in outcome:
            raise PullError('archive_invalid') from outcome['error']
    except PullError:
        raise
    except Exception:
        if process is not None and process.poll() is None:
            process.kill()
        raise PullError('decryption_failed') from None


def _write_status(path, status, reason):
    path=_safe_local_path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    temporary=path.parent/f'.pull-status-{token}.tmp'
    data={'checked_at':datetime.now(timezone.utc).isoformat(),
          'status':status if status in STATUS_KEYS else 'critical',
          'reason':reason}
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            if os.name=='posix': os.chmod(temporary,0o600)
            json.dump(data,stream,sort_keys=True)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def _pull(config, *, command_runner, popen, verifier):
    base=_sftp_base(config)
    local_dir=_safe_local_path(config['local_dir'])
    local_dir.mkdir(parents=True,exist_ok=True)
    if local_dir.is_symlink() or not local_dir.is_dir():
        raise PullError('configuration_invalid')
    listing=_run_sftp(base,'ls -1 /exports/*.tar.gz.age.json\n',command_runner)
    index_name=_latest_index(listing)
    index_stage=cipher_stage=None
    promoted_archive=None
    promoted_index=None
    try:
        index_stage=_download_one(base,index_name,'index',command_runner,local_dir)
        index=_read_index(index_stage,index_name)
        archive_name=index_name[:-len('.json')]
        if index['filename']!=archive_name:
            raise PullError('index_invalid')
        free=shutil.disk_usage(local_dir).free
        if index['ciphertext_size']+16*1024*1024>free:
            raise PullError('disk_insufficient')
        cipher_stage=_download_one(base,archive_name,'ciphertext',command_runner,local_dir)
        if (cipher_stage.stat().st_size!=index['ciphertext_size']
                or _hash_file(cipher_stage)!=index['ciphertext_sha256']):
            raise PullError('ciphertext_integrity_failed')
        _verify_age_stream(cipher_stage,config['age_identity'],popen,verifier)
        final_archive=local_dir/archive_name
        final_index=local_dir/(archive_name+'.json')
        if final_archive.exists() or final_index.exists():
            try:
                existing=_read_local_pair(local_dir,archive_name)
            except (OSError,ValueError,PullError):
                raise PullError('local_conflict') from None
            if existing['ciphertext_sha256']!=index['ciphertext_sha256']:
                raise PullError('local_conflict')
        else:
            os.replace(cipher_stage,final_archive)
            promoted_archive=final_archive
            os.replace(index_stage,final_index)
            promoted_index=final_index
            _read_local_pair(local_dir,archive_name)
        _prune_local(local_dir)
        backup_id=index['backup_id']
        return {'status':'ok','reason':'verified','backup_id':backup_id}
    finally:
        for path in (index_stage,cipher_stage):
            if path is not None:
                path.unlink(missing_ok=True)
        if promoted_archive is not None and promoted_index is None:
            promoted_archive.unlink(missing_ok=True)


def pull_latest(config, *, command_runner=subprocess.run, popen=subprocess.Popen,
                verifier=verify_archive):
    try:
        result=_pull(config,command_runner=command_runner,popen=popen,verifier=verifier)
    except PullError as exc:
        result={'status':'critical','reason':exc.reason}
    except Exception:
        result={'status':'critical','reason':'task_failed'}
    status_path=config.get('status_path') or Path(config.get('local_dir','.')).parent/'pull-status.json'
    try:
        _write_status(status_path,result['status'],result['reason'])
    except Exception:
        if result['status']=='ok':
            return {'status':'critical','reason':'status_write_failed'}
    return result


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--server',required=True)
    parser.add_argument('--known-hosts',required=True)
    parser.add_argument('--ssh-key',required=True)
    parser.add_argument('--age-identity',required=True)
    parser.add_argument('--local-dir',required=True)
    parser.add_argument('--status-path')
    parser.add_argument('--sftp-exe',default='sftp.exe')
    args=parser.parse_args(argv)
    config={'server':args.server,'username':'finsentinel-backup-pull','remote_dir':'/exports',
            'known_hosts':args.known_hosts,'ssh_key':args.ssh_key,'age_identity':args.age_identity,
            'local_dir':args.local_dir,'status_path':args.status_path,'sftp_exe':args.sftp_exe}
    result=pull_latest(config)
    print('pull: '+result['status']+' '+result['reason'])
    return 0 if result['status']=='ok' else 1


if __name__=='__main__':
    raise SystemExit(main())

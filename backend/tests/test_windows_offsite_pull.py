import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from types import SimpleNamespace

import pytest


def make_archive():
    files={'database.dump':b'database','config.tar.gz':b'config'}
    records={name:{'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)} for name,data in files.items()}
    manifest={'schema_version':1,'managed_by':'finsentinel-operations','files':records,'artifact_refs':[]}
    encoded=json.dumps(manifest,separators=(',',':')).encode()
    contents={**files,'manifest.json':encoded,'COMPLETE':hashlib.sha256(encoded).hexdigest().encode()+b'\n'}
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as archive:
        root='backup-20261117T120000000000Z-'+'a'*32
        for name,data in contents.items():
            member=tarfile.TarInfo(f'{root}/{name}');member.size=len(data)
            archive.addfile(member,io.BytesIO(data))
    return output.getvalue()


class FakeSftp:
    def __init__(self,local_dir,index_bytes,ciphertext):
        self.local_dir=Path(local_dir)
        self.index_bytes=index_bytes
        self.ciphertext=ciphertext
        self.calls=[]

    def __call__(self,args,**kwargs):
        self.calls.append((args,kwargs))
        batch=kwargs.get('input','')
        if batch.startswith('ls -1 '):
            return SimpleNamespace(returncode=0,stdout='backup-20261117T120000000000Z-'+'a'*32+'.tar.gz.age.json\n')
        for remote,local in re.findall(r'get /exports/([^\s]+) ([^\s]+)',batch):
            path=self.local_dir/local
            path.write_bytes(self.index_bytes if remote.endswith('.json') else self.ciphertext)
        return SimpleNamespace(returncode=0,stdout='')


class FakeAge:
    def __init__(self,archive_bytes,returncode=0):
        self.stdout=io.BytesIO(archive_bytes)
        self.returncode=returncode
        self.args=None
        self.stdin=None

    def wait(self,timeout=None): return self.returncode
    def poll(self): return self.returncode
    def terminate(self): self.returncode=-15
    def kill(self): self.returncode=-9


def make_config(tmp_path):
    paths={'known_hosts':tmp_path/'known_hosts','ssh_key':tmp_path/'sftp_key','age_identity':tmp_path/'identity.txt'}
    for name,path in paths.items(): path.write_text(name)
    return {'server':'120.24.108.60','username':'finsentinel-backup-pull','remote_dir':'/exports',
            **paths,'local_dir':tmp_path/'backup-copy'}


def test_pull_latest_verifies_and_promotes_ciphertext_without_plaintext(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    archive=make_archive()
    ciphertext=b'age encrypted bytes'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':filename,
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    index_bytes=json.dumps(index).encode()
    runner=FakeSftp(config['local_dir'],index_bytes,ciphertext)
    age=FakeAge(archive)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:age)

    assert result=={'status':'ok','reason':'verified','backup_id':backup_id}
    assert (config['local_dir']/filename).read_bytes()==ciphertext
    assert json.loads((config['local_dir']/(filename+'.json')).read_text())==index
    assert not list(config['local_dir'].glob('*.tar.gz'))
    assert (config['local_dir'].parent/'pull-status.json').is_file()
    assert len(runner.calls)==3


def test_pull_rejects_ciphertext_hash_mismatch_and_keeps_previous_copy(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    config['local_dir'].mkdir()
    previous=config['local_dir']/('backup-20261116T120000000000Z-'+'b'*32+'.tar.gz.age')
    previous.write_bytes(b'previous ciphertext')
    ciphertext=b'corrupted ciphertext'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    index={'schema_version':1,'backup_id':backup_id,'filename':backup_id+'.tar.gz.age',
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':'0'*64}
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:pytest.fail('age must not run'))

    assert result=={'status':'critical','reason':'ciphertext_integrity_failed'}
    assert previous.read_bytes()==b'previous ciphertext'
    assert not list(config['local_dir'].glob('*.partial-*'))


def test_pull_rejects_age_failure_without_promoting_candidate(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    ciphertext=b'age encrypted bytes'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':filename,
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:FakeAge(make_archive(),returncode=1))

    assert result=={'status':'critical','reason':'decryption_failed'}
    assert not list(config['local_dir'].glob('*.tar.gz.age'))


def test_pull_checks_index_and_free_space_before_ciphertext_download(tmp_path,monkeypatch):
    import scripts.windows_offsite_pull as module
    config=make_config(tmp_path)
    ciphertext=b'age encrypted bytes'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':filename,
           'ciphertext_size':100*1024*1024,'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _path:SimpleNamespace(free=20*1024*1024,total=40*1024*1024,used=20*1024*1024))

    result=module.pull_latest(config,command_runner=runner,popen=lambda *a,**k:pytest.fail('age must not run'))

    assert result=={'status':'critical','reason':'disk_insufficient'}
    assert len(runner.calls)==2
    assert all(f'get /exports/{filename} ' not in call[1].get('input','') for call in runner.calls)
    assert not list(config['local_dir'].glob('*.partial-*'))


def test_pull_rejects_index_filename_mismatch_before_ciphertext_download(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    ciphertext=b'age encrypted bytes'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':'backup-other.tar.gz.age',
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:pytest.fail('age must not run'))

    assert result=={'status':'critical','reason':'index_invalid'}
    assert len(runner.calls)==2
    assert all(f'get /exports/{filename} ' not in call[1].get('input','') for call in runner.calls)


def test_pull_sftp_interruption_preserves_existing_copy(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    config['local_dir'].mkdir()
    old=config['local_dir']/('backup-20261116T120000000000Z-'+'c'*32+'.tar.gz.age')
    old.write_bytes(b'good ciphertext')
    calls=[]
    def fail_on_second_call(args,**kwargs):
        calls.append(kwargs.get('input',''))
        if len(calls)==1:
            return SimpleNamespace(returncode=0,stdout='backup-20261117T120000000000Z-'+'a'*32+'.tar.gz.age.json\n')
        raise OSError('connection reset')

    result=pull_latest(config,command_runner=fail_on_second_call,popen=lambda *a,**k:pytest.fail('age must not run'))

    assert result=={'status':'critical','reason':'sftp_unavailable'}
    assert old.read_bytes()==b'good ciphertext'
    assert not list(config['local_dir'].glob('*.partial-*'))


def test_pull_rejects_corrupt_decrypted_archive_and_keeps_previous_copy(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    config['local_dir'].mkdir()
    old=config['local_dir']/('backup-20261116T120000000000Z-'+'c'*32+'.tar.gz.age')
    old.write_bytes(b'good ciphertext')
    ciphertext=b'age encrypted bytes'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':filename,
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:FakeAge(b'broken archive'))

    assert result=={'status':'critical','reason':'archive_invalid'}
    assert old.read_bytes()==b'good ciphertext'
    assert not (config['local_dir']/filename).exists()


def test_pull_duplicate_backup_is_idempotent_after_validation(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    config['local_dir'].mkdir()
    ciphertext=b'age encrypted bytes'
    archive=make_archive()
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':filename,
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    (config['local_dir']/filename).write_bytes(ciphertext)
    (config['local_dir']/(filename+'.json')).write_text(json.dumps(index))
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:FakeAge(archive))

    assert result=={'status':'ok','reason':'verified','backup_id':backup_id}
    assert (config['local_dir']/filename).read_bytes()==ciphertext


def test_pull_retains_seven_verified_pairs_after_success(tmp_path):
    from scripts.windows_offsite_pull import pull_latest
    config=make_config(tmp_path)
    config['local_dir'].mkdir()
    for day in range(10,17):
        backup_id=f'backup-202611{day:02d}T120000000000Z-'+'b'*32
        name=backup_id+'.tar.gz.age';ciphertext=f'old {day}'.encode()
        (config['local_dir']/name).write_bytes(ciphertext)
        index={'schema_version':1,'backup_id':backup_id,'filename':name,'ciphertext_size':len(ciphertext),
               'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
        (config['local_dir']/(name+'.json')).write_text(json.dumps(index))
    ciphertext=b'new encrypted bytes'
    backup_id='backup-20261117T120000000000Z-'+'a'*32
    filename=backup_id+'.tar.gz.age'
    index={'schema_version':1,'backup_id':backup_id,'filename':filename,
           'ciphertext_size':len(ciphertext),'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    runner=FakeSftp(config['local_dir'],json.dumps(index).encode(),ciphertext)

    result=pull_latest(config,command_runner=runner,popen=lambda *a,**k:FakeAge(make_archive()))

    assert result['status']=='ok'
    assert len(list(config['local_dir'].glob('*.tar.gz.age')))==7
    assert len(list(config['local_dir'].glob('*.tar.gz.age.json')))==7
    assert not (config['local_dir']/('backup-20261110T120000000000Z-'+'b'*32+'.tar.gz.age')).exists()

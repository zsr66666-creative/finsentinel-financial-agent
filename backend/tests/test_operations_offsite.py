import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest


def make_backup_tar(path, *, unsafe_name=None, tamper=False, malformed_directory=False):
    files={'database.dump':b'database','config.tar.gz':b'config'}
    records={name:{'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)} for name,data in files.items()}
    manifest={'schema_version':1,'managed_by':'finsentinel-operations','files':records,'artifact_refs':[]}
    manifest_bytes=json.dumps(manifest,separators=(',',':')).encode()
    contents={**files,'manifest.json':manifest_bytes,'COMPLETE':hashlib.sha256(manifest_bytes).hexdigest().encode()+b'\n'}
    if tamper: contents['database.dump']=b'altered'
    with tarfile.open(path,'w:gz') as archive:
        root='backup-20261117T120000000000Z-'+'a'*32
        if malformed_directory:
            member=tarfile.TarInfo(f'{root}/folder/')
            member.type=tarfile.DIRTYPE; member.size=1
            archive.addfile(member,io.BytesIO(b'x'))
        for name,data in contents.items():
            member=tarfile.TarInfo(f'{root}/{unsafe_name or name}')
            member.size=len(data); archive.addfile(member,io.BytesIO(data))


def make_recovery_point(root, stamp, suffix):
    root.mkdir(parents=True,exist_ok=True)
    point=root/f'backup-{stamp}-{suffix*32}'
    point.mkdir()
    payloads={'database.dump':b'database payload','config.tar.gz':b'config payload'}
    records={name:{'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)} for name,data in payloads.items()}
    for name,data in payloads.items(): (point/name).write_bytes(data)
    manifest={'schema_version':1,'managed_by':'finsentinel-operations','files':records,'artifact_refs':[]}
    encoded=json.dumps(manifest,separators=(',',':')).encode()
    (point/'manifest.json').write_bytes(encoded)
    (point/'COMPLETE').write_bytes(hashlib.sha256(encoded).hexdigest().encode()+b'\n')
    return point


def make_export_pair(root, stamp, suffix, ciphertext):
    archive_name=f'backup-{stamp}-{suffix*32}.tar.gz.age'
    archive=root/archive_name
    archive.write_bytes(ciphertext)
    index={'schema_version':1,'backup_id':archive_name.removesuffix('.tar.gz.age'),
           'filename':archive_name,'ciphertext_size':len(ciphertext),
           'ciphertext_sha256':hashlib.sha256(ciphertext).hexdigest()}
    (root/(archive_name+'.json')).write_text(json.dumps(index,separators=(',',':')))
    return archive_name


def test_archive_verifier_checks_manifest_and_each_file(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path)
    result=verify_archive(path)
    assert result['files']==2

    make_backup_tar(path,tamper=True)
    with pytest.raises(ValueError,match='file_integrity'):
        verify_archive(path)


def test_archive_verifier_accepts_binary_stream_and_preserves_caller_stream(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path)
    expected=verify_archive(path)
    with path.open('rb') as stream:
        actual=verify_archive(stream)
        assert not stream.closed
    assert actual==expected


def test_archive_verifier_rejects_truncated_binary_stream(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path)
    with pytest.raises(ValueError,match='archive_invalid'):
        verify_archive(io.BytesIO(path.read_bytes()[:-12]))


def test_archive_verifier_rejects_malformed_binary_stream():
    from scripts.verify_offsite_archive import verify_archive
    with pytest.raises(ValueError,match='archive_invalid'):
        verify_archive(io.BytesIO(b'not a gzip tar archive'))


def test_archive_verifier_rejects_unsafe_member_paths(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path,unsafe_name='../escape')
    with pytest.raises(ValueError,match='unsafe_archive'):
        verify_archive(path)


def test_archive_verifier_rejects_data_attached_to_directory_members(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path,malformed_directory=True)
    with pytest.raises(ValueError,match='unsafe_archive'):
        verify_archive(path)


def test_export_latest_publishes_ciphertext_and_exact_index(tmp_path):
    from scripts.operations_offsite import export_latest
    backups=tmp_path/'backups'
    make_recovery_point(backups,'20261116T120000000000Z','a')
    latest=make_recovery_point(backups,'20261117T120000000000Z','b')
    (backups/('backup-20261118T120000000000Z-'+'c'*32)).mkdir()
    exports=tmp_path/'exports'

    def encrypt(point,recipient,destination):
        assert point==latest and recipient.startswith('age1')
        Path(destination).write_bytes(b'opaque ciphertext')

    result=export_latest(backups,exports,'age1recipient',encryptor=encrypt)

    filename=latest.name+'.tar.gz.age'
    index=json.loads((exports/(filename+'.json')).read_text())
    assert result['status']=='ok'
    assert result['backup_id']==latest.name
    assert set(index)=={'schema_version','backup_id','filename','ciphertext_size','ciphertext_sha256'}
    assert index['filename']==filename
    assert index['ciphertext_size']==len(b'opaque ciphertext')
    assert index['ciphertext_sha256']==hashlib.sha256(b'opaque ciphertext').hexdigest()
    assert (exports/filename).read_bytes()==b'opaque ciphertext'


def test_export_root_owner_matches_the_privileged_process_context(tmp_path):
    import os
    from scripts.operations_offsite import _ensure_export_root
    if os.name != 'posix':
        pytest.skip('POSIX ownership contract')

    root=_ensure_export_root(tmp_path/'exports')

    assert root.stat().st_uid==(0 if os.geteuid()==0 else os.geteuid())


def test_export_rejects_group_writable_existing_root(tmp_path):
    import os
    from scripts.operations_offsite import export_latest
    if os.name != 'posix':
        pytest.skip('POSIX permission contract')
    backups=tmp_path/'backups'
    make_recovery_point(backups,'20261117T120000000000Z','g')
    exports=tmp_path/'exports'
    exports.mkdir(mode=0o775)
    exports.chmod(0o775)

    result=export_latest(backups,exports,'age1recipient',
                         encryptor=lambda *_:pytest.fail('must reject writable root'))

    assert result['status']=='critical'
    assert result['reason']=='configuration_invalid'
    assert result['backup_id'] is None


def test_export_retention_keeps_seven_verified_pairs_and_unmanaged_files(tmp_path):
    from scripts.operations_offsite import export_latest
    backups=tmp_path/'backups'
    point=make_recovery_point(backups,'20261117T120000000000Z','e')
    exports=tmp_path/'exports'
    exports.mkdir(mode=0o755)
    old_names=[]
    for day in range(10,17):
        old_names.append(make_export_pair(exports,f'202611{day:02d}T120000000000Z',f'{day:x}'[-1],b'old-'+bytes([day])))
    (exports/'operator-notes.txt').write_text('keep')

    result=export_latest(backups,exports,'age1recipient',encryptor=lambda _p,_r,d:Path(d).write_bytes(b'new ciphertext'))

    managed=[path.name for path in exports.glob('*.tar.gz.age')]
    assert result['status']=='ok'
    assert len(managed)==7
    assert old_names[0] not in managed
    assert (exports/'operator-notes.txt').read_text()=='keep'
    assert point.name==result['backup_id']


def test_export_failure_preserves_existing_pairs_and_cleans_own_partial(tmp_path):
    from scripts.operations_offsite import export_latest
    backups=tmp_path/'backups'
    make_recovery_point(backups,'20261117T120000000000Z','f')
    exports=tmp_path/'exports'
    exports.mkdir(mode=0o755)
    old=make_export_pair(exports,'20261116T120000000000Z','d',b'old ciphertext')
    before={path.name:path.read_bytes() for path in exports.iterdir() if path.name!='.export.lock'}

    def fail_after_partial(_point,_recipient,destination):
        Path(destination).write_bytes(b'partial')
        raise RuntimeError('encryption interrupted')

    result=export_latest(backups,exports,'age1recipient',encryptor=fail_after_partial)

    assert result['status']=='critical'
    assert {path.name:path.read_bytes() for path in exports.iterdir() if path.name!='.export.lock'}==before
    assert old in {path.name for path in exports.glob('*.tar.gz.age')}
    assert not list(exports.glob('.partial-*'))


def test_export_rejects_conflicting_existing_backup_id(tmp_path):
    from scripts.operations_offsite import export_latest
    backups=tmp_path/'backups'
    point=make_recovery_point(backups,'20261117T120000000000Z','a')
    exports=tmp_path/'exports'
    exports.mkdir(mode=0o755)
    name=make_export_pair(exports,'20261117T120000000000Z','a',b'ciphertext')
    (exports/(name+'.json')).write_text('{}')
    before={path.name:path.read_bytes() for path in exports.iterdir() if path.name!='.export.lock'}

    result=export_latest(backups,exports,'age1recipient',encryptor=lambda *_:pytest.fail('must not overwrite'))

    assert result['status']=='critical'
    assert {path.name:path.read_bytes() for path in exports.iterdir() if path.name!='.export.lock'}==before
    assert point.name==result['backup_id']


def test_export_repeated_backup_is_idempotent(tmp_path):
    from scripts.operations_offsite import export_latest
    backups=tmp_path/'backups'
    point=make_recovery_point(backups,'20261117T120000000000Z','a')
    exports=tmp_path/'exports'
    calls=[]
    def encrypt(_point,_recipient,destination):
        calls.append(True)
        Path(destination).write_bytes(b'ciphertext')

    first=export_latest(backups,exports,'age1recipient',encryptor=encrypt)
    second=export_latest(backups,exports,'age1recipient',encryptor=encrypt)

    assert first==second
    assert len(calls)==1
    assert point.name==second['backup_id']


def test_export_index_publish_failure_removes_only_unindexed_new_archive(tmp_path,monkeypatch):
    import scripts.operations_offsite as module
    backups=tmp_path/'backups'
    make_recovery_point(backups,'20261117T120000000000Z','a')
    exports=tmp_path/'exports'
    exports.mkdir(mode=0o755)
    old=make_export_pair(exports,'20261116T120000000000Z','d',b'old ciphertext')
    before={path.name:path.read_bytes() for path in exports.iterdir()}
    real_replace=module.os.replace

    def fail_index_replace(source,destination):
        if str(destination).endswith('.tar.gz.age.json'):
            raise OSError('index publish failure')
        real_replace(source,destination)

    monkeypatch.setattr(module.os,'replace',fail_index_replace)
    result=module.export_latest(backups,exports,'age1recipient',
                                encryptor=lambda _p,_r,d:Path(d).write_bytes(b'new ciphertext'))

    after={path.name:path.read_bytes() for path in exports.iterdir() if path.name!='.export.lock'}
    assert result['status']=='critical'
    assert after==before
    assert old in {path.name for path in exports.glob('*.tar.gz.age')}
    assert not list(exports.glob('.partial-*'))


def test_export_rejects_symlinked_export_root(tmp_path):
    from scripts.operations_offsite import export_latest
    backups=tmp_path/'backups'
    make_recovery_point(backups,'20261117T120000000000Z','a')
    real=tmp_path/'real-exports'
    real.mkdir()
    link=tmp_path/'exports-link'
    try:
        link.symlink_to(real,target_is_directory=True)
    except OSError:
        pytest.skip('symlink privilege unavailable')

    result=export_latest(backups,link,'age1recipient',encryptor=lambda *_:pytest.fail('must reject path'))

    assert result['status']=='critical'
    assert not list(real.iterdir())

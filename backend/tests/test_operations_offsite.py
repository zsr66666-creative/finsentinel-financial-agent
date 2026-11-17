import hashlib
import importlib
import json
import io
import subprocess
import tarfile
import hashlib
from pathlib import Path

import pytest


def module():
    return importlib.import_module('scripts.operations_offsite')


def point(tmp_path, monkeypatch):
    m = module()
    root = tmp_path/'backups'
    backup = root/('backup-20261117T120000000000Z-'+'a'*32)
    backup.mkdir(parents=True)
    (backup/'database.dump').write_bytes(b'private database material')
    monkeypatch.setattr(m, 'valid_backups', lambda path: [backup])
    monkeypatch.setattr(m, 'verify_backup', lambda path: {'files': {'database.dump': {}}})
    return root, backup


class FakeRemote:
    def __init__(self, *, total=10_000_000, free=None):
        self.total = total
        self.files = {}
        self.fail_upload = False
        self.bad_readback = False
        self.deleted = []
        self.uploaded = []
        self.moves = []
        self.fixed_free = free

    def quota(self):
        used = sum(len(value) for value in self.files.values())
        return {'total': self.total, 'used': used, 'free': self.fixed_free if self.fixed_free is not None else self.total-used}

    def list_objects(self):
        return [{'name': name, 'size': len(value)} for name, value in self.files.items()]

    def upload(self, source, name):
        self.uploaded.append(name)
        if self.fail_upload:
            raise RuntimeError('OAuth token=must-not-leak')
        self.files[name] = Path(source).read_bytes()

    def readback_sha256(self, name):
        data = self.files[name]
        return '0'*64 if self.bad_readback else hashlib.sha256(data).hexdigest()

    def move(self, source, destination):
        self.moves.append((source, destination))
        self.files[destination] = self.files.pop(source)

    def delete(self, name):
        self.deleted.append(name)
        del self.files[name]


def fake_encrypt(_point, recipient, destination):
    assert recipient.startswith('age1')
    Path(destination).write_bytes(b'age-encrypted:opaque-ciphertext')


def make_client_config(tmp_path):
    config = tmp_path/'rclone.conf'
    config.write_text('[drive]\ntype = drive\n')
    return config


def make_test_remote(m, config, remote_root, monkeypatch):
    monkeypatch.setattr(m, '_safe_config', lambda path: Path(path))
    return m.RcloneRemote(config, remote_root)


def add_managed_files(remote, count):
    for index in range(count):
        name = f'backup-202611{10+index:02d}T120000000000Z-{index:032x}.tar.gz.age'
        remote.files[name] = b'old-ciphertext-' + bytes([index])


def test_upload_verifies_ciphertext_then_prunes_oldest_managed_file(tmp_path, monkeypatch):
    m = module()
    root, _ = point(tmp_path, monkeypatch)
    client = FakeRemote()
    add_managed_files(client, 7)
    client.files['unmanaged-notes.txt'] = b'keep'
    monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)

    result = m.sync_latest(root, 'drive:FinSentinelOffsite', 'age1recipient', make_client_config(tmp_path), remote_client=client)

    assert result['status'] == 'ok'
    assert len([name for name in client.files if name.endswith('.tar.gz.age')]) == 7
    assert client.deleted == ['backup-20261110T120000000000Z-' + f'{0:032x}' + '.tar.gz.age']
    assert client.files['unmanaged-notes.txt'] == b'keep'
    final = 'backup-20261117T120000000000Z-' + 'a'*32 + '.tar.gz.age'
    assert client.files[final].startswith(b'age-encrypted:')


def test_quota_failure_keeps_all_existing_remote_objects(tmp_path, monkeypatch):
    m = module()
    root, _ = point(tmp_path, monkeypatch)
    client = FakeRemote(total=1, free=1)
    add_managed_files(client, 7)
    client.total = sum(len(value) for value in client.files.values()) + 1
    original = dict(client.files)
    monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)

    result = m.sync_latest(root, 'drive:FinSentinelOffsite', 'age1recipient', make_client_config(tmp_path), remote_client=client)

    assert result['status'] == 'critical'
    assert result['reason'] == 'quota_insufficient'
    assert client.files == original
    assert client.deleted == []


@pytest.mark.parametrize('failure', ['encrypt', 'upload', 'readback'])
def test_transfer_failure_never_prunes_existing_remote_objects(tmp_path, monkeypatch, failure):
    m = module()
    root, _ = point(tmp_path, monkeypatch)
    client = FakeRemote()
    add_managed_files(client, 7)
    original_names = set(client.files)
    if failure == 'encrypt':
        monkeypatch.setattr(m, '_encrypt_backup', lambda *args: (_ for _ in ()).throw(RuntimeError('token=must-not-leak')))
    else:
        monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)
    if failure == 'upload':
        client.fail_upload = True
    else:
        if failure == 'readback': client.bad_readback = True

    result = m.sync_latest(root, 'drive:FinSentinelOffsite', 'age1recipient', make_client_config(tmp_path), remote_client=client)

    assert result['status'] == 'critical'
    assert set(client.deleted) == set()
    assert original_names.issubset(client.files)
    assert 'OAuth token' not in json.dumps(result)


def test_invalid_source_and_missing_oauth_config_fail_closed(tmp_path, monkeypatch):
    m = module()
    root, backup = point(tmp_path, monkeypatch)
    client = FakeRemote()
    monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)
    config = make_client_config(tmp_path)
    config.unlink()

    result = m.sync_latest(root, 'drive:FinSentinelOffsite', 'age1recipient', config)

    assert result['status'] == 'critical'
    assert result['reason'] == 'configuration_missing'
    assert not client.uploaded

    monkeypatch.setattr(m, 'verify_backup', lambda path: (_ for _ in ()).throw(ValueError('bad manifest')))
    result = m.sync_latest(root, 'drive:FinSentinelOffsite', 'age1recipient', make_client_config(tmp_path), remote_client=client)
    assert result['status'] == 'critical'
    assert result['reason'] == 'backup_invalid'
    assert not client.uploaded


def test_remote_directory_allows_safe_nested_folder_but_rejects_traversal(tmp_path, monkeypatch):
    m = module()
    config = make_client_config(tmp_path)

    remote = make_test_remote(m, config, 'drive:FinSentinel/offsite/backups', monkeypatch)

    assert remote.remote_root.endswith('FinSentinel/offsite/backups')
    with pytest.raises(m.OffsiteError, match='configuration_invalid'):
        make_test_remote(m, config, 'drive:FinSentinel/../other', monkeypatch)


def test_readback_command_uses_timeout_without_blocking_pipe_read(tmp_path, monkeypatch):
    m = module()
    config = make_client_config(tmp_path)
    remote = make_test_remote(m, config, 'drive:FinSentinel/offsite', monkeypatch)
    calls = {}

    def timeout_run(argv, **kwargs):
        calls.update(argv=argv, kwargs=kwargs)
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(m.subprocess, 'run', timeout_run)

    with pytest.raises(m.OffsiteError, match='remote_readback_failed'):
        remote.readback_sha256('backup-20261117T120000000000Z-' + 'a'*32 + '.tar.gz.age')

    assert calls['kwargs']['timeout'] == m.TIMEOUT
    assert calls['kwargs']['stdout'] is not subprocess.PIPE


def test_readback_hashes_stream_to_file_without_loading_ciphertext_into_memory(tmp_path, monkeypatch):
    m = module()
    remote = make_test_remote(m, make_client_config(tmp_path), 'drive:FinSentinel/offsite', monkeypatch)

    def write_readback(argv, **kwargs):
        kwargs['stdout'].write(b'ciphertext-bytes')

    monkeypatch.setattr(m.subprocess, 'run', write_readback)

    assert remote.readback_sha256('backup-20261117T120000000000Z-' + 'a'*32 + '.tar.gz.age') == hashlib.sha256(b'ciphertext-bytes').hexdigest()


def test_existing_verified_copy_is_idempotent_without_spare_quota(tmp_path, monkeypatch):
    m = module()
    root, backup = point(tmp_path, monkeypatch)
    monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)
    config = make_client_config(tmp_path)
    name = backup.name + '.tar.gz.age'
    client = FakeRemote(total=1, free=0)
    client.files[name] = b'age-encrypted:opaque-ciphertext'

    digest = hashlib.sha256(b'age-encrypted:opaque-ciphertext').hexdigest()
    result = m.sync_latest(root, 'drive:FinSentinel/offsite', 'age1recipient', config, remote_client=client,
                           expected_backup_id=backup.name, expected_sha256=digest)

    assert result['status'] == 'ok'
    assert client.uploaded == []
    assert client.deleted == []


def test_retention_keeps_verified_current_copy_and_six_newest_others(tmp_path, monkeypatch):
    m = module()
    root, backup = point(tmp_path, monkeypatch)
    monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)
    client = FakeRemote()
    current = backup.name + '.tar.gz.age'
    client.files[current] = b'age-encrypted:opaque-ciphertext'
    for index in range(7):
        day = 20 + index
        client.files[f'backup-202611{day:02d}T120000000000Z-{index:032x}.tar.gz.age'] = b'old'

    digest=hashlib.sha256(b'age-encrypted:opaque-ciphertext').hexdigest()
    result = m.sync_latest(root, 'drive:FinSentinel/offsite', 'age1recipient', make_client_config(tmp_path), remote_client=client,
                           expected_backup_id=backup.name, expected_sha256=digest)

    assert result['status'] == 'ok'
    assert current in client.files
    assert len([name for name in client.files if m.OBJECT_RE.fullmatch(name)]) == 7
    assert len(client.deleted) == 1


def test_existing_copy_without_matching_local_verified_hash_is_not_trusted(tmp_path, monkeypatch):
    m=module()
    root,backup=point(tmp_path,monkeypatch)
    client=FakeRemote()
    name=backup.name+'.tar.gz.age'
    client.files[name]=b'ciphertext-from-unknown-origin'
    monkeypatch.setattr(m,'_encrypt_backup',fake_encrypt)

    result=m.sync_latest(root,'drive:FinSentinel/offsite','age1recipient',make_client_config(tmp_path),remote_client=client)

    assert result['status']=='critical'
    assert result['reason']=='remote_integrity_failed'
    assert client.uploaded==[]
    assert client.deleted==[]


def test_injected_remote_client_does_not_require_production_rclone_config(tmp_path, monkeypatch):
    m=module()
    root,_=point(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'_encrypt_backup',fake_encrypt)

    result=m.sync_latest(root,'drive:FinSentinel/offsite','age1recipient',
                         tmp_path/'root-only-config-not-needed-by-fake-client',
                         remote_client=FakeRemote())

    assert result['status']=='ok'


def test_real_rclone_client_rejects_non_root_owned_config_on_linux(tmp_path):
    import os
    if os.name != 'posix': pytest.skip('POSIX ownership check')
    m=module()
    config=make_client_config(tmp_path)

    with pytest.raises(m.OffsiteError,match='configuration_invalid'):
        m.RcloneRemote(config,'drive:FinSentinel/offsite')


def test_untrusted_remote_and_recipient_are_rejected_without_commands(tmp_path, monkeypatch):
    m = module()
    root, _ = point(tmp_path, monkeypatch)
    client = FakeRemote()
    monkeypatch.setattr(m, '_encrypt_backup', fake_encrypt)
    config = make_client_config(tmp_path)

    remote_result = m.sync_latest(root, 'drive:folder;rm -rf /', 'age1recipient', config, remote_client=client)
    recipient_result = m.sync_latest(root, 'drive:FinSentinelOffsite', 'not-a-recipient', config, remote_client=client)

    assert remote_result['reason'] == 'configuration_invalid'
    assert recipient_result['reason'] == 'configuration_invalid'
    assert not client.uploaded


def make_backup_tar(path, *, unsafe_name=None, tamper=False, malformed_directory=False):
    import json
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


def test_windows_archive_verifier_checks_manifest_and_each_file(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path)
    result=verify_archive(path)
    assert result['files']==2

    make_backup_tar(path,tamper=True)
    with pytest.raises(ValueError,match='file_integrity'):
        verify_archive(path)


def test_windows_archive_verifier_rejects_unsafe_member_paths(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path,unsafe_name='../escape')
    with pytest.raises(ValueError,match='unsafe_archive'):
        verify_archive(path)


def test_windows_archive_verifier_rejects_data_attached_to_directory_members(tmp_path):
    from scripts.verify_offsite_archive import verify_archive
    path=tmp_path/'point.tar.gz'
    make_backup_tar(path,malformed_directory=True)
    with pytest.raises(ValueError,match='unsafe_archive'):
        verify_archive(path)

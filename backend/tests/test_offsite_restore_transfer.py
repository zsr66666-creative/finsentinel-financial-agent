import hashlib
import io
import importlib.util
import json
import tarfile
from types import SimpleNamespace

import pytest


def test_transfer_rejects_bad_ciphertext_before_starting_age_or_ssh(tmp_path, monkeypatch):
    import scripts.offsite_restore_transfer as module

    backup_id = 'backup-20261117T171809010380Z-' + '0e7309931ad844ccb71e42604db43784'
    archive = tmp_path / (backup_id + '.tar.gz.age')
    archive.write_bytes(b'ciphertext')
    index = tmp_path / (archive.name + '.json')
    index.write_text(json.dumps({
        'schema_version': 1,
        'backup_id': backup_id,
        'filename': archive.name,
        'ciphertext_size': archive.stat().st_size,
        'ciphertext_sha256': '0' * 64,
    }))

    monkeypatch.setattr(module.subprocess, 'Popen', lambda *a, **k: pytest.fail('process must not start'))
    with pytest.raises(ValueError, match='ciphertext_integrity_failed'):
        module.send_restore(archive, index, tmp_path/'identity', tmp_path/'key', tmp_path/'known_hosts')


def test_transfer_accepts_matching_ciphertext_and_returns_backup_id(tmp_path):
    from scripts.offsite_restore_transfer import validate_local_copy

    backup_id = 'backup-20261117T171809010380Z-' + '0e7309931ad844ccb71e42604db43784'
    archive = tmp_path / (backup_id + '.tar.gz.age')
    data = b'ciphertext'
    archive.write_bytes(data)
    index = tmp_path / (archive.name + '.json')
    index.write_text(json.dumps({
        'schema_version': 1,
        'backup_id': backup_id,
        'filename': archive.name,
        'ciphertext_size': len(data),
        'ciphertext_sha256': hashlib.sha256(data).hexdigest(),
    }))

    assert validate_local_copy(archive, index) == backup_id


def test_receiver_rejects_archive_id_mismatch_without_restoring(tmp_path):
    from scripts.offsite_restore_receiver import receive_and_restore

    archive = tmp_path / 'wrong.tar.gz'
    archive.write_bytes(b'not an archive')

    def restore(*args, **kwargs):
        pytest.fail('restore must not run for invalid archive')

    result = receive_and_restore(archive, 'backup-20261117T171809010380Z-' + 'a' * 32,
                                 tmp_path / 'staging', restore_runner=restore)
    assert result == {'status': 'critical', 'reason': 'archive_invalid'}
    assert not (tmp_path / 'staging').exists()


def _archive(path, backup_id):
    files = {'database.dump': b'dump bytes', 'config.tar.gz': b'config bytes'}
    manifest = {'schema_version': 1, 'managed_by': 'finsentinel-operations',
                'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                          for name, data in files.items()},
                'artifact_refs': [], 'backup_id': backup_id}
    manifest_bytes = json.dumps(manifest, separators=(',', ':')).encode()
    contents = {**files, 'manifest.json': manifest_bytes,
                'COMPLETE': (hashlib.sha256(manifest_bytes).hexdigest() + '\n').encode()}
    with tarfile.open(path, 'w:gz') as output:
        for name, data in contents.items():
            member = tarfile.TarInfo(f'{backup_id}/{name}')
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))


def test_receiver_restores_matching_archive_and_removes_staging(tmp_path):
    from scripts.offsite_restore_receiver import receive_and_restore

    backup_id = 'backup-20261117T171809010380Z-' + '0e7309931ad844ccb71e42604db43784'
    archive = tmp_path / 'valid.tar.gz'
    staging = tmp_path / 'staging'
    _archive(archive, backup_id)
    calls = []

    def restore_runner(database_url, backup_root, *, restore_database, require_vector):
        calls.append((database_url, backup_root, restore_database, require_vector))
        assert (backup_root / backup_id / 'database.dump').read_bytes() == b'dump bytes'
        return {'status': 'ok', 'reason': 'restore_verified'}

    result = receive_and_restore(archive, backup_id, staging, restore_runner=restore_runner,
        database_url='postgresql://test', backup_verifier=lambda p: {'managed_by': 'finsentinel-operations'})

    assert result == {'status': 'ok', 'reason': 'restore_verified', 'backup_id': backup_id}
    assert calls[0][0] == 'postgresql://test'
    assert calls[0][2].startswith('finsentinel_ops_restore_')
    assert calls[0][3] is True
    assert not staging.exists()


def test_receiver_rejects_valid_archive_for_a_different_id(tmp_path):
    from scripts.offsite_restore_receiver import receive_and_restore

    actual_id = 'backup-20261117T171809010380Z-' + '0e7309931ad844ccb71e42604db43784'
    requested_id = 'backup-20261117T171809010380Z-' + 'a' * 32
    archive = tmp_path / 'valid.tar.gz'
    staging = tmp_path / 'staging'
    _archive(archive, actual_id)

    result = receive_and_restore(archive, requested_id, staging,
        restore_runner=lambda *a, **k: pytest.fail('restore must not run'),
        backup_verifier=lambda p: {'backup_id': actual_id})

    assert result == {'status': 'critical', 'reason': 'backup_id_mismatch'}
    assert not staging.exists()


def test_receiver_loads_archive_verifier_from_its_own_directory(tmp_path):
    repo = __import__('pathlib').Path(__file__).resolve().parents[2]
    standalone = tmp_path / 'standalone'
    standalone.mkdir()
    receiver_path = standalone / 'offsite_restore_receiver.py'
    verifier_path = standalone / 'verify_offsite_archive.py'
    receiver_path.write_bytes((repo / 'scripts/offsite_restore_receiver.py').read_bytes())
    verifier_path.write_bytes((repo / 'scripts/verify_offsite_archive.py').read_bytes())
    spec = importlib.util.spec_from_file_location('standalone_receiver', receiver_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    verifier = module._load_archive_verifier()

    assert verifier.__module__ == 'finsentinel_offsite_archive_verifier'


def test_receiver_reads_database_url_from_unit_even_when_backend_is_stopped(monkeypatch):
    import scripts.offsite_restore_receiver as module

    def systemctl(args, **kwargs):
        assert args == ['systemctl', 'show', 'finsentinel-backend', '-p', 'Environment', '--value']
        return SimpleNamespace(stdout='DATABASE_URL=postgresql+psycopg:///finsentinel?host=/var/run/postgresql')

    assert module._database_url(systemctl) == 'postgresql+psycopg:///finsentinel?host=/var/run/postgresql'


def test_ecs_installer_places_verifier_beside_forced_receiver():
    repo = __import__('pathlib').Path(__file__).resolve().parents[2]
    installer = (repo / 'deploy/ecs/install-offsite-restore-receiver.sh').read_text()

    assert '"$(dirname "$receiver")/verify_offsite_archive.py"' in installer

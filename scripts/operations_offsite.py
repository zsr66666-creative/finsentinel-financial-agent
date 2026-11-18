"""Publish age-encrypted copies of verified local recovery points."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import uuid

from scripts.operations_backup import POINT_RE, safe_path, valid_backups, verify_backup

OBJECT_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\.tar\.gz\.age\Z')
RECIPIENT_RE = re.compile(r'age1[0-9a-z]{8,100}\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
RETENTION = 7
TIMEOUT = 600


class ExportError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _private(path, mode):
    if os.name == 'posix':
        os.chmod(path, mode)


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def _export_lock(root):
    lock_path = root/'.export.lock'
    safe_path(lock_path)
    with lock_path.open('a+b') as stream:
        _private(lock_path, 0o600)
        if os.name == 'posix':
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        else:
            import msvcrt
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b'\0')
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            if os.name == 'posix':
                fcntl.flock(stream, fcntl.LOCK_UN)
            else:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _encrypt_backup(point, recipient, destination):
    """Stream a verified recovery point through tar and age without plaintext staging."""
    tar = None
    age = None
    try:
        tar = subprocess.Popen(
            ['tar', '--create', '--gzip', '--file=-', '--directory', str(point.parent), point.name],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        with Path(destination).open('wb') as encrypted:
            _private(destination, 0o600)
            age = subprocess.Popen(
                ['age', '--encrypt', '--recipient', recipient],
                stdin=tar.stdout, stdout=encrypted, stderr=subprocess.DEVNULL,
            )
            tar.stdout.close()
            age_status = age.wait(timeout=TIMEOUT)
            tar_status = tar.wait(timeout=TIMEOUT)
        if age_status != 0 or tar_status != 0:
            raise ExportError('encryption_failed')
    except ExportError:
        raise
    except Exception as exc:
        for process in (age, tar):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        raise ExportError('encryption_failed') from exc


def _index_path(root, archive_name):
    return root/(archive_name+'.json')


def _read_pair(root, archive_name):
    if not OBJECT_RE.fullmatch(archive_name):
        raise ExportError('export_integrity_failed')
    archive = safe_path(root/archive_name, exists=True)
    index = safe_path(_index_path(root, archive_name), exists=True)
    if archive.is_symlink() or index.is_symlink() or not archive.is_file() or not index.is_file():
        raise ExportError('export_integrity_failed')
    try:
        data = json.loads(index.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        raise ExportError('export_integrity_failed') from None
    expected = {'schema_version', 'backup_id', 'filename', 'ciphertext_size', 'ciphertext_sha256'}
    backup_id = archive_name.removesuffix('.tar.gz.age')
    if (not isinstance(data, dict) or set(data) != expected or data.get('schema_version') != 1
            or data.get('backup_id') != backup_id or data.get('filename') != archive_name
            or type(data.get('ciphertext_size')) is not int or data['ciphertext_size'] <= 0
            or not isinstance(data.get('ciphertext_sha256'), str)
            or not SHA_RE.fullmatch(data['ciphertext_sha256'])):
        raise ExportError('export_integrity_failed')
    if archive.stat().st_size != data['ciphertext_size'] or _sha256(archive) != data['ciphertext_sha256']:
        raise ExportError('export_integrity_failed')
    return data


def _write_new(path, content):
    with path.open('xb') as stream:
        _private(path, 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _verified_pairs(root):
    pairs = []
    for archive in root.iterdir():
        if archive.is_symlink() or not OBJECT_RE.fullmatch(archive.name):
            continue
        try:
            data = _read_pair(root, archive.name)
        except (OSError, ValueError, ExportError):
            continue
        pairs.append((data['backup_id'], archive.name))
    return sorted(pairs)


def _prune(root):
    pairs = _verified_pairs(root)
    for _, archive_name in pairs[:-RETENTION]:
        _read_pair(root, archive_name)
        _index_path(root, archive_name).unlink()
        (root/archive_name).unlink()


def _ensure_export_root(export_root):
    root = Path(export_root).absolute()
    root = safe_path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o755)
    root = safe_path(root, exists=True)
    if not root.is_dir():
        raise ExportError('configuration_invalid')
    if os.name == 'posix':
        info = root.stat()
        expected_owner = 0 if os.geteuid() == 0 else os.geteuid()
        if info.st_uid != expected_owner or info.st_mode & 0o022:
            raise ExportError('configuration_invalid')
        _private(root, 0o755)
    return root


def export_latest(backup_root, export_root, recipient, *, encryptor=None):
    """Publish the newest verified recovery point and prune only verified older pairs."""
    root = None
    temporary = []
    published_archive = None
    published_index = None
    point = None
    stage = 'configuration_invalid'
    try:
        if not isinstance(recipient, str) or not RECIPIENT_RE.fullmatch(recipient):
            raise ExportError('configuration_invalid')
        root = _ensure_export_root(export_root)
        backup_root = safe_path(backup_root, exists=True)
        if not backup_root.is_dir():
            raise ExportError('backup_invalid')
        with _export_lock(root):
            stage = 'backup_invalid'
            points = valid_backups(backup_root)
            if not points:
                raise ExportError('backup_missing')
            point = points[-1]
            verify_backup(point)
            archive_name = point.name+'.tar.gz.age'
            final_archive = root/archive_name
            final_index = _index_path(root, archive_name)
            if final_archive.exists() or final_index.exists():
                data = _read_pair(root, archive_name)
                stage = 'retention_failed'
                _prune(root)
                return {'status':'ok','reason':'export_verified','backup_id':point.name,
                        'ciphertext_sha256':data['ciphertext_sha256'],'ciphertext_size':data['ciphertext_size']}

            nonce = uuid.uuid4().hex
            temp_archive = root/f'.partial-{nonce}.age'
            temp_index = root/f'.partial-{nonce}.json'
            temporary.extend((temp_archive, temp_index))
            stage = 'encryption_failed'
            (encryptor or _encrypt_backup)(point, recipient, temp_archive)
            size = temp_archive.stat().st_size
            if size <= 0:
                raise ExportError('encryption_failed')
            with temp_archive.open('r+b') as stream:
                stream.flush()
                os.fsync(stream.fileno())
            digest = _sha256(temp_archive)
            data = {'schema_version':1,'backup_id':point.name,'filename':archive_name,
                    'ciphertext_size':size,'ciphertext_sha256':digest}
            _write_new(temp_index, (json.dumps(data,sort_keys=True,separators=(',',':'))+'\n').encode())
            _private(temp_archive, 0o644)
            _private(temp_index, 0o644)
            stage = 'export_publish_failed'
            os.replace(temp_archive, final_archive)
            published_archive = final_archive
            os.replace(temp_index, final_index)
            published_index = final_index
            _read_pair(root, archive_name)
            stage = 'retention_failed'
            _prune(root)
            return {'status':'ok','reason':'export_verified','backup_id':point.name,
                    'ciphertext_sha256':digest,'ciphertext_size':size}
    except ExportError as exc:
        reason = exc.reason
    except Exception:
        reason = stage
    finally:
        for path in temporary:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        if published_archive is not None and published_index is None:
            try:
                published_archive.unlink(missing_ok=True)
            except OSError:
                pass
    return {'status':'critical','reason':reason,'backup_id':point.name if point is not None else None}

"""Encrypted, fail-closed copies of verified local recovery points."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from scripts.operations_backup import valid_backups, verify_backup

OBJECT_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\.tar\.gz\.age\Z')
REMOTE_RE = re.compile(r'[A-Za-z0-9_-]{1,32}:[A-Za-z0-9_-]{1,64}(?:/[A-Za-z0-9_-]{1,64})*\Z')
RECIPIENT_RE = re.compile(r'age1[0-9a-z]{8,100}\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
TIMEOUT = 600
RETENTION = 7


class OffsiteError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _safe_config(path):
    path = Path(path).absolute()
    if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
        raise OffsiteError('configuration_invalid')
    if not path.is_file():
        raise OffsiteError('configuration_missing')
    if os.name == 'posix':
        if path.stat().st_uid != 0 or path.stat().st_mode & 0o077:
            raise OffsiteError('configuration_invalid')
    return path


def _run(argv, *, timeout=TIMEOUT, stdout=subprocess.PIPE):
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                              stderr=subprocess.DEVNULL, check=True, timeout=timeout)
    except Exception as exc:
        raise OffsiteError('remote_unavailable') from exc


def _encrypt_backup(point, recipient, destination):
    """Stream a compressed backup through age; plaintext is never staged."""
    tar = None
    age = None
    try:
        tar = subprocess.Popen(
            ['tar', '--create', '--gzip', '--file=-', '--directory', str(point.parent), point.name],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        with Path(destination).open('wb') as encrypted:
            if os.name == 'posix':
                os.chmod(destination, 0o600)
            age = subprocess.Popen(
                ['age', '--encrypt', '--recipient', recipient],
                stdin=tar.stdout, stdout=encrypted, stderr=subprocess.DEVNULL,
            )
            tar.stdout.close()
            age_status = age.wait(timeout=TIMEOUT)
            tar_status = tar.wait(timeout=TIMEOUT)
        if age_status != 0 or tar_status != 0:
            raise OffsiteError('encryption_failed')
    except OffsiteError:
        raise
    except Exception as exc:
        for process in (age, tar):
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=10)
        raise OffsiteError('encryption_failed') from exc


class RcloneRemote:
    def __init__(self, config_path, remote_root):
        self.config_path = _safe_config(config_path)
        if not REMOTE_RE.fullmatch(remote_root):
            raise OffsiteError('configuration_invalid')
        self.remote_root = remote_root

    def _path(self, name):
        if not (OBJECT_RE.fullmatch(name) or re.fullmatch(r'\.partial-[0-9a-f]{32}\.uploading', name)):
            raise OffsiteError('remote_name_invalid')
        return self.remote_root + '/' + name

    def _base(self):
        return ['rclone', '--config', str(self.config_path)]

    def quota(self):
        result = _run(self._base() + ['about', self.remote_root, '--json'])
        try:
            value = json.loads(result.stdout)
            return {key: value[key] for key in ('total', 'used', 'free') if type(value.get(key)) is int}
        except (ValueError, TypeError, KeyError):
            raise OffsiteError('quota_unknown') from None

    def list_objects(self):
        result = _run(self._base() + ['lsjson', self.remote_root, '--files-only', '--max-depth', '1'])
        try:
            rows = json.loads(result.stdout)
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError()
            return [{'name': row['Name'], 'size': row['Size']}
                    for row in rows if isinstance(row, dict)
                    and isinstance(row.get('Name'), str)
                    and type(row.get('Size')) is int and row['Size'] >= 0]
        except (ValueError, TypeError, KeyError):
            raise OffsiteError('remote_listing_invalid') from None

    def upload(self, source, name):
        _run(self._base() + ['copyto', str(source), self._path(name)])

    def readback_sha256(self, name):
        try:
            with tempfile.TemporaryFile(mode='w+b') as output:
                subprocess.run(self._base() + ['cat', self._path(name)],
                               stdin=subprocess.DEVNULL, stdout=output,
                               stderr=subprocess.DEVNULL, check=True, timeout=TIMEOUT)
                output.seek(0)
                digest = hashlib.sha256()
                for block in iter(lambda: output.read(1024 * 1024), b''):
                    digest.update(block)
                return digest.hexdigest()
        except Exception as exc:
            raise OffsiteError('remote_readback_failed') from exc

    def move(self, source, destination):
        _run(self._base() + ['moveto', self._path(source), self._path(destination)])

    def delete(self, name):
        _run(self._base() + ['deletefile', self._path(name)])


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _managed_objects(objects):
    managed = []
    for item in objects:
        name, size = item.get('name'), item.get('size')
        if isinstance(name, str) and OBJECT_RE.fullmatch(name):
            if type(size) is not int or size < 0:
                raise OffsiteError('remote_listing_invalid')
            managed.append((name, size))
    return sorted(managed)


def _quota_preflight(quota, managed, encrypted_size):
    if set(quota) != {'total', 'used', 'free'} or any(type(value) is not int or value < 0 for value in quota.values()):
        raise OffsiteError('quota_unknown')
    if quota['used'] > quota['total'] or quota['free'] != quota['total'] - quota['used']:
        raise OffsiteError('quota_unknown')
    managed_bytes = sum(size for _, size in managed)
    if quota['free'] < encrypted_size or quota['free'] + managed_bytes < encrypted_size * (RETENTION + 1):
        raise OffsiteError('quota_insufficient')


def sync_latest(backup_root, remote, recipient, rclone_config, *, remote_client=None, encryptor=None,
                temp_root=None, expected_backup_id=None, expected_sha256=None):
    """Encrypt and publish the latest valid local point; prune only after readback verification."""
    stage = 'configuration_invalid'
    temp_path = None
    point = None
    try:
        if not REMOTE_RE.fullmatch(remote) or not RECIPIENT_RE.fullmatch(recipient):
            raise OffsiteError('configuration_invalid')
        config_path = _safe_config(rclone_config)
        client = remote_client or RcloneRemote(config_path, remote)
        stage = 'backup_invalid'
        points = valid_backups(backup_root)
        if not points:
            raise OffsiteError('backup_missing')
        point = points[-1]
        verify_backup(point)
        final_name = point.name + '.tar.gz.age'
        objects = client.list_objects()
        managed = _managed_objects(objects)
        if final_name in dict(managed):
            if expected_backup_id != point.name or not isinstance(expected_sha256, str) or not SHA_RE.fullmatch(expected_sha256):
                raise OffsiteError('remote_integrity_failed')
            stage = 'remote_readback_failed'
            if client.readback_sha256(final_name) != expected_sha256:
                raise OffsiteError('remote_integrity_failed')
            digest = expected_sha256
        else:
            stage_root = Path(temp_root or backup_root).absolute()
            if any(part.is_symlink() for part in (stage_root, *stage_root.parents)):
                raise OffsiteError('temporary_path_invalid')
            stage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, name = tempfile.mkstemp(prefix='.offsite-', suffix='.age', dir=stage_root)
            temp_path = Path(name)
            if os.name == 'posix':
                os.chmod(temp_path, 0o600)
            os.close(fd)
            stage = 'encryption_failed'
            (encryptor or _encrypt_backup)(point, recipient, temp_path)
            encrypted_size = temp_path.stat().st_size
            if encrypted_size <= 0:
                raise OffsiteError('encryption_failed')
            digest = _sha256(temp_path)
            stage = 'quota_unknown'
            _quota_preflight(client.quota(), managed, encrypted_size)
            partial_name = '.partial-' + uuid.uuid4().hex + '.uploading'
            stage = 'upload_failed'
            client.upload(temp_path, partial_name)
            stage = 'remote_readback_failed'
            if client.readback_sha256(partial_name) != digest:
                raise OffsiteError('remote_integrity_failed')
            stage = 'remote_publish_failed'
            client.move(partial_name, final_name)

        stage = 'retention_failed'
        refreshed = _managed_objects(client.list_objects())
        keep = {final_name}
        for name, _ in reversed(refreshed):
            if len(keep) >= RETENTION:
                break
            keep.add(name)
        for old_name, _ in refreshed:
            if old_name not in keep:
                client.delete(old_name)
        return {'status': 'ok', 'reason': 'offsite_verified', 'finished_at': datetime.now(timezone.utc).isoformat(),
                'backup_id': point.name, 'ciphertext_sha256': digest}
    except OffsiteError as exc:
        reason = exc.reason
    except Exception:
        reason = stage
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return {'status': 'critical', 'reason': reason, 'finished_at': datetime.now(timezone.utc).isoformat(),
            'backup_id': point.name if point is not None else None}

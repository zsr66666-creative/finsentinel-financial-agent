#!/usr/bin/env python3
"""One-shot forced SSH receiver for an isolated offsite restore drill."""
import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid

BACKUP_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\Z')
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024


def _load_archive_verifier():
    path = Path(__file__).with_name('verify_offsite_archive.py')
    if not path.is_file():
        raise ModuleNotFoundError('bundled archive verifier is missing', name='verify_offsite_archive')
    spec = importlib.util.spec_from_file_location('finsentinel_offsite_archive_verifier', path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError('bundled archive verifier cannot be loaded', name='verify_offsite_archive')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_archive


def _database_url(run=subprocess.run):
    try:
        configured = run(['systemctl', 'show', 'finsentinel-backend', '-p', 'Environment', '--value'],
                         check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, timeout=5).stdout
        for item in shlex.split(configured):
            if item.startswith('DATABASE_URL='):
                value = item.partition('=')[2]
                if value == 'postgresql+psycopg:///finsentinel?host=/var/run/postgresql':
                    return value
                break
    except Exception:
        pass
    raise ValueError('database_configuration_missing')


def _release_root():
    value = subprocess.run(['systemctl', 'show', 'finsentinel-backend', '-p', 'ExecStart', '--value'],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=5).stdout
    match = re.search(r'--app-dir\s+([^ ;}]+)', value)
    if not match:
        raise ValueError('backend_release_missing')
    backend = Path(match.group(1)).resolve()
    if backend.name != 'backend' or not (backend.parent / 'scripts/operations_backup.py').is_file():
        raise ValueError('backend_release_missing')
    return backend.parent


def _extract_verified(archive_path, expected_id, point_root, verifier):
    try:
        result = verifier(archive_path)
        if result.get('backup_id') != expected_id:
            raise ValueError('backup_id_mismatch')
        point = point_root / expected_id
        point.mkdir(mode=0o700)
        unpacked = 0
        with tarfile.open(archive_path, 'r:gz') as archive:
            for member in archive:
                unpacked += member.size
                if unpacked > MAX_UNPACKED_BYTES:
                    raise ValueError('archive_too_large')
                path = PurePosixPath(member.name)
                if path.parts[0] != expected_id:
                    raise ValueError('archive_invalid')
                relative = PurePosixPath(*path.parts[1:])
                target = point.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(mode=0o700, parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError('archive_invalid')
                    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                    fd = os.open(target, flags, 0o600)
                    with os.fdopen(fd, 'wb') as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
        return point
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) in {'backup_id_mismatch', 'archive_too_large'}:
            raise
        raise ValueError('archive_invalid') from None


def receive_and_restore(archive_path, expected_id, staging_root, *,
                        restore_runner=None, database_url=None, verifier=None,
                        backup_verifier=None):
    if not isinstance(expected_id, str) or not BACKUP_RE.fullmatch(expected_id):
        return {'status': 'critical', 'reason': 'backup_id_invalid'}
    archive_path = Path(archive_path)
    staging_root = Path(staging_root)
    try:
        if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError('archive_invalid')
        if staging_root.exists() or staging_root.is_symlink():
            raise ValueError('staging_conflict')
        if verifier is None:
            verifier = _load_archive_verifier()
        if backup_verifier is None:
            from scripts.operations_backup import verify_backup
            backup_verifier = verify_backup
        staging_root.mkdir(mode=0o700, parents=True)
        point = _extract_verified(archive_path, expected_id, staging_root, verifier)
        backup_verifier(point)
        if restore_runner is None:
            from scripts.operations_backup import restore
            restore_runner = restore
        if database_url is None:
            database_url = _database_url()
        database = 'finsentinel_ops_restore_' + uuid.uuid4().hex
        result = restore_runner(database_url, staging_root, restore_database=database,
                                require_vector=True)
        if result.get('status') != 'ok' or result.get('reason') != 'restore_verified':
            reason = result.get('reason')
            if reason not in {'restore_failed', 'restore_cleanup_failed', 'restore_cleanup_pending',
                              'no_valid_backup', 'invalid_reference', 'insufficient_space'}:
                reason = 'restore_failed'
            return {'status': 'critical', 'reason': reason}
        return {'status': 'ok', 'reason': 'restore_verified', 'backup_id': expected_id}
    except ValueError as exc:
        reason = str(exc)
        if reason not in {'archive_invalid', 'archive_too_large', 'backup_id_mismatch', 'staging_conflict',
                          'database_configuration_missing', 'backend_release_missing'}:
            reason = 'restore_failed'
        return {'status': 'critical', 'reason': reason}
    except ModuleNotFoundError:
        return {'status': 'critical', 'reason': 'restore_runtime_missing'}
    except PermissionError:
        return {'status': 'critical', 'reason': 'restore_permission_failed'}
    except subprocess.TimeoutExpired:
        return {'status': 'critical', 'reason': 'restore_timeout'}
    except Exception:
        return {'status': 'critical', 'reason': 'restore_failed'}
    finally:
        if staging_root.exists() and not staging_root.is_symlink():
            shutil.rmtree(staging_root, ignore_errors=True)


def _revoke_key(comment):
    path = Path('/root/.ssh/authorized_keys')
    if path.is_symlink() or not path.is_file():
        raise ValueError('temporary_key_cleanup_failed')
    original = path.read_bytes()
    lines = original.splitlines(keepends=True)
    kept = [line for line in lines if not line.rstrip(b'\r\n').endswith(comment.encode('ascii'))]
    if len(kept) != len(lines) - 1:
        raise ValueError('temporary_key_cleanup_failed')
    temporary = path.with_name('.authorized_keys.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.writelines(kept)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, 0, 0)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup_id')
    parser.add_argument('--inbox', default='/var/lib/finsentinel/restore-drill-inbox')
    args = parser.parse_args(argv)
    if os.geteuid() != 0 or not BACKUP_RE.fullmatch(args.backup_id):
        return 2
    inbox = Path(args.inbox)
    if inbox.is_symlink() or not inbox.is_dir() or inbox.stat().st_uid != 0:
        return 2
    archive_path = inbox / (args.backup_id + '.tar.gz')
    try:
        if os.environ.get('SSH_ORIGINAL_COMMAND') != 'restore ' + args.backup_id:
            raise ValueError('command_invalid')
        if shutil.disk_usage(inbox).free < 3 * 1024 * 1024 * 1024:
            raise ValueError('disk_insufficient')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(archive_path, flags, 0o600)
        total = 0
        with os.fdopen(fd, 'wb') as output:
            while block := sys.stdin.buffer.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError('archive_too_large')
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        release = _release_root()
        sys.path.insert(0, str(release / 'backend'))
        sys.path.insert(0, str(release))
        result = receive_and_restore(archive_path, args.backup_id,
            inbox / ('staging-' + uuid.uuid4().hex))
        if result.get('status') != 'ok':
            raise ValueError(result.get('reason', 'restore_failed'))
        print('offsite_restore: ok restore_verified ' + args.backup_id, flush=True)
        return 0
    except Exception as exc:
        reason = str(exc)
        if reason not in {'archive_too_large', 'temporary_key_cleanup_failed',
                          'restore_runtime_missing', 'restore_permission_failed', 'restore_timeout',
                          'restore_cleanup_failed', 'restore_cleanup_pending', 'no_valid_backup',
                          'invalid_reference', 'insufficient_space', 'database_configuration_missing',
                          'backend_release_missing'}:
            reason = 'restore_failed'
        print('offsite_restore: critical ' + reason, file=sys.stderr, flush=True)
        return 1
    finally:
        archive_path.unlink(missing_ok=True)
        comment = 'finsentinel-restore-drill-' + args.backup_id
        try:
            _revoke_key(comment)
        except Exception:
            print('offsite_restore: critical temporary_key_cleanup_failed', file=sys.stderr, flush=True)


if __name__ == '__main__':
    raise SystemExit(main())

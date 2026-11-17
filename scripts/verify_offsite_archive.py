"""Verify a decrypted recovery archive without extracting untrusted paths."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

BACKUP_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
MAX_ENTRIES = 200_000
MAX_METADATA = 32 * 1024 * 1024
MAX_TOTAL_SIZE = 1024 * 1024**4


def _safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or '..' in path.parts or '\\' in name:
        raise ValueError('unsafe_archive')
    return path


def verify_archive(path):
    files = {}
    metadata = {}
    roots = set()
    seen = set()
    total_size = 0
    try:
        opener = (lambda: tarfile.open(fileobj=path, mode='r|gz')) if hasattr(path, 'read') else (
            lambda: tarfile.open(path, mode='r|gz'))
        with opener() as archive:
            for member in archive:
                if len(seen) >= MAX_ENTRIES or member.name in seen:
                    raise ValueError('unsafe_archive')
                name = _safe_name(member.name)
                roots.add(name.parts[0])
                if not BACKUP_RE.fullmatch(name.parts[0]):
                    raise ValueError('unsafe_archive')
                if member.isdir():
                    if member.size != 0 or name.as_posix() != member.name.rstrip('/'):
                        raise ValueError('unsafe_archive')
                    seen.add(member.name)
                    continue
                if not member.isfile() or len(name.parts) < 2 or name.as_posix() != member.name or member.size < 0:
                    raise ValueError('unsafe_archive')
                relative = PurePosixPath(*name.parts[1:]).as_posix()
                if relative in files:
                    raise ValueError('unsafe_archive')
                total_size += member.size
                if total_size > MAX_TOTAL_SIZE:
                    raise ValueError('archive_too_large')
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError('archive_invalid')
                digest = hashlib.sha256()
                captured = bytearray() if relative in ('manifest.json', 'COMPLETE') else None
                size = 0
                while block := stream.read(1024 * 1024):
                    size += len(block)
                    digest.update(block)
                    if captured is not None:
                        if size > MAX_METADATA:
                            raise ValueError('metadata_too_large')
                        captured.extend(block)
                if size != member.size:
                    raise ValueError('archive_invalid')
                files[relative] = {'sha256': digest.hexdigest(), 'size': size}
                if captured is not None:
                    metadata[relative] = bytes(captured)
                seen.add(member.name)
            while archive.fileobj.read(1024 * 1024):
                pass
            if not getattr(archive.fileobj.cmp, 'eof', False):
                raise tarfile.ReadError('truncated gzip stream')
    except ValueError:
        raise
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise ValueError('archive_invalid') from exc

    if len(roots) != 1 or not {'manifest.json', 'COMPLETE', 'database.dump', 'config.tar.gz'}.issubset(files):
        raise ValueError('incomplete_backup')
    manifest_bytes = metadata['manifest.json']
    try:
        complete = metadata['COMPLETE'].decode('ascii').strip()
    except UnicodeDecodeError as exc:
        raise ValueError('manifest_integrity') from exc
    if complete != hashlib.sha256(manifest_bytes).hexdigest():
        raise ValueError('manifest_integrity')
    try:
        manifest = json.loads(manifest_bytes)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('manifest_invalid') from exc
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1 or manifest.get('managed_by') != 'finsentinel-operations':
        raise ValueError('manifest_invalid')
    expected = manifest.get('files')
    refs = manifest.get('artifact_refs')
    if not isinstance(expected, dict) or not isinstance(refs, list):
        raise ValueError('manifest_invalid')
    if set(files) != set(expected) | {'manifest.json', 'COMPLETE'}:
        raise ValueError('manifest_file_set')
    for name, record in expected.items():
        relative = _safe_name(name)
        if relative.as_posix() != name or len(relative.parts) == 0 or name in ('manifest.json', 'COMPLETE'):
            raise ValueError('unsafe_manifest')
        if not isinstance(record, dict) or type(record.get('size')) is not int or record['size'] < 0 or not isinstance(record.get('sha256'), str) or not SHA_RE.fullmatch(record['sha256']):
            raise ValueError('unsafe_manifest')
        actual = files.get(name)
        if actual is None or actual['size'] != record['size'] or actual['sha256'] != record['sha256']:
            raise ValueError('file_integrity')
    for record in refs:
        if not isinstance(record, dict) or not isinstance(record.get('sha256'), str) or not SHA_RE.fullmatch(record['sha256']):
            raise ValueError('reference_integrity')
        if expected.get('artifacts/' + record['sha256'] + '.pdf', {}).get('sha256') != record['sha256']:
            raise ValueError('reference_integrity')
    return {'backup_id': next(iter(roots)), 'files': len(expected), 'status': 'verified'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    result = verify_archive(parser.parse_args().archive)
    print(json.dumps(result, sort_keys=True))

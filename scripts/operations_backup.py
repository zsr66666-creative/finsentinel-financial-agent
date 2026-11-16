"""Root-owned local recovery points. No backup content is returned to the API.

The caller serializes jobs; the module also locks the backup root on POSIX.
PostgreSQL tools receive connection secrets through environment, never argv.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import select
import tarfile
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

MANAGED_BY = 'finsentinel-operations'
POINT_RE = re.compile(r'backup-\d{8}T\d{12}Z-[0-9a-f]{32}\Z')
RESTORE_RE = re.compile(r'finsentinel_ops_restore_[0-9a-f]{32}\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
TIMEOUT = 600


class MissingOriginal(ValueError):
    def __init__(self, sha):
        self.sha = sha
        super().__init__('missing_original')


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_path(path, *, exists=False):
    """Reject relative paths and symlinks in every existing component."""
    path = Path(path)
    if path == Path(path.anchor):
        raise ValueError('unsafe_path')
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe_path')
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError('unsafe_path')
    if exists and not path.exists():
        raise ValueError('missing_path')
    return path.resolve(strict=exists)


def _private(path, mode):
    if os.name == 'posix':
        os.chmod(path, mode)


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


@contextmanager
def _lock(root):
    root = safe_path(root)
    root.mkdir(parents=True, exist_ok=True, mode=(0o700 if os.name == 'posix' else 0o777))
    _private(root, 0o700)
    lock = root/'.operations.lock'
    safe_path(lock)
    with lock.open('a+b') as stream:
        _private(lock, 0o600)
        if os.name == 'posix':
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield root
        finally:
            if os.name == 'posix':
                fcntl.flock(stream, fcntl.LOCK_UN)


def _run(argv, *, env=None, input=None, stdin=None, stdout=subprocess.PIPE):
    # Capture but never print raw tool output (may contain credentials or rows).
    return subprocess.run(argv, env=env, input=input, stdin=stdin, stdout=stdout,
                          stderr=subprocess.PIPE, check=True, timeout=TIMEOUT)


def _connection(database_url, database=None):
    url = make_url(database_url)
    if url.get_backend_name() != 'postgresql':
        raise ValueError('postgres_required')
    env = os.environ.copy()
    for key in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGSERVICE'):
        env.pop(key, None)
    mapping = {'PGHOST': url.query.get('host') or url.host,
               'PGPORT': url.port, 'PGDATABASE': database or url.database,
               'PGUSER': url.username, 'PGPASSWORD': url.password,
               'PGSSLMODE': url.query.get('sslmode'), 'PGCONNECT_TIMEOUT': '10'}
    env.update({k: str(v) for k,v in mapping.items() if v is not None})
    return url.set(database=database) if database else url, env


def _engine(database_url):
    return create_engine(database_url, connect_args={'connect_timeout': 10},
                         execution_options={'isolation_level': 'REPEATABLE READ'})


def _inventory(conn):
    conn.execute(text("SET LOCAL statement_timeout = '120s'"))
    tables = conn.execute(text("SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') AND schemaname NOT LIKE 'pg_%' ORDER BY 1,2")).all()
    quote = conn.dialect.identifier_preparer.quote
    counts = {f'{s}.{t}': conn.execute(text(f'SELECT count(*) FROM {quote(s)}.{quote(t)}')).scalar_one() for s,t in tables}
    schema = [list(row) for row in conn.execute(text("SELECT table_schema,table_name,column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY table_schema,table_name,ordinal_position"))]
    refs = {}
    def add(sha, path=None):
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise ValueError('invalid_reference')
        record = refs.setdefault(sha, {'sha256': sha, 'paths': []})
        if path and path not in record['paths']:
            record['paths'].append(path)
    if ('public','ingestion_artifacts') in tables:
        for row in conn.execute(text('SELECT sha256, artifact_path FROM ingestion_artifacts')):
            add(row.sha256, row.artifact_path)
    if ('public','document_chunk_embeddings') in tables:
        for row in conn.execute(text("SELECT DISTINCT provenance->>'document_sha256', provenance->>'pdf_sha256' FROM document_chunk_embeddings WHERE provenance IS NOT NULL")):
            sha = row[0] or row[1]
            if sha: add(sha)
            else: raise ValueError('missing_document_reference')
    for record in refs.values():
        record['paths'].sort()
    return {'table_counts': counts, 'schema': schema, 'artifact_refs': sorted(refs.values(), key=lambda x:x['sha256'])}


@contextmanager
def _direct_snapshot(database_url, dump):
    url, env = _connection(database_url)
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            metadata = _inventory(conn)
            size = conn.execute(text('SELECT pg_database_size(current_database())')).scalar_one()
            if shutil.disk_usage(dump.parent).free < size * 2 + 64*1024*1024:
                raise ValueError('insufficient_space')
            snapshot = conn.execute(text('SELECT pg_export_snapshot()')).scalar_one()
            metadata['postgres_version'] = conn.execute(text('SHOW server_version')).scalar_one()
            metadata['database_owner'] = conn.execute(text('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()')).scalar_one()
            _run(['pg_dump','--format=custom','--snapshot',snapshot,'--file',str(dump)], env=env)
            _private(dump, 0o600)
            yield metadata
            conn.rollback()
    finally:
        engine.dispose()



def _root_peer(url):
    return (os.name == 'posix' and os.geteuid() == 0 and not url.password
            and not url.host and url.query.get('host', '/var/run/postgresql') == '/var/run/postgresql')


def _helper_process(database_url, mode):
    url = make_url(database_url).set(username='postgres', password=None)
    process = subprocess.Popen(['sudo','-n','-u','postgres',sys.executable,'-m',
                                'scripts.operations_backup',mode],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=Path(__file__).resolve().parents[1])
    process.stdin.write((url.render_as_string(hide_password=False)+'\n').encode())
    process.stdin.flush()
    ready, _, _ = select.select([process.stdout], [], [], 150)
    if not ready:
        process.kill(); process.wait(timeout=10)
        raise ValueError('database_helper_timeout')
    line = process.stdout.readline(32*1024*1024)
    try:
        metadata = json.loads(line)
    except Exception:
        process.kill(); process.wait(timeout=10)
        raise ValueError('database_helper_failed') from None
    return process, metadata


@contextmanager
def _snapshot(database_url, dump):
    url, env = _connection(database_url)
    if not _root_peer(url):
        with _direct_snapshot(database_url, dump) as metadata:
            yield metadata
        return
    process, metadata = _helper_process(database_url, '--snapshot-helper')
    try:
        if shutil.disk_usage(dump.parent).free < metadata.pop('database_size') * 2 + 64*1024*1024:
            raise ValueError('insufficient_space')
        snapshot = metadata.pop('snapshot')
        with dump.open('xb') as stream:
            _private(dump, 0o600)
            _run(['sudo','-n','-u','postgres','pg_dump','-h','/var/run/postgresql',
                  '-d',url.database,'--format=custom','--snapshot',snapshot], stdout=stream)
        yield metadata
    finally:
        try:
            process.stdin.write(b'finish\n'); process.stdin.flush()
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            process.kill(); process.wait(timeout=10)
        process.stdin.close(); process.stdout.close()


def _restored_inventory(url):
    if _root_peer(url):
        process, metadata = _helper_process(url, '--inventory-helper')
        process.stdin.close(); process.stdout.close()
        if process.wait(timeout=10): raise ValueError('inventory_failed')
        return metadata
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            return _inventory(conn)
    finally:
        engine.dispose()

def _copy_sources(refs, source_root, target):
    source_root = safe_path(source_root, exists=True)
    candidates = None
    for record in refs:
        sha = record['sha256']
        if not SHA_RE.fullmatch(sha): raise ValueError('invalid_reference')
        blob = source_root/'blobs'/(sha+'.pdf')
        if not blob.exists():
            # Legacy source PDFs may predate content-addressed worker blobs.
            if candidates is None:
                candidates = {}
                for candidate in source_root.rglob('*.pdf'):
                    candidate = safe_path(candidate, exists=True)
                    if not candidate.is_relative_to(source_root): raise ValueError('unsafe_path')
                    candidates.setdefault(_hash(candidate), candidate)
            blob = candidates.get(sha)
        if blob is None: raise MissingOriginal(sha)
        blob = safe_path(blob, exists=True)
        if not blob.is_relative_to(source_root) or _hash(blob) != sha:
            raise ValueError('original_hash_mismatch')
        if shutil.disk_usage(target).free < blob.stat().st_size + 64*1024*1024:
            raise ValueError('insufficient_space')
        destination = target/'artifacts'/(sha+'.pdf')
        destination.parent.mkdir(mode=(0o700 if os.name == 'posix' else 0o777), exist_ok=True)
        shutil.copyfile(blob, destination); _private(destination, 0o600)
        if _hash(destination) != sha or _hash(blob) != sha:
            raise ValueError('original_changed')
        for index, raw in enumerate(record.get('paths', [])):
            parsed = safe_path(raw, exists=True)
            if not parsed.is_relative_to(source_root): raise ValueError('unsafe_path')
            data = json.loads(parsed.read_text(encoding='utf-8'))
            if data.get('sha256') != sha: raise ValueError('metadata_hash_mismatch')
            dest = target/'artifacts'/f'{sha}-{index}.json'
            before = _hash(parsed)
            shutil.copyfile(parsed, dest); _private(dest, 0o600)
            if _hash(dest) != before or _hash(parsed) != before:
                raise ValueError('metadata_changed')


def _write_json(path, data):
    with path.open('x', encoding='utf-8') as stream:
        _private(path, 0o600)
        json.dump(data, stream, ensure_ascii=False, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())


def verify_backup(point):
    point = safe_path(point, exists=True)
    if not POINT_RE.fullmatch(point.name) or not point.is_dir(): raise ValueError('invalid_backup')
    for path in point.rglob('*'): safe_path(path, exists=True)
    complete = point/'COMPLETE'; manifest_path = point/'manifest.json'
    if not complete.is_file() or not manifest_path.is_file(): raise ValueError('incomplete_backup')
    if complete.read_text(encoding='ascii').strip() != _hash(manifest_path):
        raise ValueError('manifest_integrity')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('managed_by') != MANAGED_BY:
        raise ValueError('unmanaged_backup')
    files = manifest['files']
    if 'database.dump' not in files or 'config.tar.gz' not in files:
        raise ValueError('incomplete_backup')
    actual = {p.relative_to(point).as_posix() for p in point.rglob('*') if p.is_file()} - {'manifest.json','COMPLETE'}
    if actual != set(files): raise ValueError('manifest_file_set')
    for name, info in files.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name:
            raise ValueError('unsafe_manifest')
        path = safe_path(point.joinpath(*relative.parts), exists=True)
        if not path.is_relative_to(point) or not path.is_file() or path.stat().st_size != info['size'] or _hash(path) != info['sha256']:
            raise ValueError('file_integrity')
    for record in manifest['artifact_refs']:
        sha = record['sha256']
        if not SHA_RE.fullmatch(sha) or files.get('artifacts/'+sha+'.pdf', {}).get('sha256') != sha:
            raise ValueError('reference_integrity')
    return manifest


def valid_backups(backup_root):
    root = safe_path(backup_root)
    if not root.exists(): return []
    valid = []
    for point in root.iterdir():
        if not POINT_RE.fullmatch(point.name): continue
        try: verify_backup(point)
        except (OSError, ValueError, KeyError, TypeError): continue
        valid.append(point)
    return sorted(valid, key=lambda path:path.name)


def _prune(root):
    for point in valid_backups(root)[:-7]:
        # Revalidate immediately before deleting, under the exclusive job lock.
        checked = safe_path(point, exists=True)
        if checked.parent != root or not POINT_RE.fullmatch(checked.name): raise ValueError('unsafe_cleanup')
        verify_backup(checked)
        shutil.rmtree(checked)



@contextmanager
def _staging(root):
    """Delete only this invocation's temporary tree, while holding the job lock."""
    path = root/('.partial-'+uuid4().hex)
    path.mkdir(mode=(0o700 if os.name == 'posix' else 0o777))
    identity = path.stat()
    try:
        yield path
    finally:
        if path.exists() or path.is_symlink():
            checked = safe_path(path, exists=True)
            current = checked.stat()
            if (checked.parent != root or not re.fullmatch(r'\.partial-[0-9a-f]{32}', checked.name)
                    or (current.st_dev,current.st_ino) != (identity.st_dev,identity.st_ino)):
                raise ValueError('unsafe_temporary_cleanup')
            for child in checked.rglob('*'):
                safe_path(child, exists=True)
            shutil.rmtree(checked)

def backup(database_url, backup_root, artifact_root, config_paths=(), source_revision='unknown'):
    point_id = 'backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid4().hex
    try:
        with _lock(backup_root) as root:
            safe_path(artifact_root, exists=True)
            if shutil.disk_usage(root).free < 64*1024*1024: raise ValueError('insufficient_space')
            with _staging(root) as staging:
                with _snapshot(database_url, staging/'database.dump') as metadata:
                    _copy_sources(metadata['artifact_refs'], artifact_root, staging)
                    with tarfile.open(staging/'config.tar.gz', 'w:gz') as archive:
                        _private(staging/'config.tar.gz', 0o600)
                        for index, raw in enumerate(config_paths):
                            config = safe_path(raw, exists=True)
                            if not config.is_file(): raise ValueError('config_file_required')
                            # Explicit regular files only; no repository/directory recursion.
                            archive.add(config, arcname=f'{index:04d}-{config.name}', recursive=False)
                files = {p.relative_to(staging).as_posix(): {'sha256':_hash(p),'size':p.stat().st_size}
                         for p in staging.rglob('*') if p.is_file()}
                manifest = dict(schema_version=1, managed_by=MANAGED_BY, created_at=now(),
                                source_revision=source_revision, **metadata, files=files)
                _write_json(staging/'manifest.json', manifest)
                complete = staging/'COMPLETE'; complete.write_text(_hash(staging/'manifest.json')+'\n', encoding='ascii')
                _private(complete, 0o600)
                # Validate under a valid managed name before publishing into the root.
                validation = staging/point_id; validation.mkdir(mode=(0o700 if os.name == 'posix' else 0o777))
                for path in list(staging.iterdir()):
                    if path != validation: path.rename(validation/path.name)
                verify_backup(validation)
                destination = root/point_id
                validation.rename(destination)
                staging.rmdir()
                _prune(root)
        return {'status':'ok','finished_at':now(),'backup_id':point_id,'reason':'backup_verified'}
    except MissingOriginal as exc:
        return {'status':'critical','finished_at':now(),'reason':'missing_original','missing_sha256':exc.sha}
    except Exception:
        # Do not prune or publish an incomplete point. Current temporary files
        # are removed under lock; callers receive no exception/log contents.
        return {'status':'critical','finished_at':now(),'reason':'backup_failed'}


def _admin(database_url, sql):
    url, env = _connection(database_url)
    if url.host or url.query.get('host', '/var/run/postgresql') != '/var/run/postgresql':
        raise ValueError('local_admin_only')
    env.pop('PGUSER', None); env.pop('PGPASSWORD', None)
    env['PGDATABASE'] = 'postgres'; env['PGHOST'] = '/var/run/postgresql'
    _run(['sudo','-n','-u','postgres','psql','-X','--no-psqlrc','-v','ON_ERROR_STOP=1','-d','postgres'],
         env=env, input=sql.encode())


def restore(database_url, backup_root, *, restore_database=None, admin_runner=None, require_vector=True):
    created = False; cleanup_failed = False; result = None; marker = None
    database = restore_database or 'finsentinel_ops_restore_'+uuid4().hex
    admin = admin_runner or (lambda sql: _admin(database_url, sql))
    try:
        url, env = _connection(database_url, database)
        if not RESTORE_RE.fullmatch(database) or database == make_url(database_url).database:
            raise ValueError('unsafe_restore_database')
        # Explicit source URL user is required; never create a superuser-owned app DB.
        role = make_url(database_url).username
        with _lock(backup_root) as root:
            points = valid_backups(root)
            if not points: raise ValueError('no_valid_backup')
            point = points[-1]; manifest = verify_backup(point)
            role = role or manifest.get('database_owner')
            if not role or not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]{0,62}', role):
                raise ValueError('explicit_application_role_required')
            marker = root/'.restore-pending.json'
            safe_path(marker)
            if marker.exists():
                marker = None
                raise ValueError('restore_cleanup_pending')
            _write_json(marker, {'database':database,'managed_by':MANAGED_BY,'created_at':now()})
            # No IF NOT EXISTS: successful create proves this invocation owns it.
            admin(f'CREATE DATABASE "{database}" OWNER "{role}";')
            created = True
            if require_vector:
                # psql meta-command connects only to our generated, validated name.
                admin(f'\\connect {database}\nCREATE EXTENSION IF NOT EXISTS vector;')
            argv = ['pg_restore','--dbname',database,'--exit-on-error','--no-owner','--no-privileges','--no-comments']
            if _root_peer(url):
                argv = ['sudo','-n','-u',role,'env','PGHOST=/var/run/postgresql',
                        'PGDATABASE='+database,*argv]
            with (point/'database.dump').open('rb') as stream:
                _run(argv, env=env, stdin=stream)
            actual = _restored_inventory(url)
            for key in ('table_counts','schema','artifact_refs'):
                if actual[key] != manifest[key]: raise ValueError('restore_inventory_mismatch')
            result = {'status':'ok','finished_at':now(),'backup_id':point.name,'reason':'restore_verified'}
    except Exception:
        result = {'status':'critical','finished_at':now(),'reason':'restore_failed'}
    finally:
        if created:
            try:
                # Cleanup only this invocation's successfully created, exact name.
                admin(f'DROP DATABASE "{database}";')
            except Exception:
                cleanup_failed = True
        if marker is not None and not cleanup_failed:
            try:
                marker.unlink(missing_ok=True)
            except OSError:
                cleanup_failed = True
        if cleanup_failed:
            result = {'status':'critical','finished_at':now(),'reason':'restore_cleanup_failed'}
    return result


def _database_helper(mode):
    """Private root-to-postgres pipe protocol; never emits rows or credentials."""
    url = sys.stdin.buffer.readline(16384).decode().strip()
    engine = _engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            metadata = _inventory(conn)
            if mode == '--snapshot-helper':
                metadata.update(snapshot=conn.execute(text('SELECT pg_export_snapshot()')).scalar_one(),
                    database_size=conn.execute(text('SELECT pg_database_size(current_database())')).scalar_one(),
                    database_owner=conn.execute(text('SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()')).scalar_one(),
                    postgres_version=conn.execute(text('SHOW server_version')).scalar_one())
            print(json.dumps(metadata), flush=True)
            if mode == '--snapshot-helper':
                if not select.select([sys.stdin.buffer], [], [], TIMEOUT)[0]:
                    raise ValueError('snapshot_helper_timeout')
                sys.stdin.buffer.readline(100)
            conn.rollback()
    finally:
        engine.dispose()


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] in ('--snapshot-helper','--inventory-helper'):
        try:
            _database_helper(sys.argv[1])
        except Exception:
            sys.exit(1)
    else:
        sys.exit('private helper only; use scripts.operations_runner')

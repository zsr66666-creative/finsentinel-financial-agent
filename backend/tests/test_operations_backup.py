import hashlib
import importlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest


def module():
    return importlib.import_module('scripts.operations_backup')


def fake_snapshot(monkeypatch, refs=(), counts=None):
    m = module()
    @contextmanager
    def snapshot(url, dump):
        dump.write_bytes(b'custom pg dump')
        yield {'table_counts': counts or {'accounts': 2}, 'schema': [['public','accounts','id','integer','NO']],
               'artifact_refs': list(refs), 'postgres_version': 'test'}
    monkeypatch.setattr(m, '_snapshot', snapshot)
    return m


def test_requires_absolute_root(tmp_path):
    result = module().backup('postgresql:///secret', Path('relative'), tmp_path)
    assert result['status'] == 'critical'
    assert 'secret' not in json.dumps(result)


def test_success_retains_only_seven_complete_managed_points(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    root = tmp_path/'backup'
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    unknown = root/'unknown'; unknown.mkdir(parents=True)
    for _ in range(9):
        assert m.backup('postgresql:///test', root, artifacts)['status'] == 'ok'
    assert len(m.valid_backups(root)) == 7
    assert unknown.is_dir()
    assert all(m.verify_backup(p)['schema_version'] == 1 for p in m.valid_backups(root))


def test_failed_backup_never_prunes(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    root = tmp_path/'backup'; artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    for _ in range(7):
        assert m.backup('postgresql:///test', root, artifacts)['status'] == 'ok'
    @contextmanager
    def failed(url, dump):
        raise ValueError('password=sensitive')
        yield
    monkeypatch.setattr(m, '_snapshot', failed)
    result = m.backup('postgresql:///test', root, artifacts)
    assert result['status'] == 'critical'
    assert 'sensitive' not in json.dumps(result)
    assert len(m.valid_backups(root)) == 7


def test_reference_hash_and_manifest_integrity(tmp_path, monkeypatch):
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    pdf = artifacts/'source.pdf'; pdf.write_bytes(b'%PDF source')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    m = fake_snapshot(monkeypatch, [{'sha256': digest, 'paths': []}])
    result = m.backup('postgresql:///test', tmp_path/'backup', artifacts)
    assert result['status'] == 'ok'
    point = m.valid_backups(tmp_path/'backup')[0]
    assert (point/'artifacts'/f'{digest}.pdf').read_bytes() == pdf.read_bytes()
    (point/'database.dump').write_bytes(b'tampered')
    with pytest.raises(ValueError): m.verify_backup(point)
    assert m.valid_backups(tmp_path/'backup') == []


def test_missing_reference_fails_without_complete(tmp_path, monkeypatch):
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    m = fake_snapshot(monkeypatch, [{'sha256': 'a'*64, 'paths': []}])
    assert m.backup('postgresql:///test', tmp_path/'backup', artifacts)['status'] == 'critical'
    assert m.valid_backups(tmp_path/'backup') == []


def test_symlink_root_rejected(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    target = tmp_path/'actual'; target.mkdir()
    link = tmp_path/'linked'
    try: link.symlink_to(target, target_is_directory=True)
    except OSError: pytest.skip('symlinks unavailable')
    assert m.backup('postgresql:///test', link, target)['status'] == 'critical'


def test_restore_rejects_production_before_any_commands(tmp_path, monkeypatch):
    m = module()
    assert m.restore('postgresql:///production', tmp_path, restore_database='production')['status'] == 'critical'


def test_config_is_restricted_archive_and_no_link_following(tmp_path, monkeypatch):
    import tarfile
    m = fake_snapshot(monkeypatch)
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    config = tmp_path/'app.env'; config.write_text('DATABASE_URL=private')
    root = tmp_path/'backup'
    result = m.backup('postgresql:///test', root, artifacts, [config])
    assert result['status'] == 'ok' and 'private' not in json.dumps(result)
    point = m.valid_backups(root)[0]
    with tarfile.open(point/'config.tar.gz') as archive:
        assert archive.extractfile('0000-app.env').read() == b'DATABASE_URL=private'
    if os.name != 'nt':
        assert point.stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in point.rglob('*') if p.is_file())

def test_restore_roundtrip_contract_and_cleanup(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    root = tmp_path/'backup'
    assert m.backup('postgresql://app@/source', root, artifacts)['status'] == 'ok'
    commands = []; admin = []
    monkeypatch.setattr(m, '_run', lambda argv, **kw: commands.append((argv,kw)))
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, *args): pass
    class Engine:
        def connect(self): return Connection()
        def dispose(self): pass
    monkeypatch.setattr(m, '_engine', lambda url: Engine())
    monkeypatch.setattr(m, '_inventory', lambda conn: {'table_counts': {'accounts':2}, 'schema': [['public','accounts','id','integer','NO']], 'artifact_refs': []})
    result = m.restore('postgresql://app@/source', root, admin_runner=admin.append)
    assert result['status'] == 'ok'
    assert admin[0].startswith('CREATE DATABASE "finsentinel_ops_restore_')
    assert 'CREATE EXTENSION' in admin[1]
    assert admin[2].startswith('DROP DATABASE "finsentinel_ops_restore_')
    assert '--no-owner' in commands[0][0] and '--no-comments' in commands[0][0]


def test_preexisting_database_is_never_dropped(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    artifacts = tmp_path/'artifacts'; artifacts.mkdir(); root = tmp_path/'backup'
    assert m.backup('postgresql://app@/source', root, artifacts)['status'] == 'ok'
    commands = []
    def fail_create(sql):
        commands.append(sql)
        raise RuntimeError('already exists')
    assert m.restore('postgresql://app@/source', root, admin_runner=fail_create)['status'] == 'critical'
    assert len(commands) == 1 and commands[0].startswith('CREATE DATABASE')


def test_unclean_restore_blocks_new_databases(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    artifacts = tmp_path/'artifacts'; artifacts.mkdir(); root = tmp_path/'backup'
    assert m.backup('postgresql://app@/source', root, artifacts)['status'] == 'ok'
    admin = []
    def commands(sql):
        admin.append(sql)
        if sql.startswith('DROP'): raise RuntimeError('cannot drop')
    monkeypatch.setattr(m, '_run', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('restore failed')))
    assert m.restore('postgresql://app@/source', root, admin_runner=commands)['reason'] == 'restore_cleanup_failed'
    count = len(admin)
    assert m.restore('postgresql://app@/source', root, admin_runner=commands)['status'] == 'critical'
    assert len(admin) == count


def test_manifest_cannot_reference_outside_point(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    artifacts = tmp_path/'artifacts'; artifacts.mkdir(); root = tmp_path/'backup'
    assert m.backup('postgresql:///test', root, artifacts)['status'] == 'ok'
    point = m.valid_backups(root)[0]
    manifest_path = point/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['files']['../external'] = {'sha256': 'a'*64, 'size': 1}
    manifest_path.write_text(json.dumps(manifest))
    (point/'COMPLETE').write_text(hashlib.sha256(manifest_path.read_bytes()).hexdigest())
    with pytest.raises(ValueError): m.verify_backup(point)

def test_missing_original_reports_only_safe_sha(tmp_path, monkeypatch):
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    m = fake_snapshot(monkeypatch, [{'sha256': 'b'*64, 'paths': []}])
    result = m.backup('postgresql://user:password@host/db', tmp_path/'backup', artifacts)
    assert result['reason'] == 'missing_original'
    assert result['missing_sha256'] == 'b'*64
    assert 'password' not in json.dumps(result)


@pytest.mark.skipif(not os.environ.get('OPERATIONS_TEST_DATABASE_URL'), reason='isolated PostgreSQL service required')
def test_postgresql_real_snapshot_and_restore_roundtrip(tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from uuid import uuid4
    m = module()
    base = make_url(os.environ['OPERATIONS_TEST_DATABASE_URL'])
    admin_engine = create_engine(base, isolation_level='AUTOCOMMIT')
    source_db = 'finsentinel_ops_fixture_'+uuid4().hex
    source_url = base.set(database=source_db)
    artifacts = tmp_path/'artifacts'; (artifacts/'blobs').mkdir(parents=True)
    pdf = b'%PDF-1.4 isolated original test'
    sha = hashlib.sha256(pdf).hexdigest()
    (artifacts/'blobs'/(sha+'.pdf')).write_bytes(pdf)
    parsed = artifacts/'parsed.json'; parsed.write_text(json.dumps({'sha256':sha,'pages':[]}))
    def admin(sql):
        with admin_engine.connect() as conn: conn.execute(text(sql))
    engine = None; source_created = False
    try:
        admin(f'CREATE DATABASE "{source_db}"')
        source_created = True
        engine = create_engine(source_url)
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE accounts (id integer PRIMARY KEY, name text)'))
            conn.execute(text("INSERT INTO accounts VALUES (1,'fixture')"))
            conn.execute(text('CREATE TABLE review_decisions (id integer PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE ingestion_artifacts (sha256 text NOT NULL, artifact_path text NOT NULL)'))
            conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:sha,:path)'), {'sha':sha,'path':str(parsed)})
            conn.execute(text('CREATE TABLE document_chunk_embeddings (id integer PRIMARY KEY, provenance jsonb NOT NULL)'))
            conn.execute(text('INSERT INTO document_chunk_embeddings VALUES (1,CAST(:p AS jsonb))'), {'p':json.dumps({'document_sha256':sha})})
        root = tmp_path/'backup'
        assert m.backup(source_url, root, artifacts)['status'] == 'ok'
        manifest = m.verify_backup(m.valid_backups(root)[0])
        # A committed change after the recovery point must not alter expected counts.
        with engine.begin() as conn: conn.execute(text("INSERT INTO accounts VALUES (2,'later')"))
        assert manifest['table_counts']['public.accounts'] == 1
        result = m.restore(source_url, root, admin_runner=admin, require_vector=False)
        assert result['status'] == 'ok'
        with admin_engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM pg_database WHERE datname LIKE 'finsentinel_ops_restore_%'")).scalar_one() == 0
    finally:
        if engine: engine.dispose()
        if source_created: admin(f'DROP DATABASE "{source_db}"')
        admin_engine.dispose()

def test_root_peer_dump_keeps_backup_files_root_owned(tmp_path, monkeypatch):
    from sqlalchemy.engine import make_url
    m = module()
    writes = []; commands = []
    class Pipe:
        def write(self, data): writes.append(data)
        def flush(self): pass
        def close(self): pass
    class Process:
        stdin = Pipe(); stdout = Pipe()
        def wait(self, **kwargs): return 0
    monkeypatch.setattr(m, '_root_peer', lambda url: True)
    monkeypatch.setattr(m, '_helper_process', lambda url, mode: (Process(), {
        'snapshot':'000003-1','database_size':1,'table_counts':{},'schema':[],
        'artifact_refs':[],'database_owner':'finsentinel'}))
    def run(argv, **kwargs):
        commands.append(argv)
        kwargs['stdout'].write(b'dump')
    monkeypatch.setattr(m, '_run', run)
    dump = tmp_path/'root-only.dump'
    with m._snapshot('postgresql+psycopg:///finsentinel?host=/var/run/postgresql', dump) as metadata:
        assert metadata['database_owner'] == 'finsentinel'
        assert 'snapshot' not in metadata
    assert dump.read_bytes() == b'dump'
    assert commands[0][:5] == ['sudo','-n','-u','postgres','pg_dump']
    assert str(dump) not in commands[0]
    assert writes == [b'finish\n']


def test_reference_parsed_metadata_is_required_and_copied(tmp_path, monkeypatch):
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    pdf = artifacts/'file.pdf'; pdf.write_bytes(b'%PDF fixture')
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    parsed = artifacts/'parsed.json'; parsed.write_text(json.dumps({'sha256':sha,'pages':[]}))
    m = fake_snapshot(monkeypatch, [{'sha256':sha,'paths':[str(parsed)]}])
    root = tmp_path/'backup'
    assert m.backup('postgresql:///fixture', root, artifacts)['status'] == 'ok'
    point = m.valid_backups(root)[0]
    assert json.loads((point/'artifacts'/(sha+'-0.json')).read_text())['sha256'] == sha
    parsed.write_text(json.dumps({'sha256':'a'*64}))
    assert m.backup('postgresql:///fixture', root, artifacts)['status'] == 'critical'
    assert len(m.valid_backups(root)) == 1


def test_unknown_and_incomplete_backup_names_never_pruned(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch)
    artifacts = tmp_path/'artifacts'; artifacts.mkdir(); root = tmp_path/'backup'; root.mkdir()
    incomplete = root/'backup-20260101T010101000000Z-00000000000000000000000000000000'
    incomplete.mkdir(); (incomplete/'precious').write_text('retain')
    for _ in range(8): assert m.backup('postgresql:///fixture', root, artifacts)['status'] == 'ok'
    assert (incomplete/'precious').read_text() == 'retain'
    assert len(m.valid_backups(root)) == 7

def test_failed_backup_removes_only_its_partial_directory(tmp_path, monkeypatch):
    m = fake_snapshot(monkeypatch, [{'sha256':'c'*64,'paths':[]}])
    root = tmp_path/'backup'; root.mkdir()
    artifacts = tmp_path/'artifacts'; artifacts.mkdir()
    unknown = root/'.partial-unknown-existing'; unknown.mkdir()
    (unknown/'keep').write_text('untouched')
    assert m.backup('postgresql:///fixture', root, artifacts)['status'] == 'critical'
    assert list(root.glob('.partial-*')) == [unknown]
    assert (unknown/'keep').read_text() == 'untouched'

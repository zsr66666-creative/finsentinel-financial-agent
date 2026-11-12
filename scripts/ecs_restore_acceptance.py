"""Read production under exported snapshot; restore ONLY into explicit test DB."""
import argparse
import json
from pathlib import Path
import subprocess
from sqlalchemy import create_engine,text

def counts(conn):
    names=conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
    return {name:conn.execute(text('SELECT count(*) FROM public."'+name.replace('"','""')+'"')).scalar_one() for name in names}

def main():
    p=argparse.ArgumentParser();p.add_argument('--restore-db',required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    if not args.restore_db.startswith('finsentinel_restore_test_') or not args.restore_db.replace('_','').isalnum():
        raise ValueError('dedicated restore test database required')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    dump=args.output_dir/'production-snapshot.dump'
    source=create_engine('postgresql+psycopg:///finsentinel?host=/var/run/postgresql')
    with source.connect().execution_options(isolation_level='REPEATABLE READ') as c:
        c.execute(text('SET TRANSACTION READ ONLY'))
        snapshot=c.execute(text('SELECT pg_export_snapshot()')).scalar_one()
        expected=counts(c)
        subprocess.run(['pg_dump','-h','/var/run/postgresql','-d','finsentinel','-Fc','--snapshot',snapshot,'-f',str(dump)],check=True,timeout=300)
        c.rollback()
    source.dispose()
    # vector is pre-created by postgres; application role cannot COMMENT on it.
    # Comments are outside this schema/data restore acceptance contract.
    subprocess.run(['pg_restore','--exit-on-error','--no-owner','--no-privileges','--no-comments','-h','/var/run/postgresql','-d',args.restore_db,str(dump)],check=True,timeout=300)
    restored=create_engine('postgresql+psycopg:///'+args.restore_db+'?host=/var/run/postgresql')
    with restored.connect() as c:
        actual=counts(c)
        version=c.execute(text('SELECT version()')).scalar_one()
    restored.dispose()
    assert expected==actual, 'restored table counts differ from exported production snapshot'
    report=dict(status='passed',restore_database=args.restore_db,postgres_version=version,
        snapshot_table_counts=expected,restored_table_counts=actual,
        limitations=['table-count/schema restore check, not full row checksum or application recovery',
            'production read only; test database retained for inspection'])
    (args.output_dir/'restore-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()

"""Explicit additive saved reports schema management."""
import argparse
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy import create_engine
from app.saved_reports import migrate_saved_reports,check_saved_reports

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['migrate','check']);args=parser.parse_args()
    url=os.environ.get('DATABASE_URL')
    if not url:parser.error('DATABASE_URL required')
    engine=create_engine(url)
    try:
        (migrate_saved_reports if args.command=='migrate' else check_saved_reports)(engine)
        print('Saved reports schema ready');return 0
    except Exception as exc:
        print('Saved reports command failed: '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__),file=sys.stderr);return 1
    finally:engine.dispose()
if __name__=='__main__':raise SystemExit(main())

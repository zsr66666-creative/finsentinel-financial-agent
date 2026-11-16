"""Explicit additive research library schema management."""
import argparse
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy import create_engine
from app.personal_research import migrate_research_library,check_research_library

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['migrate','check']);args=parser.parse_args()
    url=os.environ.get('DATABASE_URL')
    if not url:parser.error('DATABASE_URL required')
    engine=create_engine(url)
    try:
        (migrate_research_library if args.command=='migrate' else check_research_library)(engine)
        print('Research library schema ready');return 0
    except Exception as exc:
        print('Research library command failed: '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__),file=sys.stderr);return 1
    finally:engine.dispose()
if __name__=='__main__':raise SystemExit(main())

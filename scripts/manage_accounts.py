"""Interactive account migration and bootstrap. Never accepts passwords as arguments."""
import argparse
import getpass
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy import create_engine,select,func
from app.auth.service import Accounts,migrate_accounts,users

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['migrate','bootstrap','check','reset-admin']);args=parser.parse_args()
    url=os.environ.get('DATABASE_URL')
    if not url:parser.error('DATABASE_URL required')
    engine=create_engine(url);service=Accounts(engine)
    try:
        if args.command=='migrate':migrate_accounts(engine);print('Account migration ready');return 0
        with engine.connect() as c:active=c.execute(select(func.count()).select_from(users).where(users.c.role=='admin',users.c.enabled==True)).scalar()
        if args.command=='check':return 0 if active else 1
        if args.command=='bootstrap' and active:print('Active administrator already exists');return 0
        if not sys.stdin.isatty():parser.error('bootstrap requires interactive terminal')
        username=input('Administrator username: ').strip()
        if args.command=='reset-admin':
            with engine.connect() as c:existing=c.execute(select(users).where(users.c.username==username,users.c.role=='admin')).mappings().first()
            if not existing:raise ValueError('administrator_not_found')
            nickname=existing['nickname']
        else:nickname=input('Administrator nickname: ').strip()
        password=getpass.getpass('Temporary password (12-128 characters): ')
        if password!=getpass.getpass('Confirm temporary password: '):raise ValueError('password_mismatch')
        if args.command=='reset-admin':
            service.update_user(existing['id'],{'password':password,'enabled':True},None)
            print('Administrator password reset; sessions revoked; rotation required');return 0
        created=service.create_user(username,password,'admin',nickname,bootstrap_only=True)
        if created is None:print('Active administrator already exists');return 0
        print('Administrator created; password rotation required on first login');return 0
    except Exception as exc:
        print('Account command failed: '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__),file=sys.stderr);return 1
    finally:engine.dispose()
if __name__=='__main__':raise SystemExit(main())

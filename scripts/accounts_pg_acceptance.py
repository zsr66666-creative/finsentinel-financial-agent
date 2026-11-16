"""Exercise account concurrency in an isolated PostgreSQL schema, not production users."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4
from sqlalchemy import create_engine, inspect, text
from app.auth.service import Accounts, migrate_accounts


def accept(engine):
    if engine.dialect.name != 'postgresql':
        raise ValueError('PostgreSQL required')

    def counts():
        with engine.connect() as connection:
            names = inspect(connection).get_table_names()
            return {name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
                    for name in ('account_users', 'financial_reviews', 'document_chunk_embeddings') if name in names}

    before = counts()
    schema = 'accounts_accept_' + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = create_engine(engine.url, connect_args={'options': '-csearch_path=' + schema})
    replay = None
    try:
        assert migrate_accounts(isolated) == ['006_accounts']
        assert migrate_accounts(isolated) == []
        service = Accounts(isolated)
        password = secrets.token_urlsafe(24)
        first = service.create_user('isolated_admin_one', password, 'admin', 'Isolated admin one')
        second = service.create_user('isolated_admin_two', password, 'admin', 'Isolated admin two', first['id'])

        def disable(user):
            try:
                service.update_user(user['id'], {'enabled': False}, first['id'])
                return 'disabled'
            except ValueError as exc:
                assert str(exc) == 'last_admin'
                return 'protected'

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(disable, (first, second)))
        assert sorted(results) == ['disabled', 'protected']
        active = [u for u in service.list_users() if u['enabled'] and u['role'] == 'admin']
        assert len(active) == 1
        admin = active[0]
        login = service.login(admin['username'], password)
        assert login is not None
        token, envelope = login
        replay = create_engine(engine.url, connect_args={'options': '-csearch_path=' + schema})
        assert Accounts(replay).session(token)['user']['id'] == admin['id']
        changed = secrets.token_urlsafe(24)
        service.password(admin['id'], password, changed)
        assert Accounts(replay).session(token) is None
        assert service.login(admin['username'], password) is None
        assert service.login(admin['username'], changed)[1]['user']['must_change_password'] is False
        viewer = service.create_user('isolated_viewer', password, 'viewer', 'Isolated viewer', admin['id'])
        viewer_token, _ = service.login(viewer['username'], password)
        service.update_user(viewer['id'], {'enabled': False}, admin['id'])
        assert Accounts(replay).session(viewer_token) is None
    finally:
        if replay is not None:
            replay.dispose()
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    after = counts()
    # Background workers can add evidence; never treat a concurrent count change as corruption.
    # Account and human-review counts are stable expectations during this maintenance window.
    assert all(after[name] == before[name] for name in before if name != 'document_chunk_embeddings'), \
        'Production user/review counts changed during isolated acceptance; inspect before continuing'
    result = {'status': 'passed', 'isolated_schema_removed': True, 'production_counts': after,
              'background_vector_delta': after.get('document_chunk_embeddings', 0)-before.get('document_chunk_embeddings', 0),
              'checks': ['migration_idempotence', 'concurrent_last_admin', 'fresh_connection_session',
                         'password_revocation', 'disabled_user_revocation'],
              'limitations': ['isolated database checks; browser role acceptance remains separate']}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    engine = create_engine(os.environ['DATABASE_URL'])
    try:
        args.output.write_text(json.dumps(accept(engine), indent=2) + '\n')
    finally:
        engine.dispose()

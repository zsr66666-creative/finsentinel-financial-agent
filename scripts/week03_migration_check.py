"""Verify migration round trips in an empty database or isolated schema."""

import argparse
import json
import os
from uuid import uuid4

from sqlalchemy import inspect, text

from app.migrations import migrate_down, migrate_up
from app.store import Store, TABLES


def check_migrations(engine):
    initial_tables = inspect(engine).get_table_names()
    if initial_tables:
        raise ValueError("migration check requires an empty database or isolated schema")

    with engine.connect() as connection:
        version = connection.execute(text("select version()" if engine.dialect.name == "postgresql" else "select sqlite_version()" )).scalar_one()

    first_up = migrate_up(engine)
    after_up = inspect(engine).get_table_names()
    second_up = migrate_up(engine)
    if set(after_up) != set(TABLES) | {"schema_migrations"}:
        raise AssertionError("migration did not create the expected tables")
    if not migrate_down(engine):
        raise AssertionError("migration rollback did not run")
    after_down = inspect(engine).get_table_names()
    if after_down:
        raise AssertionError("migration rollback left tables behind")
    final_up = migrate_up(engine)
    after_reapply = inspect(engine).get_table_names()
    if set(after_reapply) != set(after_up):
        raise AssertionError("migration reapply changed the table set")

    return {
        "dialect": engine.dialect.name,
        "database_version": version,
        "initial_table_count": len(initial_tables),
        "table_count_after_up": len(after_up),
        "table_count_after_down": len(after_down),
        "table_count_after_reapply": len(after_reapply),
        "idempotent": first_up == ["001_initial_schema"] and second_up == [] and final_up == ["001_initial_schema"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("TEST_POSTGRES_URL"))
    args = parser.parse_args()
    if not args.database_url:
        parser.error("set TEST_POSTGRES_URL or pass --database-url")

    if args.database_url.startswith("postgresql"):
        schema = f"finsentinel_migration_{uuid4().hex[:12]}"
        admin = Store(args.database_url, create_schema=False)
        try:
            with admin.engine.begin() as connection:
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            isolated_url = f"{args.database_url}?options=-csearch_path%3D{schema}" if "?" not in args.database_url else f"{args.database_url}&options=-csearch_path%3D{schema}"
            store = Store(isolated_url, create_schema=False)
            try:
                result = check_migrations(store.engine)
            finally:
                store.close()
        finally:
            with admin.engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            admin.close()
    else:
        store = Store(args.database_url, create_schema=False)
        try:
            result = check_migrations(store.engine)
        finally:
            store.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

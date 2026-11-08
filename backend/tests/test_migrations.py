from sqlalchemy import inspect, text

from app.migrations import migrate_down, migrate_up
from app.store import Store


def test_migration_up_is_idempotent_and_down_can_be_reapplied(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'migration.db'}", create_schema=False)

    assert migrate_up(store.engine) == ["001_initial_schema"]
    assert migrate_up(store.engine) == []
    assert "companies" in inspect(store.engine).get_table_names()

    assert migrate_down(store.engine, "001_initial_schema") is True
    assert "companies" not in inspect(store.engine).get_table_names()
    assert migrate_up(store.engine) == ["001_initial_schema"]
    with store.engine.connect() as connection:
        count = connection.execute(text("select count(*) from schema_migrations")).scalar_one()
    assert count == 1
    store.close()

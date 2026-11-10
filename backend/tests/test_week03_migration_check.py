import pytest

from scripts.week03_migration_check import check_migrations
from app.store import Store, TABLES


def test_migration_check_uses_an_empty_database_and_restores_schema(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'migration-check.db'}", create_schema=False)
    try:
        result = check_migrations(store.engine)
        assert result["initial_table_count"] == 0
        assert result["table_count_after_up"] == len(TABLES) + 1
        assert result["table_count_after_down"] == 0
        assert result["table_count_after_reapply"] == len(TABLES) + 1
        assert result["idempotent"]
    finally:
        store.close()


def test_migration_check_rejects_nonempty_database(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'existing.db'}")
    try:
        with pytest.raises(ValueError, match="empty database or isolated schema"):
            check_migrations(store.engine)
        assert len(store.all("companies")) == 0
    finally:
        store.close()

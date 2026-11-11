from sqlalchemy import inspect, text

from app.migrations import migrate_down, migrate_up, migrate_vector_up
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

def test_vector_dimension_mismatch_and_initial_rollback_are_rejected():
    import pytest
    store = Store('sqlite://')
    migrate_vector_up(store.engine, 512)
    with pytest.raises(ValueError, match='dimension'):
        migrate_vector_up(store.engine, 768)
    with pytest.raises(ValueError, match='002'):
        migrate_down(store.engine)
    with pytest.raises(Exception):
        with store.engine.begin() as connection:
            connection.execute(text("INSERT INTO document_chunk_embeddings VALUES ('c','m',3,'[]','hash','now')"))
    store.close()

def test_vector_migration_is_idempotent_and_reversible_on_sqlite(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'vector.db'}", create_schema=False)
    assert migrate_vector_up(store.engine, dimensions=3) == ["002_document_chunk_embeddings"]
    assert migrate_vector_up(store.engine, dimensions=3) == []
    assert "document_chunk_embeddings" in inspect(store.engine).get_table_names()
    assert migrate_down(store.engine, "002_document_chunk_embeddings") is True
    assert "document_chunk_embeddings" not in inspect(store.engine).get_table_names()
    store.close()

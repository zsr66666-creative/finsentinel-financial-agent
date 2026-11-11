from datetime import datetime, timezone
from sqlalchemy import inspect, text
from app.store import Base, MODELS

MIGRATION_NAME = "001_initial_schema"
VECTOR_MIGRATION_NAME = "002_document_chunk_embeddings"

def _ensure_version_table(connection):
    connection.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(100) PRIMARY KEY, applied_at VARCHAR(40) NOT NULL)"))

def migrate_up(engine) -> list[str]:
    with engine.begin() as connection:
        _ensure_version_table(connection)
        applied = {row[0] for row in connection.execute(text("SELECT name FROM schema_migrations"))}
        if MIGRATION_NAME in applied:
            return []
        Base.metadata.create_all(connection)
        connection.execute(text("INSERT INTO schema_migrations (name, applied_at) VALUES (:name, :applied_at)"), {"name": MIGRATION_NAME, "applied_at": datetime.now(timezone.utc).isoformat()})
        return [MIGRATION_NAME]

def migrate_vector_up(engine, dimensions: int = 512) -> list[str]:
    """Create the pgvector-ready embedding store without changing chunks."""
    if type(dimensions) is not int or not 1 <= dimensions <= 2000:
        raise ValueError("embedding dimensions must be an integer from 1 to 2000")
    with engine.begin() as connection:
        _ensure_version_table(connection)
        applied = {row[0] for row in connection.execute(text("SELECT name FROM schema_migrations"))}
        if VECTOR_MIGRATION_NAME in applied:
            constraints = inspect(connection).get_check_constraints('document_chunk_embeddings')
            expected = f'ck_embedding_dimension_{dimensions}'
            if not any(c['name'] == expected for c in constraints):
                raise ValueError('embedding dimension/schema mismatch; inspect the existing table before continuing')
            return []
        if 'document_chunk_embeddings' in inspect(connection).get_table_names():
            raise ValueError('unversioned embedding table exists; inspect before migrating')
        if connection.dialect.name == "postgresql":
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            embedding_type = f"VECTOR({dimensions})"
        else:
            embedding_type = "TEXT"
        connection.execute(text(f"""CREATE TABLE IF NOT EXISTS document_chunk_embeddings (
            chunk_id VARCHAR(200) PRIMARY KEY, model VARCHAR(200) NOT NULL,
            dimensions INTEGER NOT NULL CONSTRAINT ck_embedding_dimension_{dimensions} CHECK (dimensions = {dimensions}), embedding {embedding_type} NOT NULL,
            text_sha256 VARCHAR(64) NOT NULL, created_at VARCHAR(40) NOT NULL)"""))
        # Start with exact search. Train/build an ANN index only after data and
        # recall measurements are available, never on an empty table.
        connection.execute(text("INSERT INTO schema_migrations (name, applied_at) VALUES (:name, :applied_at)"), {"name": VECTOR_MIGRATION_NAME, "applied_at": datetime.now(timezone.utc).isoformat()})
        return [VECTOR_MIGRATION_NAME]

def migrate_down(engine, name: str = MIGRATION_NAME) -> bool:
    if name == VECTOR_MIGRATION_NAME:
        with engine.begin() as connection:
            if "schema_migrations" not in inspect(connection).get_table_names():
                return False
            connection.execute(text("DROP TABLE IF EXISTS document_chunk_embeddings"))
            connection.execute(text("DELETE FROM schema_migrations WHERE name = :name"), {"name": name})
            return True
    if name != MIGRATION_NAME:
        raise ValueError(f"Unknown migration: {name}")
    with engine.begin() as connection:
        if "schema_migrations" not in inspect(connection).get_table_names():
            return False
        if connection.execute(text("SELECT 1 FROM schema_migrations WHERE name = :name"), {'name': VECTOR_MIGRATION_NAME}).first():
            raise ValueError('roll back 002_document_chunk_embeddings before the initial schema')
        for table in reversed(list(MODELS.values())):
            table.__table__.drop(connection, checkfirst=True)
        connection.execute(text("DELETE FROM schema_migrations WHERE name = :name"), {"name": name})
        connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
        return True

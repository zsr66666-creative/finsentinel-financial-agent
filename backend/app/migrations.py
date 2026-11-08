from datetime import datetime, timezone
from sqlalchemy import inspect, text
from app.store import Base, MODELS

MIGRATION_NAME = "001_initial_schema"

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

def migrate_down(engine, name: str = MIGRATION_NAME) -> bool:
    if name != MIGRATION_NAME:
        raise ValueError(f"Unknown migration: {name}")
    with engine.begin() as connection:
        if "schema_migrations" not in inspect(connection).get_table_names():
            return False
        for table in reversed(list(MODELS.values())):
            table.__table__.drop(connection, checkfirst=True)
        connection.execute(text("DELETE FROM schema_migrations WHERE name = :name"), {"name": name})
        connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
        return True

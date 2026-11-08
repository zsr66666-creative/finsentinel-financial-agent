import pytest

from app.database_config import DatabaseConfig


def test_accepts_sqlite_and_postgres_urls_without_exposing_password():
    sqlite = DatabaseConfig.from_url("sqlite:///local.db")
    postgres = DatabaseConfig.from_url("postgresql+psycopg://alice:secret@db.example:5432/finsentinel")

    assert sqlite.is_sqlite is True
    assert postgres.is_sqlite is False
    assert postgres.safe_url == "postgresql+psycopg://alice:***@db.example:5432/finsentinel"


def test_rejects_unsupported_database_scheme():
    with pytest.raises(ValueError, match="Unsupported database URL scheme"):
        DatabaseConfig.from_url("mysql://user:pass@localhost/app")

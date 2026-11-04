"""SQLite database configuration for the v0.1 local backend."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import event

from .store import Store


DEFAULT_DATABASE_URL = "sqlite:///./finsentinel.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_database(url: str | None = None) -> Store:
    """Create the local Store and enable SQLite foreign-key enforcement."""
    store = Store(url or database_url())
    if store.engine.url.get_backend_name() == "sqlite":
        with store.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return store


def database_path() -> Path:
    url = database_url()
    if not url.startswith("sqlite:///"):
        raise ValueError("Day 4 seed requires a SQLite DATABASE_URL")
    return Path(url.removeprefix("sqlite:///"))

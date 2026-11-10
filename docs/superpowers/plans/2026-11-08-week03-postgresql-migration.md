# Week 03 PostgreSQL Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PostgreSQL-compatible persistence path while preserving SQLite local mode and verifying migration, rollback, and API response compatibility.

**Architecture:** Keep the existing SQLAlchemy `Store` interface and JSON payload model as the application boundary. Add an explicit schema version table and idempotent migration runner, use PostgreSQL connection settings from `DATABASE_URL`, and keep SQLite as the default development database. Migration tests use temporary SQLite plus an optional PostgreSQL service when available.

**Tech Stack:** Python 3.13, SQLAlchemy 2.x, SQLite, PostgreSQL 16, pytest, Podman Compose.

## Global Constraints

- SQLite remains the default local mode.
- PostgreSQL must use the same `Store.all`, `Store.get`, and `Store.put` behavior.
- Migrations must be idempotent and provide a verified rollback path.
- Database connection failures must return an actionable application error without exposing credentials.
- No API keys, passwords, or connection strings containing secrets may enter Git.

---

### Task 1: Database dependency and configuration contract

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/store.py`
- Create: `backend/app/database_config.py`
- Test: `backend/tests/test_database_config.py`

- [x] Add the PostgreSQL SQLAlchemy driver and a parser for `DATABASE_URL`.
- [x] Preserve `sqlite:///...` and `sqlite:///:memory:` behavior.
- [x] Reject unsupported schemes with a clear `ValueError`.
- [x] Redact passwords in diagnostic strings.
- [x] Run `python -m pytest backend/tests/test_database_config.py -q` (2 passed).

### Task 2: Versioned migration runner

**Files:**
- Create: `backend/migrations/001_initial_schema.py`
- Create: `backend/app/migrations.py`
- Modify: `backend/app/store.py`
- Test: `backend/tests/test_migrations.py`

- [x] Add a `schema_migrations` table with migration name and applied timestamp.
- [x] Make the initial migration create all existing tables and indexes.
- [x] Make repeated migration runs no-op successfully.
- [x] Add `migrate_up()` and `migrate_down()` APIs with explicit migration names.
- [x] Verify up, second up, down, and up again against a temporary SQLite database (1 passed).

### Task 3: PostgreSQL connection and failure handling

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/store.py`
- Test: `backend/tests/test_database_startup.py`

- [ ] Initialize the store from `DATABASE_URL` without changing API routes.
- [ ] Catch connection failures during startup and expose a safe `/health` response with database status.
- [ ] Ensure error responses never include passwords or full connection URLs.
- [ ] Keep synthetic SQLite startup unchanged for local tests.
- [ ] Run `python -m pytest backend/tests/test_database_startup.py backend/tests/test_backend.py -q`.

### Task 4: API parity regression

**Files:**
- Create: `backend/tests/test_sqlite_postgres_parity.py`
- Modify: `docs/week03-postgresql-migration.md`

- [ ] Seed the same fixture through SQLite and PostgreSQL stores when `TEST_POSTGRES_URL` is set.
- [ ] Compare `/api/v1/companies`, `/api/v1/alerts`, `/api/v1/evals/summary`, and evidence responses after normalization of ordering and timestamps.
- [ ] Skip only the PostgreSQL half when `TEST_POSTGRES_URL` is absent, and report that limitation explicitly.
- [ ] Record migration command, database versions, table count, and parity result.

### Task 5: Compose and rollback acceptance

**Files:**
- Modify: `compose.yaml`
- Create: `scripts/week03_migration_check.py`
- Create: `docs/week03-postgresql-migration.md`

- [ ] Add PostgreSQL service configuration with a health check and a non-secret development password supplied by environment substitution.
- [ ] Add backend dependency on the database health check.
- [ ] Make the script run migration up, verify table count, run rollback, and migrate up again.
- [ ] Run static Compose validation when Podman/Docker is available; otherwise record the exact environment limitation.

### Task 6: Verification and release checkpoint

**Files:**
- Modify: `README.md`
- Modify: `docs/week03-postgresql-migration.md`

- [ ] Run backend tests and migration checks.
- [ ] Run `git diff --check`.
- [ ] Record PASS/WARN/FAIL separately for SQLite, PostgreSQL, rollback, and API parity.
- [ ] Commit only the Week 03 files and push after verification.

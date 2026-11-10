# Week 3 PostgreSQL migration status

## Task 4: API parity

The parity test is in `backend/tests/test_sqlite_postgres_parity.py`. It calls the
companies, alerts, evaluation summary, and evidence APIs against the same
synthetic fixture in SQLite and PostgreSQL. It requires `TEST_POSTGRES_URL` to
point to an empty, disposable PostgreSQL database; the test refuses a database
that contains application data. The SQLite contract runs independently.

Run from the repository root:

```text
python -m pytest backend/tests/test_sqlite_postgres_parity.py -q
```

With a disposable PostgreSQL database available, set `TEST_POSTGRES_URL` in
the process environment and rerun the same command. The URL must remain out
of committed files and logs.

## Verification status

| Check | Status | Evidence |
|---|---|---|
| SQLite API contract | PASS | Companies, alerts, evaluation summary, and evidence returned expected data. |
| PostgreSQL API parity | PASS | PostgreSQL 18.6, `test_sqlite_postgres_parity.py`: 2 passed, 0 skipped. |
| PostgreSQL migration on isolated schema | PASS | PostgreSQL 18.6; table count 0 -> 15 -> 0 -> 15; repeated up is a no-op. |
| SQLite migration up/down | PASS | Covered by `backend/tests/test_migrations.py`. |

The local Windows PostgreSQL 18.6 service was used for parity verification.
The disposable test database contained 14 application tables after the test.
This proves the selected API responses match SQLite for the synthetic fixture;
deployment and recovery checks remain unverified. PostgreSQL production
readiness is not established.

## Task 5: migration and Compose

The migration check uses a new random PostgreSQL schema in the configured
test database. It removes that schema after the check, including on failure.
It refuses to run against a nonempty SQLite database. Run it from the
repository root with `PYTHONPATH=backend;.` on Windows or
`PYTHONPATH=backend:.` on Linux:

```text
python -m scripts.week03_migration_check
```

Set `TEST_POSTGRES_URL` in the process environment. The URL must target a
disposable test database and must not be committed. On PostgreSQL 18.6 the
check reported 0 tables before migration, 15 after up, 0 after down, and 15
after reapplying; idempotency was true. The 15 tables consist of 14 application
tables and `schema_migrations`.

The default `compose.yaml` keeps SQLite mode. To use PostgreSQL, set
`POSTGRES_PASSWORD` in the process environment and run:

```text
podman compose -f compose.yaml -f compose.postgres.yaml --profile postgres up --build
```

The PostgreSQL service has `pg_isready` health checks; the PostgreSQL overlay
makes the backend wait for a healthy database. Both YAML files parsed and the
dependency contract was checked locally. A container start was not verified:
Podman machine was unavailable to this Codex environment, and
`podman_compose` failed to spawn a child process with WinError 5.

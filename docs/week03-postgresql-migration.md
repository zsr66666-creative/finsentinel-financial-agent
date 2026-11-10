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
| PostgreSQL migration on empty database | NOT RUN | The parity test creates tables through `Store`; the versioned migration runner has not been run on PostgreSQL. |
| SQLite migration up/down | PASS | Covered by `backend/tests/test_migrations.py`. |

The local Windows PostgreSQL 18.6 service was used for parity verification.
The disposable test database contained 14 application tables after the test.
This proves the selected API responses match SQLite for the synthetic fixture;
the versioned migration on PostgreSQL, rollback, deployment, and recovery
checks remain unverified. PostgreSQL production readiness is not established.

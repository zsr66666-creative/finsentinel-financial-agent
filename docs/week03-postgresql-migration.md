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
| PostgreSQL API parity | NOT RUN | No PostgreSQL service or `TEST_POSTGRES_URL` is available in this environment. |
| PostgreSQL migration on empty database | NOT RUN | Requires a running PostgreSQL instance. |
| SQLite migration up/down | PASS | Covered by `backend/tests/test_migrations.py`. |

The local Podman socket at `127.0.0.1:50078` refused connections and port
`127.0.0.1:5432` was closed. An attempt to start the existing Podman machine
from Codex was not executed because the automatic approval service returned
HTTP 413. PostgreSQL API parity and database version remain unverified.
PostgreSQL production readiness is not established.

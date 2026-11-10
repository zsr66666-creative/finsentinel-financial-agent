import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from app.store import Store, TABLES


def api_snapshot(database_url):
    with TestClient(create_app(database_url, data_mode="synthetic_demo")) as client:
        companies = client.get("/api/v1/companies")
        alerts = client.get("/api/v1/alerts")
        eval_summary = client.get("/api/v1/evals/summary")
        metrics = client.get("/api/v1/companies/002475/metrics")
        assert companies.status_code == alerts.status_code == eval_summary.status_code == metrics.status_code == 200
        evidence_id = metrics.json()["items"][0]["source_ids"][0]
        evidence = client.get(f"/api/v1/evidence/{evidence_id}")
        assert evidence.status_code == 200
        return {
            "companies": companies.json(),
            "alerts": alerts.json(),
            "eval_summary": eval_summary.json(),
            "evidence": evidence.json(),
        }


def test_sqlite_api_contract_baseline(tmp_path):
    result = api_snapshot(f"sqlite:///{tmp_path / 'api-contract.db'}")

    assert len(result["companies"]["items"]) == 24
    assert result["alerts"]["items"]
    assert result["eval_summary"]["data_mode"] == "synthetic_demo"
    assert result["evidence"]["id"]
    assert result["evidence"]["page_no"] > 0


def test_sqlite_and_postgres_api_contracts_match(tmp_path):
    postgres_url = os.getenv("TEST_POSTGRES_URL")
    if not postgres_url:
        pytest.skip("TEST_POSTGRES_URL is not configured; PostgreSQL API parity not measured")

    postgres_store = Store(postgres_url)
    try:
        with postgres_store.engine.connect() as connection:
            nonempty = []
            for table in TABLES:
                count = connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
                if count:
                    nonempty.append(table)
        if nonempty:
            pytest.fail("TEST_POSTGRES_URL must point to an empty disposable database; non-empty tables: " + ", ".join(nonempty))
    finally:
        postgres_store.close()

    sqlite_result = api_snapshot(f"sqlite:///{tmp_path / 'sqlite-parity.db'}")
    postgres_result = api_snapshot(postgres_url)
    assert postgres_result == sqlite_result

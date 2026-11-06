from fastapi.testclient import TestClient

from app.main import create_app


def test_week12_core_api_contract(tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'e2e.db'}", data_mode="synthetic_demo"))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["data_mode"] == "synthetic_demo"

    alerts = client.get("/api/v1/alerts")
    companies = client.get("/api/v1/companies")
    quality = client.get("/api/v1/data/quality")
    assert alerts.status_code == companies.status_code == quality.status_code == 200
    assert alerts.json()["items"]
    assert companies.json()["items"]
    assert quality.json()["data_mode"] == "synthetic_demo"

    company_id = companies.json()["items"][0]["id"]
    metrics = client.get(f"/api/v1/companies/{company_id}/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["items"]
    assert all(row["data_mode"] == "synthetic_demo" for row in metrics.json()["items"])


def test_week12_missing_company_and_metric_are_explicit(tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'e2e-errors.db'}", data_mode="synthetic_demo"))
    assert client.get("/api/v1/companies/missing/metrics").status_code == 404

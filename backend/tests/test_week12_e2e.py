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


def test_week12_observability_tracks_latency_and_errors(tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'observability.db'}", data_mode="synthetic_demo"))
    assert client.get("/health").headers["x-process-time-ms"]
    assert client.get("/api/v1/companies/missing").status_code == 404
    body = client.get("/api/v1/observability").json()
    # The metrics endpoint returns the snapshot collected before its own response is recorded.
    assert body["requests_total"] >= 2
    assert body["errors_total"] >= 1
    assert body["error_rate"] > 0
    assert body["p95_duration_ms"] >= body["avg_duration_ms"]
    assert body["status_counts"]["404"] >= 1
    assert body["sample_size"] >= 2
    assert body["recent_requests"]


def test_week12_security_headers_and_cors_boundary(tmp_path):
    client = TestClient(create_app(f"sqlite:///{tmp_path / 'security.db'}", data_mode="synthetic_demo"))
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"

    external = client.get("/health", headers={"Origin": "https://example.invalid"})
    assert "access-control-allow-origin" not in external.headers

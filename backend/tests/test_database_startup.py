from fastapi.testclient import TestClient

import app.main as main


def test_sqlite_health_reports_connected_database(tmp_path):
    client = TestClient(main.create_app(f"sqlite:///{tmp_path / 'health.db'}", data_mode="synthetic_demo"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"] == {"status": "connected", "dialect": "sqlite"}


def test_database_url_environment_variable_selects_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'from-env.db'}")
    client = TestClient(main.create_app(data_mode="real_corpus"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["database"]["dialect"] == "sqlite"


def test_database_startup_error_is_safe_and_visible(monkeypatch):
    def fail_store(url):
        raise RuntimeError("connection failed: postgresql://user:top-secret@db.internal/app")

    monkeypatch.setattr(main, "Store", fail_store)
    app = main.create_app("postgresql+psycopg://user:top-secret@db.internal/app", data_mode="real_corpus")

    response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.json()["database"] == {"status": "unavailable", "error": "database_connection_failed"}
    assert "top-secret" not in response.text
    assert "db.internal" not in response.text

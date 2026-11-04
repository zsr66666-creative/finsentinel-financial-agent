from fastapi.testclient import TestClient

from app.database import create_database
from app.main import create_app
from app.seed import seed_day4


def _client(tmp_path):
    url = f"sqlite:///{tmp_path / 'api.db'}"
    seed_day4(create_database(url))
    return TestClient(create_app(url, data_mode="real_corpus"))


def test_growth_endpoint_returns_verified_values(tmp_path):
    response = _client(tmp_path).get(
        "/api/v1/companies/cn-002475/metrics/revenue/growth",
        params={"current_period": "2026H1", "previous_period": "2025H1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["current_value"] == "174504335921.25"
    assert body["previous_value"] == "124503174115.60"
    assert body["growth"] == "40.16"
    assert body["data_mode"] == "real_public_disclosure_local_copy"


def test_growth_does_not_invent_inventory_comparison(tmp_path):
    response = _client(tmp_path).get(
        "/api/v1/companies/cn-002475/metrics/inventory/growth",
        params={"current_period": "2026H1", "previous_period": "2025H1"},
    )
    assert response.status_code == 404


def test_financial_ratios_endpoint_returns_formulas_and_values(tmp_path):
    response = _client(tmp_path).get(
        "/api/v1/companies/cn-002475/financial-ratios",
        params={
            "revenue": "120",
            "cost": "90",
            "opening_receivables": "40",
            "closing_receivables": "80",
            "opening_inventory": "30",
            "closing_inventory": "60",
            "operating_cash_flow": "30",
            "consolidated_net_profit": "100",
        },
    )
    assert response.status_code == 200
    ratios = response.json()["ratios"]
    assert ratios["gross_margin"]["value"] == "25"
    assert ratios["receivables_turnover"]["value"] == "2"
    assert ratios["inventory_turnover"]["value"] == "2"
    assert ratios["cash_flow_quality"]["value"] == "0.3"

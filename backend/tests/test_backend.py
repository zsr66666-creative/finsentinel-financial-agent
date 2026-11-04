from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tools import calc_growth, detect_anomaly


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as client:
        yield client


def test_decimal_growth_and_zero_denominator():
    assert calc_growth(Decimal('80'), Decimal('100')) == Decimal('-20')
    with pytest.raises(ValueError, match='zero'):
        calc_growth(Decimal('3'), Decimal('0'))
    assert detect_anomaly([100, 80], 'decline_10pct')['triggered']


def test_seed_data_and_evidence_contract(client):
    companies = client.get('/api/v1/companies').json()['items']
    assert len(companies) == 24
    metrics = client.get('/api/v1/companies/002475/metrics').json()['items']
    assert metrics and all(m['source_ids'] for m in metrics)
    assert metrics[0]['company']['name'] == '立讯精密'
    evidence_id = metrics[0]['source_ids'][0]
    evidence = client.get('/api/v1/evidence/' + evidence_id)
    assert evidence.status_code == 200
    assert evidence.json()['page_no'] > 0
    alerts = client.get('/api/v1/alerts').json()['items']
    assert alerts
    detail = client.get(f"/api/v1/alerts/{alerts[0]['id']}").json()
    assert detail['evidence'][0]['page'] > 0
    assert detail['data_mode'] == 'synthetic_demo'


def test_analysis_has_verified_evidence_and_trace(client):
    response = client.post('/api/v1/analysis/runs', json={'company_id': '002475', 'question': '营收同比和现金流有什么风险？'})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run['status'] == 'completed'
    assert [s['node'] for s in run['agent_steps']] == ['Planner', 'DataQuality', 'Retriever', 'QuantAnalyst', 'EvidenceVerifier', 'ReportComposer']
    assert run['tool_calls'] and run['evidence']
    assert run['verification']['numeric_verified']
    assert run['verification']['citation_coverage'] == 1.0
    assert client.get('/api/v1/analysis/runs/' + run['id']).json()['id'] == run['id']


def test_feedback_enters_regression_queue(client):
    alert = client.get('/api/v1/alerts').json()['items'][0]
    response = client.post(f"/api/v1/alerts/{alert['id']}/feedback", json={'action':'reject', 'error_type':'citation_error', 'comment':'证据不足'})
    assert response.status_code == 201
    assert response.json()['regression_case_id']
    assert client.get('/api/v1/alerts/' + alert['id']).json()['status'] == 'rejected'
    summary = client.get('/api/v1/evals/summary').json()
    assert summary['pending_regression_cases'] == 1


def test_input_validation_and_missing_resources(client):
    assert client.post('/api/v1/analysis/runs', json={'company_id': 'missing', 'question': 'test'}).status_code == 404
    assert client.post('/api/v1/analysis/runs', json={'company_id': '002475', 'question': ''}).status_code == 422
    assert client.get('/api/v1/alerts/missing').status_code == 404
    assert client.post('/api/v1/alerts/missing/feedback', json={'action': 'reject'}).status_code == 404
    assert client.get('/api/v1/companies/missing/metrics').status_code == 404
    assert client.get('/api/v1/companies/002475/metrics?period=2099').status_code == 404
    assert client.get('/api/v1/evidence/missing').status_code == 404


def test_ingestion_and_evaluations(client):
    response = client.post('/api/v1/admin/ingestion/jobs', json={'company_ids': ['002475'], 'mode':'demo_refresh'})
    assert response.status_code == 202
    assert response.json()['status'] == 'completed'
    result = client.post('/api/v1/evals/runs', json={'mode':'workflow'}).json()
    assert result['case_count'] >= 30
    assert result['metrics']['numeric_accuracy'] == 1.0
    assert result['metrics']['citation_coverage'] == 1.0


def test_state_survives_app_restart(tmp_path):
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    with TestClient(create_app(url)) as client:
        run = client.post('/api/v1/analysis/runs', json={'company_id':'002475','question':'分析营业收入'}).json()
    with TestClient(create_app(url)) as client:
        assert client.get('/api/v1/analysis/runs/' + run['id']).status_code == 200

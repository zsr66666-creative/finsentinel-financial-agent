import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'day4.db'}")) as c:
        yield c

def test_feedback_history_and_candidate_persist(client):
    alert = client.get('/api/v1/alerts').json()['items'][0]
    key = 'day4-idempotency-001'
    payload = {'action':'reject','error_type':'citation_error','comment':'证据不足','idempotency_key':key}
    first = client.post(f"/api/v1/alerts/{alert['id']}/feedback", json=payload)
    second = client.post(f"/api/v1/alerts/{alert['id']}/feedback", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()['id'] == second.json()['id']
    assert len(client.get(f"/api/v1/alerts/{alert['id']}/feedback").json()['items']) == 1
    assert len(client.get('/api/v1/review/candidates').json()['items']) == 1

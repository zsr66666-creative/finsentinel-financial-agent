import pytest
from app.store import Store

def test_feedback_transaction_rolls_back_when_candidate_conflicts(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'rollback.db'}")
    store.put('alerts', {'id': 'a1', 'status': 'pending'})
    store.put('eval_cases', {'id': 'case-1', 'status': 'pending_review'})
    with pytest.raises(Exception):
        store.feedback_transaction(feedback={'id': 'f1'}, alert={'id': 'a1', 'status': 'rejected'}, candidate={'id': 'case-1', 'status': 'pending_review'})
    assert store.get('feedback', 'f1') is None
    assert store.get('alerts', 'a1')['status'] == 'pending'
    store.close()

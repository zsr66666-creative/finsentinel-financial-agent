import pytest
from app.review import next_alert_status, validate_feedback

def test_feedback_status_transitions():
    assert next_alert_status('pending', 'confirm') == 'confirmed'
    assert next_alert_status('pending', 'reject') == 'rejected'
    assert next_alert_status('pending', 'modify') == 'modified_pending_review'

def test_feedback_requires_reason_and_modification():
    with pytest.raises(ValueError, match='reason'):
        validate_feedback('reject', reason=None, comment='', modification=None)
    with pytest.raises(ValueError, match='modification'):
        validate_feedback('modify', reason='数字需更正', comment='', modification=None)
    validate_feedback('modify', reason='数字需更正', comment='', modification={'answer': '2'})

def test_review_does_not_reopen_final_status():
    with pytest.raises(ValueError, match='cannot be reviewed'):
        next_alert_status('confirmed', 'reject')

from typing import Literal

FeedbackAction = Literal['confirm', 'reject', 'modify']
STATUS_BY_ACTION = {'confirm': 'confirmed', 'reject': 'rejected', 'modify': 'modified_pending_review'}

def validate_feedback(action: FeedbackAction, *, reason: str | None, comment: str, modification: dict | None) -> None:
    text = (reason or comment or '').strip()
    if action in ('reject', 'modify') and not text:
        raise ValueError('reason is required for reject/modify')
    if action == 'modify' and not modification:
        raise ValueError('modification is required for modify')

def next_alert_status(current: str, action: FeedbackAction) -> str:
    if current not in ('pending', 'pending_review', 'modified_pending_review'):
        raise ValueError(f'alert status {current} cannot be reviewed again')
    return STATUS_BY_ACTION[action]

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AnalysisRequest(StrictModel):
    company_id: str
    question: str = Field(min_length=1, max_length=2000)
    period: str = '2025'
    mode: Literal['workflow', 'baseline'] = 'workflow'


class FeedbackRequest(StrictModel):
    action: Literal['confirm', 'reject', 'modify']
    error_type: Literal['data_error', 'calculation_error', 'citation_error', 'period_error', 'overstatement', 'other'] | None = None
    comment: str = Field(default='', max_length=2000)
    reason: str | None = Field(default=None, max_length=2000)
    modification: dict[str, str | int | float | bool | None] | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)


class IngestionRequest(StrictModel):
    company_ids: list[str] = Field(default_factory=list, max_length=30)
    mode: Literal['demo_refresh'] = 'demo_refresh'


class EvalRequest(StrictModel):
    mode: Literal['workflow', 'baseline'] = 'workflow'


class RiskEvaluationRequest(StrictModel):
    company_id: str
    period: str
    metrics: dict[str, str | int | float | None]
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)


class EventEvaluationRequest(StrictModel):
    company_id: str
    period: str
    event_type: Literal['impairment', 'litigation', 'major_customer', 'related_party']
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    event_date: str | None = None
    amount: str | None = None
    description: str = Field(default='', max_length=2000)

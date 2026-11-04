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

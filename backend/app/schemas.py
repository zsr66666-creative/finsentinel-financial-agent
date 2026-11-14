from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class EvidenceComparisonRequest(StrictModel):
    question: str = Field(min_length=1, max_length=500)


class EvidenceVectorSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    vector: list[float] = Field(min_length=512, max_length=512)
    model: str = Field(min_length=1, max_length=160)
    company_code: str = Field(min_length=1, max_length=32)
    period: str = Field(min_length=1, max_length=32)
    top_k: int = Field(default=5, ge=1, le=20)
    as_of: str | None = Field(default=None, max_length=32)


class EvidenceTextSearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    company_code: str = Field(min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
    period: str = Field(min_length=1, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator('query')
    @classmethod
    def meaningful_query(cls, value):
        if not value.strip():
            raise ValueError('query must contain text')
        return value.strip()


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

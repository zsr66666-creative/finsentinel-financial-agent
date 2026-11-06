"""Typed v0.1 records used by seed scripts and API boundaries.

The existing Store persists these records in SQLite JSON columns while the
field names follow the relational data contract in docs/data-contract.md.
Alembic migrations can replace the JSON payload columns with normalized
tables in the next backend milestone without changing the API contract.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CompanyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    ticker: str
    name: str
    exchange: Literal["SZ", "SH", "BJ"]
    industry: str


class DocumentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    company_id: str
    title: str
    document_type: str
    report_period: str
    published_at: str | None = None
    source_url: str | None = None
    accessed_at: str
    sha256: str
    file_size_bytes: int
    page_count: int
    extraction_method: str
    quality_status: str


class MetricRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    company_id: str
    document_id: str
    metric: Literal["revenue", "net_profit_attributable", "inventory"]
    value: Decimal | str | None
    currency: str = "CNY"
    unit: str
    period: str
    statement_scope: Literal["consolidated", "parent_company"]
    source_page: int | None = None
    source_evidence_ids: list[str]
    quality_status: str


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    document_id: str
    page_no: int
    text: str
    source_url: str | None = None
    extraction_method: str

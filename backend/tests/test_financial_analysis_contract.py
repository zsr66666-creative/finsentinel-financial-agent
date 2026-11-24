import pytest
from pydantic import ValidationError

from app.schemas import AnalysisResponse, FinancialInput


def test_verified_input_requires_page_and_document_hash():
    with pytest.raises(ValidationError):
        FinancialInput(company_id='000100', metric='net_profit', period='2024FY',
                       value='1', unit='CNY', statement_scope='consolidated',
                       extraction_status='human_verified', evidence_id='ev1')


def test_needs_review_response_can_explain_missing_input():
    result = AnalysisResponse(status='needs_review', classification='无法判断',
                              metrics={}, charts=[], evidence=[],
                              reason='missing verified cash flow')
    assert result.status == 'needs_review'

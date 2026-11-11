import pytest
from app.evidence_comparison import compare_evidence

def row(value, **changes):
    return dict(company='002475', metric='inventory', period='2026-06-30',
                unit='CNY', scope='parent', value=value, evidence_ids=['p63'], **changes)

def test_decimal_comparison_and_explicit_negation():
    previous = row('0.2'); previous['period']='2025-12-31'
    result=compare_evidence(row('0.3'), previous, relation='not_greater')
    assert result['status']=='supported'
    assert result['claim_true'] is False
    assert result['difference']=='0.1'
    assert result['evidence_ids']==['p63']

@pytest.mark.parametrize('field,value', [('company','other'),('unit','USD'),
    ('scope','consolidated'),('metric','revenue'),('value','NaN'),
    ('evidence_ids',[]),('period','2027-01-01')])
def test_unusable_or_mismatched_evidence_requires_review(field,value):
    previous=row('10'); previous['period']='2025-12-31'; previous[field]=value
    assert compare_evidence(row('20'),previous,relation='greater')['status']=='needs_review'

def test_unsupported_forecast_relation_requires_review():
    assert compare_evidence(row('20'),row('10'),relation='will_grow')['status']=='needs_review'

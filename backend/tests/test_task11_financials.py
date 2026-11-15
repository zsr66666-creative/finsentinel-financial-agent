from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import create_app
from app.verified_financials import calculate_change, company_comparisons, verify_metric, load_contracts


def test_decimal_change_is_exact_and_zero_is_not_fabricated():
    assert calculate_change('0.30', '0.10') == dict(difference='0.20', change_percent='200.00', change_percent_reason=None, direction='increase')
    assert calculate_change('0.00', '0.00') == dict(difference='0.00', change_percent=None, change_percent_reason='zero_comparison_base', direction='unchanged')
    assert calculate_change('-2.00', '-4.00')['change_percent'] == '50.00'
    assert calculate_change('1.00', '6.00')['change_percent'] == '-83.33'
    for value in ('NaN', 'Infinity', '1e9', '1,234.00', '', None):
        with pytest.raises(ValueError): calculate_change(value, '1.00')


def test_contract_does_not_relabel_original_balance_columns():
    reports = load_contracts()
    assert len(reports) == 2
    xf = next(r for r in reports if r['company_code'] == '002230')
    metric = next(m for m in xf['metrics'] if m['metric'] == 'receivables')
    assert metric['previous_period'] == '2024-01-01'
    assert len(xf['metrics']) == 3


def test_evidence_change_or_missing_anchor_refuses_numeric_result():
    report = load_contracts()[0]
    metric = report['metrics'][0]
    pages = {e['page']: 'unrelated text' for e in metric['evidence']}
    rejected = verify_metric(report, metric, pages)
    assert rejected['status'] == 'needs_review'
    assert 'current_value' not in rejected and 'difference' not in rejected


def test_unsupported_scope_or_missing_artifact_never_uses_demo_values(tmp_path):
    engine = create_engine('sqlite:///:memory:')
    for code, period, scope in [('002475','2024FY','consolidated'),('002230','2023FY','consolidated'),('002555','2024FY','parent')]:
        result = company_comparisons(engine, code, period, scope, tmp_path)
        assert result['status'] == 'needs_review' and result['items'] == []
    result = company_comparisons(engine, '002555', '2024FY', 'consolidated', tmp_path)
    assert len(result['items']) == 3 and all(i['status'] == 'needs_review' for i in result['items'])
    assert all('current_value' not in i for i in result['items'])


def test_api_refuses_unavailable_source_and_preserves_legacy_route():
    client = TestClient(create_app(database_url='sqlite:///:memory:'))
    body = client.get('/api/v1/companies/002555/financial-comparison').json()
    assert body['status'] == 'needs_review'
    assert body['data_mode'] != 'synthetic_demo'
    assert client.post('/api/v1/evidence/compare', json={'question':'不完整问题'}).json()['status'] == 'needs_review'


@pytest.fixture
def real_sources(tmp_path):
    local = Path(__file__).resolve().parents[2] / 'work/task10-real'
    if not (local/'002230-2024FY.pdf').exists():
        pytest.skip('local real official PDFs not present; cloud acceptance is required')
    blobs = tmp_path/'blobs'; blobs.mkdir()
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE ingestion_artifacts (id TEXT, sha256 TEXT, company_code TEXT, report_period TEXT, report_type TEXT, artifact_path TEXT)'))
        for report in load_contracts():
            (blobs/(report['sha256']+'.pdf')).write_bytes((local/(report['company_code']+'-2024FY.pdf')).read_bytes())
            conn.execute(text('INSERT INTO ingestion_artifacts VALUES (:document_id,:sha256,:company_code,:report_period,:report_type,:artifact_path)'), {**report, 'artifact_path':'not-read-by-this-api'})
    return engine, tmp_path


def test_actual_official_pdfs_produce_six_source_bound_comparisons(real_sources):
    engine, root = real_sources
    expected = {'002555': ('17440957495.58','1212667677.20','2997982682.73'), '002230':('23343093018.69','14666453043.92','2495173454.92')}
    for code, values in expected.items():
        result = company_comparisons(engine, code, '2024FY', 'consolidated', root)
        assert result['status'] == 'supported'
        assert tuple(m['current_value'] for m in result['items']) == values
        assert all(m['review_status']=='pending_human' and m['evidence'] for m in result['items'])
        for metric in result['items']:
            assert Decimal(metric['difference']) == Decimal(metric['current_value']) - Decimal(metric['previous_value'])
            assert metric['source_url'].startswith('https://static.cninfo.com.cn/')
            assert {e['role'] for e in metric['evidence']} >= {'row','statement','columns','unit'}
            assert metric['statement_scope'] == 'consolidated'


def test_wrong_db_company_or_substituted_pdf_is_rejected(real_sources):
    engine, root = real_sources
    with engine.begin() as conn:
        conn.execute(text("UPDATE ingestion_artifacts SET company_code='002230' WHERE company_code='002555'"))
    result = company_comparisons(engine, '002555','2024FY','consolidated',root)
    assert all(m['status']=='needs_review' and 'current_value' not in m for m in result['items'])
    report = next(r for r in load_contracts() if r['company_code']=='002230')
    (root/'blobs'/(report['sha256']+'.pdf')).write_bytes(b'%PDF-tampered')
    result = company_comparisons(engine, '002230','2024FY','consolidated',root)
    assert all(m['status']=='needs_review' and 'current_value' not in m for m in result['items'])


def test_valid_hash_does_not_allow_different_numeric_contract():
    import fitz
    local = Path(__file__).resolve().parents[2]/'work/task10-real/002555-2024FY.pdf'
    if not local.exists(): pytest.skip('real PDF unavailable')
    report = next(r for r in load_contracts() if r['company_code']=='002555')
    metric = deepcopy(report['metrics'][0]);metric['current_value']='1.00'
    with fitz.open(local) as doc:
        pages = {e['page']: doc[e['page']-1].get_text() for e in metric['evidence']}
    assert verify_metric(report,metric,pages)['status']=='needs_review'

def test_period_unit_scope_and_metric_metadata_cannot_drift_from_statement():
    import fitz
    local = Path(__file__).resolve().parents[2]/'work/task10-real'
    if not (local/'002555-2024FY.pdf').exists(): pytest.skip('real PDFs unavailable')
    for report in load_contracts():
        with fitz.open(local/(report['company_code']+'-2024FY.pdf')) as doc:
            for metric in report['metrics']:
                pages={e['page']:doc[e['page']-1].get_text() for e in metric['evidence']}
                for key,bad in [('current_period','2025-01-01/2025-12-31'),('previous_period','2022-01-01/2022-12-31'),('current_column','2025 年度'),('previous_column','2022 年度'),('period_kind','incorrect'),('unit','USD'),('statement_scope','parent'),('label','错误指标')]:
                    changed={**metric,key:bad}
                    value=verify_metric(report,changed,pages)
                    assert value['status']=='needs_review' and 'current_value' not in value,(report['company_code'],metric['metric'],key)

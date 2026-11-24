from fastapi.testclient import TestClient

from app.main import create_app
from app.corpus import load_corpus


def _add_verified_period(store, code, period, net, cash, page):
    store.put('filings', {'id':f'{code}-{period}', 'company_id':code, 'version':'b' * 64,
                          'source_url':f'https://reports.example.test/{code}-{period}.pdf',
                          'data_mode':'real_corpus'})
    for metric, value, offset in [('net_profit', net, 0), ('operating_cash_flow', cash, 1)]:
        eid = f'{code}-{period}-{metric}-ev'
        store.put('evidence_spans', {'id': eid, 'company_id': code, 'period': period,
                    'page': page + offset, 'text': f'核验摘录 {metric} {value}',
                    'filing_id': f'{code}-{period}', 'data_mode': 'real_corpus'})
        store.put('financial_metrics', {'id': f'{code}-{period}-{metric}', 'company_id': code,
                    'filing_id':f'{code}-{period}',
                    'metric': metric, 'value': str(value), 'unit': 'CNY', 'period': period,
                    'source_ids': [eid], 'statement_scope': 'consolidated',
                    'document_sha256': 'b' * 64, 'page': page + offset,
                    'excerpt': f'核验摘录 {metric} {value}', 'extraction_status': 'human_verified',
                    'evidence_id': eid, 'data_mode': 'real_corpus'})


def test_analysis_endpoint_returns_auditable_formula_and_chart_values():
    app = create_app(database_url='sqlite://', data_mode='empty')
    store = app.state.store
    store.put('companies', {'id': '000100', 'code': '000100', 'name': 'TCL科技', 'data_mode': 'real_corpus'})
    _add_verified_period(store, '000100', '2023FY', 100, 110, 20)
    _add_verified_period(store, '000100', '2024FY', 125, 88, 30)
    response = TestClient(app).get('/api/v1/companies/000100/financial-analysis?from_period=2023FY&to_period=2024FY')
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'completed'
    assert result['classification'] == '利润增长但现金流恶化'
    assert result['metrics']['net_profit_yoy']['value'] == '25.00'
    assert result['charts'][0]['series'][1]['value'] == '-20.0'
    assert {item['page'] for item in result['evidence']} == {20, 21, 30, 31}
    assert all(item['source_url'].startswith('https://reports.example.test/') for item in result['evidence'])


def test_agent_run_uses_financial_analysis_tool_for_cash_profit_question():
    app = create_app(database_url='sqlite://', data_mode='empty')
    store = app.state.store
    store.put('companies', {'id': '000100', 'code': '000100', 'name': 'TCL科技', 'data_mode': 'real_corpus'})
    _add_verified_period(store, '000100', '2023FY', 100, 110, 20)
    _add_verified_period(store, '000100', '2024FY', 125, 88, 30)
    response = TestClient(app).post('/api/v1/analysis/runs', json={
        'company_id': '000100', 'question': '2024FY经营现金流与净利润是否背离？', 'period': '2024FY'})
    assert response.status_code == 201
    run = response.json()
    assert run['status'] == 'completed'
    assert run['classification'] == '利润增长但现金流恶化'
    assert run['metrics']['net_profit_yoy']['value'] == '25.00'


def test_analysis_endpoint_refuses_synthetic_or_unverified_metrics():
    app = create_app(database_url='sqlite://', data_mode='empty')
    store = app.state.store
    store.put('companies', {'id': '000100', 'code': '000100', 'name': 'TCL科技', 'data_mode': 'real_corpus'})
    _add_verified_period(store, '000100', '2023FY', 100, 110, 20)
    _add_verified_period(store, '000100', '2024FY', 125, 88, 30)
    record = store.get('financial_metrics', '000100-2024FY-net_profit')
    store.put('financial_metrics', {**record, 'extraction_status': 'machine_extracted'})
    response = TestClient(app).get('/api/v1/companies/000100/financial-analysis?from_period=2023FY&to_period=2024FY')
    assert response.status_code == 200
    result = response.json()
    assert result['status'] == 'needs_review'
    assert result['classification'] == '无法判断'


def test_analysis_endpoint_rejects_metric_page_that_differs_from_evidence_page():
    app = create_app(database_url='sqlite://', data_mode='empty')
    store = app.state.store
    store.put('companies', {'id': '000100', 'code': '000100', 'name': 'TCL科技', 'data_mode': 'real_corpus'})
    _add_verified_period(store, '000100', '2023FY', 100, 110, 20)
    _add_verified_period(store, '000100', '2024FY', 125, 88, 30)
    record = store.get('financial_metrics', '000100-2024FY-net_profit')
    store.put('financial_metrics', {**record, 'page': 999})
    result = TestClient(app).get('/api/v1/companies/000100/financial-analysis?from_period=2023FY&to_period=2024FY').json()
    assert result['status'] == 'needs_review'
    assert 'evidence_id' in result['reason'] or 'missing' in result['reason']


def test_multi_year_charts_keep_verified_annual_points_and_missing_period_gaps():
    app = create_app(database_url='sqlite://', data_mode='empty')
    store = app.state.store
    store.put('companies', {'id': '000100', 'code': '000100', 'name': 'TCL科技', 'data_mode': 'real_corpus'})
    _add_verified_period(store, '000100', '2022FY', 80, 70, 10)
    _add_verified_period(store, '000100', '2023FY', 100, 110, 20)
    _add_verified_period(store, '000100', '2024FY', 125, 88, 30)
    response = TestClient(app).get('/api/v1/companies/000100/financial-analysis?from_period=2022FY&to_period=2024FY')
    result = response.json()
    assert result['status'] == 'completed'
    assert [point['period'] for point in result['charts'][1]['series'][0]['points']] == ['2022FY', '2023FY', '2024FY']
    assert result['charts'][1]['series'][0]['points'][1]['value'] == '1.1'
    assert len(result['charts'][0]['series'][0]['points']) == 2


def test_corpus_loader_preserves_financial_verification_metadata(tmp_path):
    app = create_app(database_url='sqlite://', data_mode='empty')
    corpus = tmp_path / 'corpus.jsonl'
    corpus.write_text('{"id":"f1","company_code":"000100","company_name":"TCL","sha256":"' + 'c' * 64 + '","report_period":"2024FY","report_type":"annual","pages":[{"page":8,"text":"经营现金流 100"}],"metrics":[{"metric":"operating_cash_flow","value":"100","period":"2024FY","unit":"CNY","statement_scope":"consolidated","page":8,"excerpt":"经营现金流 100","extraction_status":"human_verified","source_ids":["f1-p8-s0"]}]}', encoding='utf-8')
    load_corpus(app.state.store, corpus)
    metric = app.state.store.all('financial_metrics')[0]
    assert metric['statement_scope'] == 'consolidated'
    assert metric['document_sha256'] == 'c' * 64
    assert metric['page'] == 8
    assert metric['extraction_status'] == 'human_verified'


def test_five_pilot_companies_without_verified_financial_values_never_get_numeric_conclusions():
    pilots = [('000100', 'TCL科技'), ('000157', '中联重科'), ('000425', '徐工机械'),
              ('000528', '柳工'), ('000725', '京东方A')]
    app = create_app(database_url='sqlite://', data_mode='empty')
    for code, name in pilots:
        app.state.store.put('companies', {'id':code,'code':code,'name':name,'data_mode':'real_corpus'})
    with TestClient(app) as client:
        for code, _ in pilots:
            result = client.get(f'/api/v1/companies/{code}/financial-analysis?from_period=2023FY&to_period=2024FY').json()
            assert result['status'] == 'needs_review'
            assert result['classification'] == '无法判断'
            assert result['metrics'] == {}

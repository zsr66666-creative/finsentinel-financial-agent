import os
import logging
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import AnalysisRequest, FeedbackRequest, IngestionRequest, EvalRequest, RiskEvaluationRequest, EventEvaluationRequest
from app.seed import seed
from app.store import Store
from app.tools import Tools
from app.workflow import run_workflow
from app.financial_calculations import (
    calc_cash_flow_quality,
    calc_growth,
    calc_gross_margin,
    calc_inventory_turnover,
    calc_receivables_turnover,
)
from app.risk_rules import evaluate_event_rule, evaluate_rules
from app.retrieval import search_chunks
from app.evaluation import recall_at_k
from app.review import next_alert_status, validate_feedback


def now():
    return datetime.now(timezone.utc).isoformat()


def envelope(items):
    return {'items':items,'total':len(items)}


def _metric_response(store, metric, mode):
    evidence_ids = metric.get('source_ids', metric.get('source_evidence_ids', []))
    evidence = store.get('evidence_spans', evidence_ids[0]) if evidence_ids else None
    filing_id = metric.get('filing_id', metric.get('document_id'))
    filing = store.get('filings', filing_id) if filing_id else None
    return {
        **metric,
        'company': {'ticker': metric.get('company_id'), 'name': (store.get('companies', metric.get('company_id')) or {}).get('name')},
        'source_page': metric.get('source_page', metric.get('page')) or (evidence or {}).get('page_no', (evidence or {}).get('page')),
        'source_url': metric.get('source_url') or (evidence or {}).get('source_url') or (filing or {}).get('source_url'),
        'data_mode': metric.get('data_mode', mode),
    }


def create_app(database_url=None, data_mode=None):
    url = database_url or os.getenv('DATABASE_URL','sqlite:///./finsentinel.db')
    mode = data_mode or os.getenv('DATA_MODE','synthetic_demo')
    store = Store(url)
    if mode == 'synthetic_demo':
        seed(store)
    elif mode == 'real_corpus' and os.getenv('CORPUS_PATH'):
        from app.corpus import load_corpus
        load_corpus(store,os.environ['CORPUS_PATH'])
    tools = Tools(store)
    request_stats = {'total': 0, 'errors': 0, 'total_ms': 0.0}
    recent_requests = deque(maxlen=50)
    latency_samples = deque(maxlen=500)
    status_counts = {}
    logger = logging.getLogger('finsentinel.api')

    def record_request(method, path, status_code, elapsed_ms):
        request_stats['total'] += 1
        request_stats['total_ms'] += elapsed_ms
        if status_code >= 400:
            request_stats['errors'] += 1
        latency_samples.append(elapsed_ms)
        status_key = str(status_code)
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        recent_requests.append({'method': method, 'path': path, 'status_code': status_code, 'duration_ms': elapsed_ms})

    @asynccontextmanager
    async def lifespan(app):
        yield
        store.close()

    app = FastAPI(title='FinSentinel API',version='0.1.0',lifespan=lifespan,description='Evidence-first finance research workbench. Synthetic fixtures are explicitly labeled.')
    app.state.store = store
    app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:3000').split(','),allow_methods=['GET','POST'],allow_headers=['Content-Type'])

    @app.middleware('http')
    async def request_observability(request: Request, call_next):
        started = perf_counter()
        request.state.observability_started = started
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            record_request(request.method, request.url.path, 500, elapsed_ms)
            logger.exception('%s %s 500 %.2fms', request.method, request.url.path, elapsed_ms)
            raise
        elapsed_ms = round((perf_counter() - started) * 1000, 2)
        record_request(request.method, request.url.path, response.status_code, elapsed_ms)
        logger.info('%s %s %s %.2fms', request.method, request.url.path, response.status_code, elapsed_ms)
        response.headers['X-Process-Time-Ms'] = str(elapsed_ms)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    def require(table, key):
        item = store.get(table,key)
        if not item:
            raise HTTPException(404, f'{table} record not found')
        return item

    @app.get('/health')
    def health():
        return {'status':'ok','data_mode':mode,'model':'deterministic-demo','database':'connected'}

    @app.get('/api/v1/observability')
    def observability(request: Request):
        # Include this successful snapshot request in the response.  The
        # middleware records it after the handler returns, so reading the
        # counters directly here otherwise produces an off-by-one snapshot.
        current_ms = round((perf_counter() - getattr(request.state, 'observability_started', perf_counter())) * 1000, 2)
        total = request_stats['total'] + 1
        total_ms = request_stats['total_ms'] + current_ms
        samples = sorted([*latency_samples, current_ms])
        current_status_counts = dict(status_counts)
        current_status_counts['200'] = current_status_counts.get('200', 0) + 1
        p95_index = max(0, int(len(samples) * 0.95 + 0.9999) - 1) if samples else 0
        return {
            'requests_total': total,
            'errors_total': request_stats['errors'],
            'error_rate': round(request_stats['errors'] / total, 4) if total else 0.0,
            'avg_duration_ms': round(total_ms / total, 2) if total else 0.0,
            'p95_duration_ms': samples[p95_index] if samples else 0.0,
            'max_duration_ms': samples[-1] if samples else 0.0,
            'sample_size': len(samples),
            'status_counts': current_status_counts,
            'recent_requests': [*list(recent_requests), {'method': request.method, 'path': request.url.path, 'status_code': 200, 'duration_ms': current_ms}],
            'retention': 50,
            'latency_retention': 500,
        }

    @app.get('/api/v1/companies')
    def companies():
        return envelope(store.all('companies'))

    @app.get('/api/v1/companies/{company_id}')
    def company(company_id: str):
        return require('companies',company_id)

    @app.get('/api/v1/companies/{company_id}/metrics')
    def metrics(company_id: str, period: str | None = None):
        require('companies',company_id)
        rows = [m for m in store.all('financial_metrics') if m['company_id']==company_id and (period is None or m['period']==period)]
        if not rows:
            raise HTTPException(404, 'financial metrics not found')
        return envelope([_metric_response(store, m, mode) for m in rows])

    @app.get('/api/v1/evidence/{evidence_id}')
    def evidence(evidence_id: str):
        item = require('evidence_spans', evidence_id)
        document_id = item.get('filing_id') or item.get('document_id')
        document = store.get('filings', document_id) if document_id else None
        return {
            'id': item['id'],
            'company_id': item.get('company_id'),
            'document_id': document_id,
            'page_no': item.get('page_no', item.get('page')),
            'text': item.get('text', ''),
            'source_url': item.get('source_url') or (document or {}).get('source_url'),
            'period': item.get('period'),
            'data_mode': item.get('data_mode', mode),
        }

    @app.get('/api/v1/evidence/search')
    def search_evidence(company_id: str | None = None, period: str | None = None, document_type: str | None = None, query: str = '', as_of: str | None = None, top_k: int = 5):
        if not query.strip():
            return {'items': [], 'total': 0, 'retrieval_mode': 'bm25_only', 'warnings': ['empty_query']}
        return search_chunks(store.all('document_chunks') or store.all('evidence_spans'), query, company_id, period, document_type, as_of, top_k)

    @app.get('/api/v1/companies/{company_id}/metrics/{metric}/growth')
    def metric_growth(company_id: str, metric: str, current_period: str, previous_period: str):
        company = require('companies', company_id)
        rows = [m for m in store.all('financial_metrics') if m.get('company_id') == company_id and m.get('metric') == metric]
        current = next((m for m in rows if m.get('period') == current_period), None)
        previous = next((m for m in rows if m.get('period') == previous_period), None)
        if not current or not previous:
            raise HTTPException(404, 'current or previous metric not found')
        if current.get('unit') != previous.get('unit'):
            raise HTTPException(422, 'current and previous units must match')
        try:
            growth = calc_growth(current.get('value'), previous.get('value'))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        formula = f"({current['value']} - {previous['value']}) / {previous['value']} × 100"
        return {
            'company': {'ticker': company.get('ticker', company.get('code')), 'name': company.get('name')},
            'metric': metric,
            'current_period': current_period,
            'previous_period': previous_period,
            'current_value': current['value'],
            'previous_value': previous['value'],
            'growth': str(growth.quantize(__import__('decimal').Decimal('0.01'))),
            'unit': '%',
            'formula': formula,
            'source_ids': current.get('source_ids', []) + previous.get('source_ids', []),
            'data_mode': current.get('data_mode', mode),
        }

    @app.get('/api/v1/companies/{company_id}/financial-ratios')
    def financial_ratios(
        company_id: str,
        revenue: str | None = None,
        cost: str | None = None,
        opening_receivables: str | None = None,
        closing_receivables: str | None = None,
        opening_inventory: str | None = None,
        closing_inventory: str | None = None,
        operating_cash_flow: str | None = None,
        consolidated_net_profit: str | None = None,
    ):
        require('companies', company_id)
        result = {'company_id': company_id, 'ratios': {}}
        def add(name, formula, value):
            result['ratios'][name] = {'value': str(value), 'formula': formula, 'status': 'calculated'}
        try:
            if revenue is not None and cost is not None:
                add('gross_margin', '(revenue - cost) / revenue × 100', calc_gross_margin(revenue, cost))
            if all(v is not None for v in (revenue, opening_receivables, closing_receivables)):
                add('receivables_turnover', 'revenue / average(opening_receivables, closing_receivables)', calc_receivables_turnover(revenue, opening_receivables, closing_receivables))
            if all(v is not None for v in (cost, opening_inventory, closing_inventory)):
                add('inventory_turnover', 'cost / average(opening_inventory, closing_inventory)', calc_inventory_turnover(cost, opening_inventory, closing_inventory))
            if operating_cash_flow is not None and consolidated_net_profit is not None:
                add('cash_flow_quality', 'operating_cash_flow / consolidated_net_profit', calc_cash_flow_quality(operating_cash_flow, consolidated_net_profit))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return result

    @app.get('/api/v1/alerts')
    def alerts(company_id: str | None = None, status: str | None = None, severity: str | None = None):
        return envelope([a for a in store.all('alerts') if (not company_id or a['company_id']==company_id) and (not status or a['status']==status) and (not severity or a['severity']==severity)])

    @app.post('/api/v1/alerts/evaluate', status_code=201)
    def evaluate_alerts(request: RiskEvaluationRequest):
        require('companies', request.company_id)
        alerts = evaluate_rules(request.metrics, request.company_id, request.period, request.evidence_ids)
        for alert in alerts:
            store.put('alerts', alert)
        return envelope(alerts)

    @app.post('/api/v1/alerts/events/evaluate', status_code=201)
    def evaluate_event(request: EventEvaluationRequest):
        require('companies', request.company_id)
        alert = evaluate_event_rule(request.event_type, request.company_id, request.period, request.evidence_ids, event_date=request.event_date, amount=request.amount, description=request.description)
        if alert is None:
            return envelope([])
        store.put('alerts', alert)
        return envelope([alert])

    @app.get('/api/v1/alerts/{alert_id}')
    def alert(alert_id: str):
        item = require('alerts',alert_id)
        runs = [r for r in store.all('analysis_runs') if r['company_id']==item['company_id']]
        return {**item,'evidence':[require('evidence_spans',eid) for eid in item['evidence_ids']], 'agent_steps':runs[-1]['agent_steps'] if runs else [],'tool_calls':runs[-1]['tool_calls'] if runs else [],'feedback':[f for f in store.all('feedback') if f['alert_id']==alert_id]}

    @app.post('/api/v1/analysis/runs',status_code=201)
    def create_run(request: AnalysisRequest):
        company = require('companies',request.company_id)
        run_id, started = str(uuid4()), perf_counter()
        try:
            state = run_workflow(store,tools,request.company_id,request.question,request.period,request.mode)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        run = {'id':run_id,'run_id':run_id,'company_id':request.company_id,'company_name':company['name'],'question':request.question,'period':request.period,'mode':request.mode,'status':'completed' if state.verification['status']=='passed' else 'needs_review','summary':state.summary,'metrics':state.metrics,'evidence':state.evidence,'agent_steps':state.steps,'tool_calls':state.tool_calls,'verification':state.verification,'prompt_version':'evidence-v1','model_version':'deterministic-demo-v1','token_usage':0,'cost_usd':0.0,'duration_ms':round((perf_counter()-started)*1000,2),'created_at':now(),'data_mode':company['data_mode'],'human_review_required':True}
        store.put('analysis_runs',run)
        for step in state.steps:
            store.put('agent_steps',{**step,'run_id':run_id})
        for call in state.tool_calls:
            store.put('tool_calls',{**call,'id':str(uuid4()),'run_id':run_id})
        return run

    @app.get('/api/v1/analysis/runs/{run_id}')
    def get_run(run_id: str):
        return require('analysis_runs',run_id)

    @app.post('/api/v1/alerts/{alert_id}/feedback',status_code=201)
    def feedback(alert_id: str, request: FeedbackRequest):
        item = require('alerts', alert_id)
        existing = next((f for f in store.all('feedback') if request.idempotency_key and f.get('idempotency_key') == request.idempotency_key), None)
        if existing:
            return existing
        try:
            validate_feedback(request.action, reason=request.reason, comment=request.comment, modification=request.modification)
            next_status = next_alert_status(item.get('status', 'pending'), request.action)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        fid, case_id = str(uuid4()), None
        if request.action != 'confirm':
            case_id = f'feedback-{fid}'
        candidate = {'id':case_id,'company_id':item['company_id'],'question':item['title'],'source':'human_feedback','status':'pending_review','error_type':request.error_type,'comment':request.comment,'reason':request.reason,'modification':request.modification,'alert_id':alert_id} if case_id else None
        record = {'id':fid,'alert_id':alert_id,**request.model_dump(),'regression_case_id':case_id,'created_at':now(),'original_status':item.get('status')}
        store.feedback_transaction(feedback=record, alert={**item,'status':next_status}, candidate=candidate)
        return record
    @app.get('/api/v1/alerts/{alert_id}/feedback')
    def alert_feedback(alert_id: str):
        require('alerts', alert_id)
        items = [f for f in store.all('feedback') if f['alert_id'] == alert_id]
        return envelope(items)

    @app.get('/api/v1/review/candidates')
    def review_candidates():
        return envelope([c for c in store.all('eval_cases') if c.get('status') == 'pending_review'])
    @app.get('/api/v1/evals/summary')
    def eval_summary():
        cases = store.all('eval_cases')
        runs = store.all('eval_runs')
        return {'golden_case_count':len([c for c in cases if c.get('status')=='approved']),'pending_regression_cases':len([c for c in cases if c.get('status')=='pending_review']),'latest_run':sorted(runs,key=lambda r:r['created_at'])[-1] if runs else None,'runs':runs,'data_mode':mode,'measured':bool(runs),'targets':{'numeric_accuracy':0.98,'citation_coverage':0.95,'recall_at_5':0.90,'p95_latency_ms':12000},'notice':'演示评测仅验证 synthetic fixtures；不代表真实财报或 LLM 效果。'}

    @app.post('/api/v1/evals/runs',status_code=201)
    def evaluate(request: EvalRequest):
        cases = [c for c in store.all('eval_cases') if c.get('status')=='approved']
        correct, citations, recall, timings = 0,0,0,[]
        for case in cases:
            started = perf_counter()
            result = tools.get_metric(case['company_id'],case['metric'],case['period'])
            correct += abs(result['value']-case['expected_value'])<=case['tolerance']
            citations += all(store.get('evidence_spans',s) for s in result['source_ids'])
            retrieved = tools.search_evidence(case['company_id'],None,None,case['metric'],limit=5)
            recall += set(case['required_evidence_ids']).issubset(retrieved['source_ids'])
            timings.append((perf_counter()-started)*1000)
        n = len(cases)
        record = {'id':str(uuid4()),'created_at':now(),'mode':request.mode,'model_version':'deterministic-demo-v1','case_count':n,'metrics':{'numeric_accuracy':correct/n if n else None,'citation_coverage':citations/n if n else None,'recall_at_5':recall/n if n else None,'p95_latency_ms':round(sorted(timings)[max(0,int(len(timings)*.95)-1)],2) if n else None},'data_mode':mode,'scope':'tool-and-lexical-retrieval fixture checks; not a language-model benchmark'}
        store.put('eval_runs',record)
        return record

    @app.post('/api/v1/admin/ingestion/jobs',status_code=202)
    def ingestion(request: IngestionRequest):
        for code in request.company_ids:
            require('companies',code)
        record = {'id':str(uuid4()),'status':'completed','mode':request.mode,'company_ids':request.company_ids,'created_at':now(),'documents_processed':0,'data_mode':mode,'message':'Local fixture validation completed; no external documents downloaded.'}
        store.put('ingestion_jobs',record)
        return record

    @app.get('/api/v1/data-quality')
    @app.get('/api/v1/data/quality')
    def quality():
        values = store.all('financial_metrics')
        return {'data_mode':mode,'company_count':len(store.all('companies')),'filing_count':len(store.all('filings')),'metric_count':len(values),'evidence_count':len(store.all('evidence_spans')),'missing_source_count':sum(not m['source_ids'] for m in values),'jobs':store.all('ingestion_jobs'),'sources':store.all('filings')[:20]}

    return app


app = create_app()




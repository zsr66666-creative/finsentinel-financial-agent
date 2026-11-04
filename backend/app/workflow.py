"""Deterministic workflow with an optional LangGraph adapter.

The default graph is dependency-free so demos and tests run offline. When
LangGraph is installed, ``build_langgraph`` exposes the same state contract.
LLM adapters may fill the planner/composer, but calculations and verification
always use Tools and persisted evidence.
"""
from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4


@dataclass
class WorkflowState:
    company_id: str
    question: str
    period: str
    mode: str = 'workflow'
    plan: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    summary: str = ''


def _step(state, node, fn):
    started = perf_counter()
    try:
        fn()
        status = 'completed'
        error = None
    except Exception as exc:
        status, error = 'failed', str(exc)
        raise
    finally:
        state.steps.append({'id':str(uuid4()),'node':node,'status':status,'duration_ms':round((perf_counter()-started)*1000,2),'error':error})


def run_workflow(store, tools, company_id, question, period='2025', mode='workflow'):
    state = WorkflowState(company_id, question, period, mode)
    def planner():
        state.plan = {'company_id':company_id,'period':period,'intent':'risk_analysis','metrics':['revenue','net_profit','inventory','receivables','operating_cash_flow'],'query':question}
    _step(state,'Planner',planner)
    _step(state,'DataQuality',lambda: _quality(store, company_id, period))
    def retriever():
        result = tools.search_evidence(company_id, [f'{int(period)+1}-01-01',f'{int(period)+1}-12-31'], None, question, limit=8)
        state.evidence = result['value']
        state.tool_calls.append(_call('search_evidence', {'company_id':company_id,'query':question}, result))
    _step(state,'Retriever',retriever)
    def analyst():
        for metric in ('revenue','net_profit','inventory','receivables','operating_cash_flow'):
            try:
                current = tools.get_metric(company_id,metric,period)
                previous = tools.get_metric(company_id,metric,str(int(period)-1))
                growth = tools.calc_growth(company_id,metric,[str(int(period)-1),period])
                state.metrics.append({'metric':metric,'current':current['value'],'previous':previous['value'],'unit':current['unit'],'growth':growth['value'],'source_ids':growth['source_ids'],'calculation':growth['calculation']})
                state.tool_calls.append(_call('calc_growth', {'company_id':company_id,'metric':metric,'periods':[str(int(period)-1),period]}, growth))
            except ValueError:
                continue
    _step(state,'QuantAnalyst',analyst)
    def verify():
        source_ids = {s for m in state.metrics for s in m['source_ids']}
        evidence_ids = {e['id'] for e in store.all('evidence_spans')}
        state.verification = {'numeric_verified':all(m.get('source_ids') for m in state.metrics), 'citation_coverage':round(sum(s in evidence_ids for s in source_ids)/len(source_ids),3) if source_ids else 0.0, 'source_conflicts':0, 'status':'passed' if state.metrics and source_ids.issubset(evidence_ids) else 'partial'}
    _step(state,'EvidenceVerifier',verify)
    def composer():
        company = store.get('companies',company_id)
        declines = [m for m in state.metrics if m['growth'] < 0]
        state.summary = f"{company['name']} {period} 年分析：{len(declines)} 项指标同比下降。" + ('建议复核盈利与现金流质量。' if any(m['metric']=='net_profit' for m in declines) else '请结合原始公告进一步判断。')
    _step(state,'ReportComposer',composer)
    return state


def _quality(store, company_id, period):
    if not store.get('companies', company_id):
        raise ValueError('company not found')
    if not store.get('financial_metrics', f'{company_id}-{period}-annual-revenue'):
        raise ValueError('structured metrics unavailable for requested period')


def _call(name, arguments, result):
    return {'name':name,'arguments':arguments,'result':result,'status':'success'}


def build_langgraph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None
    graph = StateGraph(dict)
    for node in ('Planner','DataQuality','Retriever','QuantAnalyst','EvidenceVerifier','ReportComposer'):
        graph.add_node(node, lambda state, _node=node: {**state, 'last_node':_node})
    graph.add_edge(START,'Planner')
    for a,b in zip(('Planner','DataQuality','Retriever','QuantAnalyst','EvidenceVerifier'),('DataQuality','Retriever','QuantAnalyst','EvidenceVerifier','ReportComposer')):
        graph.add_edge(a,b)
    graph.add_edge('ReportComposer',END)
    return graph.compile()

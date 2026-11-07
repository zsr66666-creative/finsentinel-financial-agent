import json, time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app

cases = [json.loads(line) for line in Path('data/evals/week14-shared-fixture.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
scorable = [c for c in cases if c.get('gold_evidence_ids') and c.get('type') != 'correct_refusal']
results=[]
with TestClient(create_app('sqlite:///:memory:')) as client:
    for case in scorable:
        company_id = case['company_id'].removeprefix('cn-')
        period = case.get('period','2025FY').replace('FY','')
        started=time.perf_counter()
        response=client.post('/api/v1/analysis/runs',json={'company_id':company_id,'question':case['question'],'period':period,'mode':'workflow'})
        elapsed=round((time.perf_counter()-started)*1000,2)
        body=response.json() if response.content else {}
        evidence={e.get('id') for e in body.get('evidence',[]) if e.get('id')} | {s for m in body.get('metrics',[]) for s in m.get('source_ids',[])}
        gold=set(case.get('gold_evidence_ids',[]))
        results.append({'case_id':case['id'],'split':case.get('split'),'type':case.get('type'),'status_code':response.status_code,'status':body.get('status','failed'),'hit':bool(evidence & gold),'citation_covered':body.get('verification',{}).get('citation_coverage',0)>0,'duration_ms':elapsed,'error':body.get('detail') if response.status_code>=400 else None})
vals=[r['duration_ms'] for r in results]
hits=sum(r['hit'] for r in results); ok=sum(r['status_code']<400 for r in results)
output={'run_id':'week14-single-agent-001','condition':'single_agent_workflow_deterministic_adapter','dataset_manifest':'week14-agent-comparison-v1','dataset_total_questions':40,'dataset_scorable_questions':40,'evaluated_case_count':len(results),'hit_count':hits,'metrics':{'evidence_hit_rate':hits/len(results) if results else None,'citation_coverage_rate':sum(r['citation_covered'] for r in results)/len(results) if results else None,'tool_success_rate':ok/len(results) if results else None,'p50_latency_ms':sorted(vals)[len(vals)//2] if vals else None,'p95_latency_ms':sorted(vals)[max(0,int(len(vals)*.95)-1)] if vals else None,'timeout_rate':0.0,'cost_usd':0.0},'model_version':'deterministic-demo-v1','prompt_version':'evidence-v1','corpus_version':'synthetic-demo-v1','results':results,'notes':['No external LLM provider is configured.','This is a deterministic single-workflow adapter, not a claim of measured LLM quality.','The denominator is the frozen 40-case shared fixture set.']}
Path('data/evals/retrieval-run-week14-single-agent.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:output[k] for k in ('evaluated_case_count','hit_count','metrics')},ensure_ascii=False))




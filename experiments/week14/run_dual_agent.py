import json,time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app

cases=[json.loads(x) for x in Path('data/evals/week14-shared-fixture.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
scorable=[c for c in cases if c.get('gold_evidence_ids') and c.get('type') != 'correct_refusal']
rows=[]
with TestClient(create_app('sqlite:///:memory:')) as client:
    for case in scorable:
        company=case['company_id'].removeprefix('cn-'); period=case.get('period','2025FY').replace('FY','')
        t0=time.perf_counter(); response=client.post('/api/v1/analysis/runs',json={'company_id':company,'question':case['question'],'period':period,'mode':'workflow'}); analysis_ms=(time.perf_counter()-t0)*1000
        body=response.json() if response.content else {}; evidence={e.get('id') for e in body.get('evidence',[]) if e.get('id')} | {s for m in body.get('metrics',[]) for s in m.get('source_ids',[])}; gold=set(case['gold_evidence_ids']); comparable=bool(evidence & gold)
        t1=time.perf_counter(); source_ids={s for m in body.get('metrics',[]) for s in m.get('source_ids',[])}; citation_ok=bool(source_ids) and body.get('verification',{}).get('citation_coverage',0)>=1.0; review_ms=(time.perf_counter()-t1)*1000
        status='passed' if comparable and citation_ok else ('not_comparable' if not comparable else 'needs_review')
        rows.append({'case_id':case['id'],'split':case.get('split'),'type':case.get('type'),'analysis_status':body.get('status','failed'),'review_status':status,'gold_evidence_ids':sorted(gold),'returned_evidence_ids':sorted(evidence),'analysis_duration_ms':round(analysis_ms,2),'review_duration_ms':round(review_ms,2),'error':body.get('detail') if response.status_code>=400 else None})
vals=[r['analysis_duration_ms']+r['review_duration_ms'] for r in rows]; comparable=[r for r in rows if r['review_status']!='not_comparable']; hits=sum(r['review_status']=='passed' for r in rows)
out={'run_id':'week14-dual-agent-001','condition':'dual_agent_deterministic_review_adapter','dataset_manifest':'week14-agent-comparison-v1','dataset_total_questions':40,'dataset_scorable_questions':40,'evaluated_case_count':len(rows),'comparable_case_count':len(comparable),'hit_count':hits,'metrics':{'evidence_hit_rate_comparable':(sum(r['review_status']=='passed' for r in comparable)/len(comparable) if comparable else None),'review_pass_rate':hits/len(rows) if rows else None,'p50_latency_ms':round(sorted(vals)[len(vals)//2],2) if vals else None,'p95_latency_ms':round(sorted(vals)[max(0,int(len(vals)*.95)-1)],2) if vals else None,'timeout_rate':0.0,'cost_usd':0.0},'model_version':'deterministic-demo-v1','prompt_version':'evidence-v1','corpus_version':'synthetic-demo-v1','results':rows,'limitations':['No external LLM provider configured.','This shared fixture is intentionally separate from the real PDF golden test set.','This adapter demonstrates independent verification stages, not measured LLM dual-agent quality.']}
Path('data/evals/retrieval-run-week14-dual-agent.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({k:out[k] for k in ('evaluated_case_count','comparable_case_count','hit_count','metrics')},ensure_ascii=False))




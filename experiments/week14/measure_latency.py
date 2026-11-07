import json, time
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app

def measure(client):
    for _ in range(2): client.get('/api/v1/companies/002475/metrics?period=2025')
    values=[]
    for _ in range(10):
        t=time.perf_counter(); client.get('/api/v1/companies/002475/metrics?period=2025'); values.append(round((time.perf_counter()-t)*1000,3))
    ordered=sorted(values)
    return {'samples':10,'p50_latency_ms':ordered[5],'p95_latency_ms':ordered[8],'min_latency_ms':min(values),'max_latency_ms':max(values)}
with TestClient(create_app('sqlite:///:memory:')) as client:
    result={'run_id':'week14-latency-001','hot_request':measure(client),'cold_start':'not measured in-process','cache_hit_status':'not_measured'}
Path('data/evals/retrieval-run-week14-latency.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8'); print(result)

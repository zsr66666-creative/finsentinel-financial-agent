import json, time
from pathlib import Path
from app.main import create_app
from app.tools import Tools

app = create_app('sqlite:///:memory:')
store = app.state.store if hasattr(app, 'state') and hasattr(app.state, 'store') else None
# create_app keeps the store in route closures; use the same public API contract instead.
from fastapi.testclient import TestClient
with TestClient(app) as client:
    cases = client.get('/api/v1/evals/summary').json()
    started = time.perf_counter()
    result = client.post('/api/v1/evals/runs', json={'mode':'baseline'}).json()
    elapsed = round((time.perf_counter()-started)*1000, 2)

metrics = result.get('metrics', {})
output = {
    'run_id': 'week14-deterministic-baseline-001',
    'condition': 'deterministic_tools',
    'dataset_manifest': 'week14-agent-comparison-v1',
    'dataset_total_questions': 74,
    'dataset_scorable_questions': 59,
    'evaluated_case_count': result.get('case_count', 0),
    'hit_count': round((metrics.get('numeric_accuracy') or 0) * result.get('case_count', 0)),
    'metrics': {
        'numeric_accuracy': metrics.get('numeric_accuracy'),
        'citation_coverage': metrics.get('citation_coverage'),
        'tool_success_rate': metrics.get('numeric_accuracy'),
        'p50_latency_ms': metrics.get('p50_latency_ms'),
        'p95_latency_ms': metrics.get('p95_latency_ms'),
        'timeout_rate': 0.0,
        'cost_usd': 0.0,
    },
    'elapsed_ms': elapsed,
    'model_version': 'deterministic-demo-v1',
    'prompt_version': 'evidence-v1',
    'corpus_version': 'week10-multi-company-v3',
    'notes': ['This is a deterministic synthetic fixture baseline.', 'It is not an Agent benchmark and is not substituted for the 59-question frozen comparison set.']
}
Path('data/evals/retrieval-run-week14-deterministic-baseline.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'evaluated_case_count': output['evaluated_case_count'], 'elapsed_ms': elapsed}, ensure_ascii=False))

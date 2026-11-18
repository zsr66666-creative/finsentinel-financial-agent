"""Verify real loopback encoder and optionally the text-search API on ECS."""
import argparse
from contextlib import contextmanager, nullcontext
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter


@contextmanager
def _create_in_process_api_client(database_url=None):
    database_url = database_url or os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError('database_url_required')
    if os.getenv('AUTH_ENABLED', 'false').lower() != 'false':
        raise RuntimeError('in_process_acceptance_requires_isolated_auth_disabled_process')

    backend_root = str(Path(__file__).resolve().parents[1] / 'backend')
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    module_loaded = 'app.main' in sys.modules
    previous_database_url = os.environ.get('DATABASE_URL')
    previous_data_mode = os.environ.get('DATA_MODE')
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    os.environ['DATA_MODE'] = 'real_corpus'
    try:
        from fastapi.testclient import TestClient
        from app import main as main_module
    finally:
        if previous_database_url is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = previous_database_url
        if previous_data_mode is None:
            os.environ.pop('DATA_MODE', None)
        else:
            os.environ['DATA_MODE'] = previous_data_mode

    test_app = main_module.create_app(
        database_url=database_url,
        data_mode='real_corpus',
        create_schema=False,
        read_only=True,
    )
    if test_app.state.auth_enabled:
        test_app.state.store.close()
        raise RuntimeError('in_process_acceptance_auth_must_remain_disabled')
    try:
        with TestClient(test_app) as client:
            yield client
    finally:
        test_app.state.store.close()
        if not module_loaded:
            main_module.app.state.store.close()


def _run_acceptance(args, session, api_client=None):
    reference = json.loads((Path(args.model_dir) / 'reference.json').read_text(encoding='utf-8'))
    health = session.get('http://127.0.0.1:8081/health', timeout=10)
    health.raise_for_status()
    assert health.json()['model'] == reference['model'] + '@' + reference['revision']
    observations = []
    for question, expected in zip(reference['questions'][:4], reference['vectors'][:4]):
        started = perf_counter()
        response = session.post('http://127.0.0.1:8081/encode', json={'query': question}, timeout=15)
        response.raise_for_status()
        result = response.json()
        assert result['model'] == health.json()['model']
        vector = result['vector']
        assert len(vector) == 512 and all(type(v) in (int, float) and math.isfinite(v) for v in vector)
        assert 0.99 <= sum(v*v for v in vector) <= 1.01
        delta = max(abs(a-b) for a, b in zip(vector, expected))
        assert delta < 0.0001, delta
        row = dict(question=question, max_abs_error=delta, encoding_ms=result['encoding_ms'], http_wall_ms=round((perf_counter()-started)*1000, 3))
        if api_client is not None or args.api_url or args.vector_api_url:
            payload = dict(query=question, company_code='002475', period='2026H1', top_k=5)
            route = 'text' if args.api_url or api_client is not None else 'vector'
            if route == 'vector':
                payload.update(vector=vector, model=result['model'])
            if api_client is not None:
                response = api_client.post('/api/v1/evidence/search/text', json=payload, timeout=20)
            else:
                base = args.api_url or args.vector_api_url
                response = session.post(base.rstrip('/') + '/api/v1/evidence/search/' + route, json=payload, timeout=20)
            response.raise_for_status()
            body = response.json()
            assert body['retrieval_mode'] == 'bm25_vector_rrf' and body['warnings'] == []
            assert body['items']
            if args.api_url:
                assert body['answer_status'] == 'candidates_only'
                assert body['model'] == health.json()['model']
            assert all(item['provenance']['company_code'] == '002475' and item['provenance']['period'] == '2026H1' for item in body['items'])
            row['ids'] = [item['chunk_id'] for item in body['items']]
            # Receivables questions have known source IDs; board declaration is
            # only a transport/parity case in the tiny cloud corpus, not a gold.
            gold = '002475-2026H1-p60-s20' if '合并' in question else '002475-2026H1-p63-s4'
            if '应收' in question or '销售货款' in question:
                assert gold in row['ids'], (question, row['ids'])
        observations.append(row)
    bad = session.post('http://127.0.0.1:8081/encode', json={'query': ' '}, timeout=10)
    assert bad.status_code == 422
    if api_client is not None:
        bad = api_client.post('/api/v1/evidence/search/text', json={'query':' ', 'company_code':'002475','period':'2026H1'},timeout=10)
        assert bad.status_code == 422
    elif args.api_url:
        bad = session.post(args.api_url.rstrip('/') + '/api/v1/evidence/search/text', json={'query':' ', 'company_code':'002475','period':'2026H1'},timeout=10)
        assert bad.status_code == 422
    if api_client is not None and args.comparison_query:
        comparison = api_client.post('/api/v1/evidence/compare', json={'question': args.comparison_query}, timeout=15)
        comparison.raise_for_status()
        body = comparison.json()
        assert body['status'] == 'supported' and body['claim_true'] is True
    report = dict(status='passed', encoder=health.json(), observations=observations,
                  retrieval_path='in_process_text_api' if api_client is not None else 'text_api' if args.api_url else 'existing_vector_api' if args.vector_api_url else 'encoder_only',
                  limitations=['Known-source development smoke checks, not a held-out benchmark', 'No full-corpus coverage or financial answer correctness claim'])
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    import requests
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--api-url')
    parser.add_argument('--host-header')
    parser.add_argument('--vector-api-url', help='Local assessment only: existing remote vector API')
    parser.add_argument('--in-process-api', action='store_true')
    parser.add_argument('--database-url')
    parser.add_argument('--comparison-query')
    args = parser.parse_args()
    if sum(bool(value) for value in (args.api_url, args.vector_api_url, args.in_process_api)) > 1:
        parser.error('choose only one API acceptance mode')
    if args.database_url:
        parser.error('--database-url is not accepted; use the isolated process DATABASE_URL')

    session = requests.Session()
    session.trust_env = False
    if args.host_header:
        session.headers['Host'] = args.host_header
    api_context = _create_in_process_api_client() if args.in_process_api else nullcontext(None)
    with api_context as api_client:
        _run_acceptance(args, session, api_client)


if __name__ == '__main__':
    main()

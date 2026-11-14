"""Verify real loopback encoder and optionally the text-search API on ECS."""
import argparse
import json
import math
from pathlib import Path
from time import perf_counter


def main():
    import requests
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--api-url')
    parser.add_argument('--host-header')
    parser.add_argument('--vector-api-url', help='Local assessment only: existing remote vector API')
    args = parser.parse_args()
    reference = json.loads((Path(args.model_dir) / 'reference.json').read_text(encoding='utf-8'))
    session = requests.Session()
    session.trust_env = False
    if args.host_header:
        session.headers['Host'] = args.host_header
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
        if args.api_url or args.vector_api_url:
            payload = dict(query=question, company_code='002475', period='2026H1', top_k=5)
            base = args.api_url or args.vector_api_url
            route = 'text' if args.api_url else 'vector'
            if not args.api_url:
                payload.update(vector=vector, model=result['model'])
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
    if args.api_url:
        bad = session.post(args.api_url.rstrip('/') + '/api/v1/evidence/search/text', json={'query':' ', 'company_code':'002475','period':'2026H1'},timeout=10)
        assert bad.status_code == 422
    report = dict(status='passed', encoder=health.json(), observations=observations,
                  retrieval_path='text_api' if args.api_url else 'existing_vector_api' if args.vector_api_url else 'encoder_only',
                  limitations=['Known-source development smoke checks, not a held-out benchmark', 'No full-corpus coverage or financial answer correctness claim'])
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

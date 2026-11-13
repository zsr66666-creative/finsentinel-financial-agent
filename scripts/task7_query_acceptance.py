"""Local real-query encoding and remote persisted-corpus development checks.

No corpus vectors are copied or substituted for query embeddings. Private query
packages and raw responses stay in ignored outputs/. Not a held-out benchmark.
"""
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter

from scripts.vector_batch import MODEL, REVISION
from scripts.vector_query import PREFIX

PDF_SHA256 = '841a3271cddd0e0e6bf9d60e39bda69fa48de13c67300c313395d849bddfa588'
CASES = [
    ('parent-direct', '立讯精密2026年半年度报告母公司应收账款是多少？', '002475-2026H1-p63-s4'),
    ('parent-paraphrase', '想了解立讯精密母公司期末尚未收回的销售货款余额，应查哪段财报？', '002475-2026H1-p63-s4'),
    ('consolidated-direct', '立讯精密2026年半年度报告合并应收账款是多少？', '002475-2026H1-p60-s20'),
    ('consolidated-paraphrase', '立讯精密集团合并报表中客户欠款的期末余额在哪里披露？', '002475-2026H1-p60-s20'),
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='outputs/task7-queries')
    parser.add_argument('--base-url', help='Optional trusted API origin; omit for local export only')
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    from sentence_transformers import SentenceTransformer
    started = perf_counter()
    model = SentenceTransformer(MODEL, revision=REVISION, local_files_only=True, device='cpu')
    load_ms = round((perf_counter() - started) * 1000, 3)
    started = perf_counter()
    vectors = model.encode([PREFIX + question for _, question, _ in CASES], batch_size=2, normalize_embeddings=True)
    encode_ms = round((perf_counter() - started) * 1000, 3)
    report = dict(model=f'{MODEL}@{REVISION}', dimensions=512, model_load_ms=load_ms,
                  batch_query_encode_ms=encode_ms, split='development_smoke', cases=[],
                  limitations=['Four known-source development queries, not held-out evaluation',
                               'Gold IDs reuse reviewed receivables spans; no broad financial QA claim',
                               'Candidate retrieval does not prove scope or numeric answer correctness',
                               'No negative-case abstention evaluated; no complete-report coverage claim',
                               'Cloud wall latency excludes local model load and query encoding'])
    if args.base_url:
        import requests
        session = requests.Session()
        session.trust_env = False
    for (case_id, question, gold), values in zip(CASES, vectors):
        vector = values.tolist()
        if len(vector) != 512 or not all(__import__('math').isfinite(v) for v in vector):
            raise ValueError('invalid query encoding')
        package = dict(question=question, query_prefix=PREFIX, embedding=vector,
                       model=f'{MODEL}@{REVISION}', company_code='002475', period='2026H1')
        path = out / f'{case_id}.json'
        write_json(path, package)
        row = dict(id=case_id, question=question, gold_evidence_ids=[gold],
                   query_package_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if args.base_url:
            started = perf_counter()
            response = session.post(args.base_url.rstrip('/') + '/api/v1/evidence/search/vector',
                                    json=dict(query=question, vector=vector, model=package['model'],
                                              company_code='002475', period='2026H1', top_k=20), timeout=30)
            response.raise_for_status()
            body = response.json()
            row['http_wall_ms'] = round((perf_counter() - started) * 1000, 3)
            if body['retrieval_mode'] != 'bm25_vector_rrf' or body['warnings']:
                raise ValueError('vector search degraded: ' + str(body.get('warnings')))
            items = body['items']
            # Current cloud corpus has 14 vectors, so Top-20 is exhaustive. Abort
            # rather than derive biased per-route rankings from a truncated union.
            if len(items) >= 20:
                raise ValueError('corpus grew: need separate full per-route evaluation')
            for item in items:
                provenance = item['provenance']
                if provenance.get('company_code') != '002475' or provenance.get('period') != '2026H1' or provenance.get('document_sha256') != PDF_SHA256:
                    raise ValueError('unexpected scope or PDF fingerprint')
            if gold not in {item['chunk_id'] for item in items}:
                raise ValueError('gold evidence missing from retrieved corpus')
            rankings = {'rrf': [item['chunk_id'] for item in items]}
            for route in ('bm25', 'vector'):
                ranked = sorted((item for item in items if item.get(route + '_rank') is not None), key=lambda item: item[route + '_rank'])
                rankings[route] = [item['chunk_id'] for item in ranked]
            row.update(rankings=rankings, recall_at_5={route: int(gold in ids[:5]) for route, ids in rankings.items()},
                       server_duration_ms=body['duration_ms'], retrieval_mode=body['retrieval_mode'], corpus_candidates=len(items))
            write_json(out / f'{case_id}.response.json', body)
        report['cases'].append(row)
    if args.base_url:
        report['recall_at_5'] = {route: dict(hits=sum(row['recall_at_5'][route] for row in report['cases']), total=len(CASES)) for route in ('bm25', 'vector', 'rrf')}
    write_json(out / 'report.json', report)
    print(json.dumps({key: value for key, value in report.items() if key != 'cases'}, ensure_ascii=False, indent=2))
    print(f'Private files: {out.resolve()}')


if __name__ == '__main__':
    main()

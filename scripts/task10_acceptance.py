"""Verify newly indexed reports, exact source provenance and old Task 9 behavior."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import requests
from sqlalchemy import create_engine, text

from app.online_query import MODEL_ID
from scripts.task9_index import load_chunks
from scripts.task10_acquire import load_reports


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    parser.add_argument('--host-header')
    parser.add_argument('--artifact-root', default='/var/lib/finsentinel/ingestion')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    previous = [sys.executable, '-m', 'scripts.task9_acceptance', '--api-url', args.api_url,
                '--artifact-root', args.artifact_root, '--output', str(Path(args.output).with_name(Path(args.output).stem + '-task9.json'))]
    if args.host_header:
        previous += ['--host-header', args.host_header]
    subprocess.run(previous, check=True, timeout=180)
    engine = create_engine(os.environ['DATABASE_URL'])
    try:
        session = requests.Session()
        session.trust_env = False
        if args.host_header:
            session.headers['Host'] = args.host_header
        def get(path):
            response = session.get(args.api_url + path, timeout=15)
            response.raise_for_status()
            return response.json()
        catalog = get('/api/v1/evidence/scopes')
        assert catalog['model'] == MODEL_ID
        observations = []
        for report in load_reports():
            code, period = report['company_code'], report['report_period']
            chunks = {c['chunk_id']: c for c in load_chunks(engine, report['document_id'], args.artifact_root)}
            with engine.connect() as c:
                rows = c.execute(text('''SELECT chunk_id, provenance FROM document_chunk_embeddings
                    WHERE model=:model AND provenance->>'document_id'=:id'''), dict(model=MODEL_ID, id=report['document_id'])).mappings().all()
            assert {r['chunk_id'] for r in rows} == set(chunks)
            assert all(r['provenance'] == chunks[r['chunk_id']] for r in rows)
            scope = next(s for s in catalog['items'] if (s['company_code'], s['period']) == (code, period))
            assert scope['company_name'] == report['company_name'] and scope['industry'] == report['industry']
            document = next(d for d in scope['documents'] if d['document_id'] == report['document_id'])
            assert document['chunk_count'] == len(chunks) and document['document_sha256'] == report['sha256']
            assert document['pages'] == sorted({c['page'] for c in chunks.values()})
            assert document['total_pages'] == report['total_pages'] and document['coverage_kind'] == 'selected_pages'
            profile = get('/api/v1/companies/' + code)
            assert profile['name'] == report['company_name'] and profile['data_mode'] == 'real_pdf_candidates'
            assert 'metrics' not in profile and 'alerts' not in profile
            assert session.get(args.api_url + '/api/v1/companies/' + code + '/metrics', timeout=15).status_code == 404
            for query in ('营业收入', '应收账款', '经营活动产生的现金流量净额'):
                response = session.post(args.api_url + '/api/v1/evidence/search/text',
                    json=dict(query=query, company_code=code, period=period, top_k=5), timeout=20)
                response.raise_for_status()
                result = response.json()
                assert result['answer_status'] == 'candidates_only' and result['retrieval_mode'] == 'bm25_vector_rrf'
                assert result['items'] and all(item['provenance'] == chunks[item['chunk_id']] for item in result['items'])
                assert any(query in item['provenance']['text'] for item in result['items'])
                observations.append(dict(company_code=code, query=query, pages=[i['provenance']['page'] for i in result['items']],
                                         encoding_ms=result['encoding_ms'], retrieval_ms=result['duration_ms']))
        result = dict(status='passed', reports=load_reports(), observations=observations, task9_regression='passed',
                      limitations=['Selected-page development smoke checks, not a held-out benchmark',
                                   'Business labels are not high-tech certification claims', 'No new adjudicated financial conclusions'])
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

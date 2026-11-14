"""ECS source-backed smoke acceptance, not a held-out retrieval benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import requests
from sqlalchemy import create_engine, text

from app.online_query import MODEL_ID
from scripts.task9_index import load_chunks


ARTIFACT_ID = '05e081ae37a01bc1df83183f2b93c64590d2c2aac6dd4d0c9864743de1b105c4'
PDF_SHA = 'e436b5ab1775cfa05aacb4a16dd8e5c6b89e926ed18a7a55a86728bab6fcb1da'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api-url', default='http://127.0.0.1:8000')
    parser.add_argument('--host-header')
    parser.add_argument('--artifact-root', default='/var/lib/finsentinel/ingestion')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    engine = create_engine(os.environ['DATABASE_URL'])
    try:
        chunks = {chunk['chunk_id']: chunk for chunk in load_chunks(engine, ARTIFACT_ID, args.artifact_root)}
        # All document rows, including those not returned in smoke queries, must retain their source exactly.
        with engine.connect() as c:
            actual = c.execute(text('''SELECT chunk_id, text_sha256, provenance FROM document_chunk_embeddings
                WHERE model=:model AND provenance->>'document_id'=:doc'''), dict(model=MODEL_ID, doc=ARTIFACT_ID)).mappings().all()
        assert len(actual) == len(chunks)
        for row in actual:
            assert row['provenance'] == chunks[row['chunk_id']]
            assert row['text_sha256'] == hashlib.sha256(row['provenance']['text'].encode()).hexdigest()
        session = requests.Session()
        session.trust_env = False
        if args.host_header:
            session.headers['Host'] = args.host_header
        def get(path):
            response = session.get(args.api_url + path, timeout=15)
            response.raise_for_status()
            return response.json()
        def post(path, body):
            response = session.post(args.api_url + path, json=body, timeout=20)
            response.raise_for_status()
            return response.json()
        catalog = get('/api/v1/evidence/scopes')
        assert catalog['model'] == MODEL_ID
        current = next(s for s in catalog['items'] if (s['company_code'], s['period']) == ('002475', '2024FY'))
        document = next(d for d in current['documents'] if d['document_id'] == ARTIFACT_ID)
        assert document['document_sha256'] == PDF_SHA
        assert document['chunk_count'] == len(chunks)
        assert document['pages'] == sorted({p['page'] for p in chunks.values()})
        assert document['coverage_kind'] == 'selected_pages'
        assert any(s['company_code'] == '002475' and s['period'] == '2026H1' for s in catalog['items'])
        observations = []
        for query in ('营业收入', '应收账款', '经营活动产生的现金流量净额'):
            result = post('/api/v1/evidence/search/text', dict(query=query, company_code='002475', period='2024FY', top_k=5))
            assert result['answer_status'] == 'candidates_only' and result['items']
            assert all(item['provenance'] == chunks[item['chunk_id']] for item in result['items'])
            assert any(query in item['provenance']['text'] for item in result['items']), 'known-source smoke keyword missing: ' + query
            observations.append(dict(query=query, ids=[i['chunk_id'] for i in result['items']], encoding_ms=result['encoding_ms'], duration_ms=result['duration_ms']))
        legacy = post('/api/v1/evidence/search/text', dict(query='应收账款', company_code='002475', period='2026H1', top_k=5))
        assert '002475-2026H1-p60-s20' in [i['chunk_id'] for i in legacy['items']]
        assert all(i['provenance']['period'] == '2026H1' for i in legacy['items'])
        empty = post('/api/v1/evidence/search/text', dict(query='应收账款', company_code='999999', period='2024FY', top_k=5))
        assert empty['items'] == []
        comparison = post('/api/v1/evidence/compare', dict(question='立讯精密2026年6月30日母公司应收账款较2025年12月31日是否未增加？'))
        assert comparison['status'] == 'supported' and comparison['claim_true'] is True
        ambiguous = post('/api/v1/evidence/compare', dict(question='立讯精密2026年6月30日应收账款较2025年12月31日是否增加？'))
        assert ambiguous['status'] == 'needs_review' and ambiguous['evidence_ids'] == []
        report = dict(status='passed', model=MODEL_ID, verified_document_chunks=len(chunks), coverage=document,
                      observations=observations, legacy_retrieval='passed', reviewed_comparison='passed',
                      unsupported_scope='empty', limitations=['Known-source development smoke checks, not independent evaluation',
                          'Selected-page index only; missing results do not establish absence of disclosure',
                          'New 2024FY candidates are not adjudicated monetary comparisons'])
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

"""Small private BGE export and transactional pgvector import. No model on server."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from datetime import datetime, timezone

MODEL = 'BAAI/bge-small-zh-v1.5'
REVISION = '7999e1d3359715c523056ef9478215996d62a620'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def validate(package):
    if package['model'] != MODEL or package['revision'] != REVISION:
        raise ValueError('unexpected model/revision')
    seen = set()
    for row in package['rows']:
        if row['chunk_id'] in seen:
            raise ValueError('duplicate chunk id')
        seen.add(row['chunk_id'])
        vector = row['embedding']
        if len(vector) != 512 or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector):
            raise ValueError('invalid vector dimension/value')
        if not 0.99 < sum(x*x for x in vector) < 1.01:
            raise ValueError('vector must be normalized')
        if digest(row['text'].encode('utf-8')) != row['text_sha256']:
            raise ValueError('text hash mismatch')
        if not row['source_url'] or len(row['document_sha256']) != 64 or row['page'] < 1:
            raise ValueError('missing provenance')
    if not seen:
        raise ValueError('empty batch')

def export(args):
    from sentence_transformers import SentenceTransformer
    rows = []
    for path in sorted(Path(args.documents).glob('*.json')):
        doc = json.loads(path.read_text(encoding='utf-8'))
        if doc['id'] != args.document_id:
            continue
        for page in doc['pages']:
            for index, span in enumerate(page.get('spans', [])):
                content = span.get('text', '').strip()
                if len(content) < 40 or len(content) > 350:
                    continue
                rows.append(dict(chunk_id=f"{doc['id']}-p{page['page']}-s{index}",
                    text=content, text_sha256=digest(content.encode('utf-8')),
                    source_url=doc['source_url'], document_sha256=doc['sha256'],
                    document_id=doc['id'], page=page['page'], company_code=doc['company_code'],
                    period=doc['report_period'], source_status='local_copy_not_independently_verified'))
                if len(rows) == 10:
                    break
            if len(rows) == 10:
                break
    if len(rows) != 10:
        raise ValueError('need 10 eligible source spans')
    model = SentenceTransformer(MODEL, revision=REVISION, local_files_only=True, device='cpu')
    vectors = model.encode([r['text'] for r in rows], batch_size=2, normalize_embeddings=True)
    for row, vector in zip(rows, vectors):
        row['embedding'] = vector.tolist()
    package = dict(model=MODEL, revision=REVISION, dimensions=512, rows=rows)
    validate(package)
    target = Path(args.file)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(package, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    target.write_bytes(data)
    print(json.dumps(dict(rows=len(rows), dimensions=512, sha256=digest(data), path=str(target))))

def load(args):
    from sqlalchemy import create_engine, text
    from app.migrations import migrate_vector_up
    data = Path(args.file).read_bytes()
    if digest(data) != args.sha256:
        raise ValueError('package SHA-256 mismatch')
    package = json.loads(data)
    validate(package)
    engine = create_engine(os.environ['DATABASE_URL'])
    if engine.dialect.name != 'postgresql':
        raise ValueError('requires PostgreSQL')
    migrate_vector_up(engine, 512)
    # Provenance is retained beside the vector, not silently discarded.
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE document_chunk_embeddings ADD COLUMN IF NOT EXISTS provenance JSONB'))
        before = conn.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
        for row in package['rows']:
            model = f"{MODEL}@{REVISION}"
            existing = conn.execute(text('SELECT model, text_sha256 FROM document_chunk_embeddings WHERE chunk_id=:id'), {'id':row['chunk_id']}).first()
            if existing and tuple(existing) != (model, row['text_sha256']):
                raise ValueError('existing chunk conflicts; refusing overwrite')
            conn.execute(text('''INSERT INTO document_chunk_embeddings
                (chunk_id, model, dimensions, embedding, text_sha256, created_at, provenance)
                VALUES (:id,:model,512,CAST(:vector AS vector),:sha,:created,CAST(:provenance AS jsonb))
                ON CONFLICT (chunk_id) DO NOTHING'''),
                dict(id=row['chunk_id'], model=model, vector=json.dumps(row['embedding']),
                     sha=row['text_sha256'], created=datetime.now(timezone.utc).isoformat(),
                     provenance=json.dumps({k:v for k,v in row.items() if k!='embedding'},ensure_ascii=False)))
            actual = conn.execute(text('SELECT embedding::text FROM document_chunk_embeddings WHERE chunk_id=:id'), {'id':row['chunk_id']}).scalar_one()
            restored = json.loads(actual)
            if len(restored) != 512 or max(abs(a-b) for a,b in zip(restored,row['embedding'])) > 1e-6:
                raise ValueError('vector readback mismatch')
        after = conn.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
    engine.dispose()
    print(json.dumps(dict(before=before, after=after, added=after-before, verified=len(package['rows']), tolerance=1e-6)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['export','import'])
    parser.add_argument('--file', required=True)
    parser.add_argument('--documents', default='data/derived/documents')
    parser.add_argument('--document-id', default='002475-2026H1')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    export(args) if args.mode == 'export' else load(args)

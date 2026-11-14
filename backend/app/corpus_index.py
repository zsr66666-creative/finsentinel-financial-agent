"""Verified selected-page chunks and atomic fixed-model index publication."""
import hashlib
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import bindparam, text

from app.online_query import MODEL_ID

CHUNKER_VERSION = 'physical-span-320-v1'


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def verify_pdf_text(pdf_path, parsed):
    import fitz
    with fitz.open(pdf_path) as document:
        if document.is_encrypted or len(document) != parsed['total_pages']:
            raise ValueError('PDF page count mismatch')
        for page in parsed['pages']:
            blocks = document[page['page']-1].get_text('blocks', sort=True)
            content = '\n'.join(b[4] for b in blocks if (len(b) <= 6 or b[6] == 0) and b[4].strip())
            if content != page['text']:
                raise ValueError('PDF page text mismatch; reparse with the installed parser before indexing')


def prepare_chunks(artifact, parsed, pdf_path):
    for key in ('sha256', 'company_code', 'report_period', 'report_type'):
        if not artifact.get(key) or artifact[key] != parsed.get(key):
            raise ValueError('artifact metadata mismatch: ' + key)
    identity = sha256(json.dumps([artifact[k] for k in ('company_code', 'report_period', 'report_type', 'sha256')]).encode())
    if artifact['id'] != identity or parsed.get('id') != identity:
        raise ValueError('artifact identity mismatch')
    if sha256(pdf_path.read_bytes()) != artifact['sha256']:
        raise ValueError('PDF checksum mismatch')
    url = parsed.get('final_url') or parsed.get('source_url', '')
    source = urlsplit(url)
    if source.scheme != 'https' or source.hostname != 'static.cninfo.com.cn' or source.username or source.password:
        raise ValueError('unverified official source')
    pages = parsed.get('pages', [])
    total = parsed.get('total_pages')
    numbers = [p['page'] for p in pages]
    if (type(total) is not int or total <= 0 or not pages or len(set(numbers)) != len(numbers)
            or any(type(n) is not int or not 1 <= n <= total for n in numbers)
            or parsed.get('extracted_page_count') != len(pages)):
        raise ValueError('invalid physical page coverage')
    scope = parsed.get('extraction_scope')
    if scope not in ('complete', 'selected_financial_and_risk_pages') or (scope == 'complete' and len(pages) != total):
        raise ValueError('invalid extraction scope')
    acquired_at = parsed.get('acquired_at')
    if not acquired_at or not datetime.fromisoformat(acquired_at).tzinfo:
        raise ValueError('missing acquisition time')
    coverage = dict(kind=scope, pages=sorted(numbers), total_pages=total, indexed_page_count=len(pages))
    chunks = []
    for page in pages:
        content = page['text']
        if sha256(content.encode()) != page['text_sha256']:
            raise ValueError('page text checksum mismatch')
        last_end = 0
        for span in page['spans']:
            start, end = span['start'], span['end']
            if (type(start) is not int or type(end) is not int or not last_end <= start < end <= len(content)
                    or content[start:end] != span['text']):
                raise ValueError('span offset mismatch')
            last_end = end
            for offset in range(start, end, 320):
                stop = min(offset + 320, end)
                value = content[offset:stop]
                if not value.strip():
                    continue
                chunk_id = f'idx1-{identity}-p{page["page"]}-o{offset}-{stop}'
                chunks.append(dict(chunk_id=chunk_id, document_id=identity, company_code=artifact['company_code'],
                    period=artifact['report_period'], report_type=artifact['report_type'], page=page['page'],
                    start=offset, end=stop, text=value, text_sha256=sha256(value.encode()),
                    document_sha256=artifact['sha256'], page_text_sha256=page['text_sha256'], source_url=url,
                    acquired_at=acquired_at, source_status='official_pdf_hash_verified_unreviewed',
                    extraction_method=parsed.get('parser_version', parsed.get('parser', 'unknown')),
                    chunker_version=CHUNKER_VERSION, coverage=coverage))
    if not chunks:
        raise ValueError('no indexable text')
    coverage['extracted_pages'] = sorted(numbers)
    coverage['pages'] = sorted({chunk['page'] for chunk in chunks})
    coverage['indexed_page_count'] = len(coverage['pages'])
    return chunks


def publish_chunks(engine, chunks, vectors):
    if not chunks or len(chunks) != len(vectors) or len({c['chunk_id'] for c in chunks}) != len(chunks):
        raise ValueError('invalid chunk/vector count')
    if len({(c['document_id'], c['chunker_version']) for c in chunks}) != 1:
        raise ValueError('one document per publication required')
    for chunk, vector in zip(chunks, vectors):
        if sha256(chunk['text'].encode()) != chunk['text_sha256']:
            raise ValueError('chunk checksum mismatch')
        if (len(vector) != 512 or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)
                or not .99 <= sum(x*x for x in vector) <= 1.01):
            raise ValueError('invalid document vector')
    is_postgres = engine.dialect.name == 'postgresql'
    with engine.begin() as conn:
        if is_postgres:
            # Serialize this document's publication, including concurrent retries.
            lock = int(sha256(chunks[0]['document_id'].encode())[:15], 16)
            conn.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock})
        query = text('''SELECT chunk_id, model, dimensions, text_sha256, provenance,
            CAST(embedding AS TEXT) AS vector FROM document_chunk_embeddings
            WHERE chunk_id IN :ids OR (provenance->>'document_id'=:doc AND provenance->>'chunker_version'=:version)''')
        rows = conn.execute(query.bindparams(bindparam('ids', expanding=True)), dict(ids=[c['chunk_id'] for c in chunks],
                            doc=chunks[0]['document_id'], version=chunks[0]['chunker_version'])).mappings().all()
        existing = {r['chunk_id']: r for r in rows}
        if existing and set(existing) != {c['chunk_id'] for c in chunks}:
            raise ValueError('document publication conflict')
        for chunk, vector in zip(chunks, vectors):
            row = existing.get(chunk['chunk_id'])
            if row:
                provenance = json.loads(row['provenance']) if isinstance(row['provenance'], str) else row['provenance']
                old_vector = json.loads(row['vector'])
                if (row['model'] != MODEL_ID or row['dimensions'] != 512 or row['text_sha256'] != chunk['text_sha256']
                        or provenance != chunk or len(old_vector) != 512
                        or any(not math.isfinite(a) or abs(a-b) > 1e-5 for a, b in zip(old_vector, vector))):
                    raise ValueError('existing index conflict')
                continue
            vector_sql = 'CAST(:vector AS vector)' if is_postgres else ':vector'
            provenance_sql = 'CAST(:provenance AS jsonb)' if is_postgres else ':provenance'
            conn.execute(text(f'''INSERT INTO document_chunk_embeddings
                (chunk_id, model, dimensions, embedding, text_sha256, created_at, provenance)
                VALUES (:id, :model, 512, {vector_sql}, :sha, :created, {provenance_sql})'''),
                dict(id=chunk['chunk_id'], model=MODEL_ID, vector=json.dumps(vector, allow_nan=False),
                     sha=chunk['text_sha256'], created=datetime.now(timezone.utc).isoformat(),
                     provenance=json.dumps(chunk, ensure_ascii=False, allow_nan=False)))
    return dict(inserted=len(chunks)-len(existing), existing=len(existing), total=len(chunks),
                document_id=chunks[0]['document_id'], coverage=chunks[0]['coverage'])

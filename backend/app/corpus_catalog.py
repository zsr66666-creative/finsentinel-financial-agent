"""A coverage catalog derived exclusively from actually indexed evidence."""
import json

from sqlalchemy import inspect, text

from app.online_query import MODEL_ID


def list_scopes(engine):
    scopes = {}
    if not inspect(engine).has_table('document_chunk_embeddings'):
        return dict(items=[], total=0, model=MODEL_ID)
    with engine.connect() as conn:
        rows = conn.execution_options(stream_results=True).execute(text('''SELECT provenance
            FROM document_chunk_embeddings WHERE model=:model AND dimensions=512'''), {'model': MODEL_ID})
        for row in rows:
            p = json.loads(row.provenance) if isinstance(row.provenance, str) else row.provenance
            if not p or not isinstance(p.get('text'), str) or not p['text'].strip():
                continue
            company, period, page = p.get('company_code'), p.get('period'), p.get('page')
            if not company or not period or type(page) is not int or page < 1:
                continue
            scope = scopes.setdefault((company, period), dict(company_code=company,
                company_name={'002475': '立讯精密'}.get(company, company), period=period, chunk_count=0, documents={}))
            scope['chunk_count'] += 1
            key = (p.get('document_id'), p.get('document_sha256'))
            coverage = p.get('coverage') or {}
            document = scope['documents'].setdefault(key, dict(document_id=key[0], document_sha256=key[1],
                pages=set(), chunk_count=0, source_statuses=set(), total_pages=coverage.get('total_pages'),
                coverage_kind='selected_pages' if coverage else 'indexed_fragments'))
            document['pages'].add(page)
            document['chunk_count'] += 1
            document['source_statuses'].add(p.get('source_status', 'unreviewed'))
    items = []
    for _, scope in sorted(scopes.items()):
        documents = []
        for document in scope['documents'].values():
            document['pages'] = sorted(document['pages'])
            document['source_statuses'] = sorted(document['source_statuses'])
            if document['total_pages'] == len(document['pages']):
                document['coverage_kind'] = 'all_text_pages'
            documents.append(document)
        scope['documents'] = sorted(documents, key=lambda d: (d['document_id'] or '', d['document_sha256'] or ''))
        items.append(scope)
    return dict(items=items, total=len(items), model=MODEL_ID)

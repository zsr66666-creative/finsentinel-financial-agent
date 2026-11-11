"""Exact cosine Top-K over persisted vectors; no embedding model loaded here."""
import json
import math
from datetime import date
from time import perf_counter
from sqlalchemy import text

def search_vectors(engine, vector, *, company_code, period, model, top_k=5, as_of=None):
    if (len(vector) != 512 or any(type(x) not in (float,int) or not math.isfinite(x) for x in vector)
            or sum(x*x for x in vector) <= 0):
        raise ValueError('expected nonzero finite 512-dimensional query')
    if type(top_k) is not int or not 1 <= top_k <= 20:
        raise ValueError('top_k must be 1..20')
    if not company_code or not period or not model:
        raise ValueError('company, period and versioned model are required')
    if as_of:
        date.fromisoformat(as_of)
    statement = text('''SELECT chunk_id, provenance,
        embedding <=> CAST(:vector AS vector) AS distance
        FROM document_chunk_embeddings
        WHERE model = :model AND dimensions = 512
          AND provenance->>'company_code' = :company
          AND provenance->>'period' = :period
          AND (CAST(:as_of AS text) IS NULL OR
              (provenance->>'published_at' IS NOT NULL AND
               provenance->>'published_at' <= :as_of))
        ORDER BY distance ASC, chunk_id ASC LIMIT :limit''')
    started = perf_counter()
    with engine.connect() as conn:
        rows = conn.execute(statement, dict(vector=json.dumps(vector), model=model,
            company=company_code, period=period, as_of=as_of, limit=top_k)).mappings().all()
    items = [dict(chunk_id=r['chunk_id'], cosine_distance=float(r['distance']),
                  cosine_similarity=1-float(r['distance']), **{'provenance':r['provenance']}) for r in rows]
    return dict(items=items, total=len(items), retrieval_mode='pgvector_exact_cosine',
                duration_ms=round((perf_counter()-started)*1000,3),
                warnings=['ranking_is_not_evidence_verification'])

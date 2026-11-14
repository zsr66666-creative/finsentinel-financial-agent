import hashlib
import json

import pytest
from sqlalchemy import create_engine, text

from app.corpus_index import prepare_chunks, publish_chunks
from app.online_query import MODEL_ID


def fixture(tmp_path):
    pdf = tmp_path / 'source.pdf'
    pdf.write_bytes(b'%PDF-test-verified-blob')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    identity = hashlib.sha256(json.dumps(['002475', '2024FY', 'annual', digest]).encode()).hexdigest()
    artifact = dict(id=identity, sha256=digest, company_code='002475', report_period='2024FY', report_type='annual')
    source = '应收账款\n' + '实际披露的原文' * 80
    parsed = dict(id=identity, sha256=digest, company_code='002475', report_period='2024FY', report_type='annual',
                  source_url='https://static.cninfo.com.cn/finalpage/report.PDF', acquired_at='2026-11-12T00:00:00+00:00',
                  total_pages=100, extracted_page_count=1, extraction_scope='selected_financial_and_risk_pages',
                  parser_version='pymupdf-test', pages=[dict(page=60, text=source,
                      text_sha256=hashlib.sha256(source.encode()).hexdigest(), spans=[dict(start=0, end=len(source), text=source)])])
    return artifact, parsed, pdf


def database():
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(text('''CREATE TABLE document_chunk_embeddings (
            chunk_id TEXT PRIMARY KEY, model TEXT, dimensions INTEGER, embedding TEXT,
            text_sha256 TEXT, created_at TEXT, provenance TEXT)'''))
    return engine


def test_chunks_preserve_physical_page_exact_offsets_and_coverage(tmp_path):
    artifact, parsed, pdf = fixture(tmp_path)
    chunks = prepare_chunks(artifact, parsed, pdf)
    assert len(chunks) > 1
    assert ''.join(c['text'] for c in chunks) == parsed['pages'][0]['text']
    for chunk in chunks:
        assert chunk['page'] == 60 and chunk['period'] == '2024FY'
        assert chunk['text'] == parsed['pages'][0]['text'][chunk['start']:chunk['end']]
        assert chunk['source_status'] == 'official_pdf_hash_verified_unreviewed'
        assert chunk['coverage']['pages'] == [60] and chunk['coverage']['total_pages'] == 100
        assert len(chunk['text']) <= 320
        assert len(chunk['chunk_id']) <= 200


@pytest.mark.parametrize('change', ['pdf', 'identity', 'offset', 'page_hash', 'page', 'empty', 'scope'])
def test_invalid_source_never_indexes(tmp_path, change):
    artifact, parsed, pdf = fixture(tmp_path)
    if change == 'pdf': pdf.write_bytes(b'corrupt')
    if change == 'identity': parsed['company_code'] = 'other'
    if change == 'offset': parsed['pages'][0]['spans'][0]['end'] -= 1
    if change == 'page_hash': parsed['pages'][0]['text_sha256'] = 'bad'
    if change == 'page': parsed['pages'][0]['page'] = 101
    if change == 'empty': parsed['pages'] = []
    if change == 'scope': parsed['extraction_scope'] = 'complete'
    with pytest.raises(ValueError): prepare_chunks(artifact, parsed, pdf)


def test_publish_is_atomic_idempotent_and_rejects_conflicts(tmp_path):
    chunks = prepare_chunks(*fixture(tmp_path))
    engine = database()
    vectors = [[1.] + [0.] * 511 for _ in chunks]
    assert publish_chunks(engine, chunks, vectors)['inserted'] == len(chunks)
    assert publish_chunks(engine, chunks, vectors)['inserted'] == 0
    assert publish_chunks(engine, chunks, vectors)['existing'] == len(chunks)
    with engine.begin() as c:
        assert c.scalar(text('SELECT count(*) FROM document_chunk_embeddings')) == len(chunks)
        c.execute(text('UPDATE document_chunk_embeddings SET text_sha256="changed" WHERE chunk_id=:id'), {'id': chunks[-1]['chunk_id']})
    with pytest.raises(ValueError, match='conflict'): publish_chunks(engine, chunks, vectors)
    assert MODEL_ID


def test_bad_vector_and_mid_transaction_failure_leave_no_rows(tmp_path):
    from sqlalchemy import event
    chunks = prepare_chunks(*fixture(tmp_path))
    engine = database()
    with pytest.raises(ValueError): publish_chunks(engine, chunks, [[0.] * 512] * len(chunks))
    inserted = []
    @event.listens_for(engine, 'before_cursor_execute')
    def fail_second(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('INSERT'):
            inserted.append(1)
            if len(inserted) == 2: raise RuntimeError('simulated worker failure')
    with pytest.raises(RuntimeError): publish_chunks(engine, chunks, [[1.] + [0.] * 511] * len(chunks))
    with engine.connect() as c: assert c.scalar(text('SELECT count(*) FROM document_chunk_embeddings')) == 0


def test_parsed_source_text_is_checked_against_actual_pdf(tmp_path):
    import fitz
    from app.corpus_index import verify_pdf_text
    path = tmp_path / 'real.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), 'Actual disclosed source')
        doc.save(path)
    with fitz.open(path) as doc:
        value = doc[0].get_text('blocks', sort=True)[0][4]
    parsed = dict(total_pages=1, pages=[dict(page=1, text=value)])
    verify_pdf_text(path, parsed)
    parsed['pages'][0]['text'] = 'plausible but invented source'
    with pytest.raises(ValueError, match='PDF page text'): verify_pdf_text(path, parsed)


def test_administrator_index_rejects_artifact_outside_ingestion_root(tmp_path):
    from scripts.task9_index import load_chunks
    outside = tmp_path / 'outside.json'
    outside.write_text('{}')
    root = tmp_path / 'ingestion'
    root.mkdir()
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as c:
        c.execute(text('CREATE TABLE ingestion_artifacts (id TEXT,artifact_path TEXT)'))
        c.execute(text('INSERT INTO ingestion_artifacts VALUES (:id,:path)'), dict(id='test', path=str(outside)))
    with pytest.raises(ValueError, match='escapes ingestion root'):
        load_chunks(engine, 'test', root)


def test_changed_span_boundaries_cannot_publish_overlapping_second_corpus(tmp_path):
    artifact, parsed, pdf = fixture(tmp_path)
    initial = prepare_chunks(artifact, parsed, pdf)
    engine = database()
    publish_chunks(engine, initial, [[1.] + [0.] * 511] * len(initial))
    content = parsed['pages'][0]['text']
    parsed['pages'][0]['spans'] = [dict(start=0, end=1, text=content[:1]), dict(start=1, end=len(content), text=content[1:])]
    changed = prepare_chunks(artifact, parsed, pdf)
    with pytest.raises(ValueError, match='publication conflict'):
        publish_chunks(engine, changed, [[1.] + [0.] * 511] * len(changed))
    with engine.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM document_chunk_embeddings')) == len(initial)

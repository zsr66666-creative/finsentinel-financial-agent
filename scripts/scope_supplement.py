"""Export four private evidence vectors, or verify PostgreSQL readback read-only."""
import argparse
import json
import math
import os
from pathlib import Path
from scripts.vector_batch import MODEL,REVISION,digest,validate
from scripts.week04_source_comparison_check import SOURCE_SHA


def verify_restored(row,actual,model,text_hash):
    provenance={k:v for k,v in row.items() if k!='embedding'}
    vector=json.loads(actual['embedding'])
    if (actual['model']!=model or actual['dimensions']!=512 or
        actual['text_sha256']!=text_hash or actual['provenance']!=provenance or
        len(vector)!=512 or len(row['embedding'])!=512 or
        any(not math.isfinite(v) for v in vector) or
        max(abs(a-b) for a,b in zip(vector,row['embedding']))>1e-6):
        raise ValueError(f"readback mismatch: {row['chunk_id']}")


def export(args):
    import pymupdf
    from sentence_transformers import SentenceTransformer
    if digest(args.pdf.read_bytes())!=SOURCE_SHA:
        raise ValueError('source PDF checksum mismatch')
    docs=[json.loads(p.read_text(encoding='utf-8')) for p in args.documents.glob('*.json')]
    matches=[d for d in docs if d['id']=='002475-2026H1' and d['sha256']==SOURCE_SHA]
    if len(matches)!=1:
        raise ValueError('unique matching local document required')
    doc=matches[0]
    rows=[]
    with pymupdf.open(args.pdf) as pdf:
        for page,index,scope in [(60,8,'consolidated'),(60,20,'consolidated'),(63,4,'parent')]:
            matches=[p for p in doc['pages'] if p['page']==page]
            content=matches[0]['spans'][index]['text'].strip()
            normalized=lambda s:' '.join(s.split())
            if normalized(content) not in normalized(pdf[page-1].get_text()):
                raise ValueError('span no longer matches full PDF')
            rows.append(dict(chunk_id=f"{doc['id']}-p{page}-s{index}",page=page,
                text=content,statement_scope=scope,extraction_method='existing_local_span'))
        lines=pdf[61].get_text().splitlines()
        titles=[(i,t.strip()) for i,t in enumerate(lines) if t.strip()=='2、母公司资产负债表']
        if len(titles)!=1:
            raise ValueError('unique mother-company title required')
        i,title=titles[0]
        rows.append(dict(chunk_id=f"{doc['id']}-p62-fulltext-line{i}",page=62,text=title,
            statement_scope='parent',extraction_method='pymupdf_full_page_text_line',
            source_line_zero_based=i,pymupdf_version=pymupdf.VersionBind))
    for row in rows:
        row.update(text_sha256=digest(row['text'].encode('utf-8')),source_url=doc['source_url'],
            document_sha256=SOURCE_SHA,document_id=doc['id'],company_code=doc['company_code'],
            period=doc['report_period'],source_status='local_pdf_hash_matched',
            scope_evidence_id=f"{doc['id']}-p60-s8" if row['statement_scope']=='consolidated'
                else f"{doc['id']}-p62-fulltext-line{i}")
    model=SentenceTransformer(MODEL,revision=REVISION,local_files_only=True,device='cpu')
    vectors=model.encode([r['text'] for r in rows],batch_size=2,normalize_embeddings=True)
    for row,vector in zip(rows,vectors):
        row['embedding']=vector.tolist()
    package=dict(model=MODEL,revision=REVISION,dimensions=512,rows=rows)
    validate(package)
    args.file.parent.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(package,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    args.file.write_bytes(data)
    manifest=dict(rows=len(rows),dimensions=512,sha256=digest(data),model=MODEL,revision=REVISION,
        ids=[r['chunk_id'] for r in rows],source_sha256=SOURCE_SHA,
        status='local_export_verified_remote_import_pending')
    args.file.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(manifest))


def verify(args):
    from sqlalchemy import create_engine,text
    data=args.file.read_bytes()
    if digest(data)!=args.sha256:
        raise ValueError('package checksum mismatch')
    package=json.loads(data)
    validate(package)
    engine=create_engine(os.environ['DATABASE_URL'])
    if engine.dialect.name!='postgresql':
        raise ValueError('requires PostgreSQL')
    with engine.connect() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        total=conn.execute(text('SELECT count(*) FROM document_chunk_embeddings')).scalar_one()
        for row in package['rows']:
            actual=conn.execute(text('''SELECT model,dimensions,text_sha256,embedding::text AS embedding,
                provenance FROM document_chunk_embeddings WHERE chunk_id=:id'''),
                dict(id=row['chunk_id'])).mappings().one()
            verify_restored(row,actual,f'{MODEL}@{REVISION}',row['text_sha256'])
        conn.rollback()
    engine.dispose()
    print(json.dumps(dict(verified=len(package['rows']),total_embeddings=total,
                          vector_tolerance=1e-6,read_only=True)))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['export','verify'])
    parser.add_argument('--file',type=Path,required=True)
    parser.add_argument('--pdf',type=Path)
    parser.add_argument('--documents',type=Path,default=Path('data/derived/documents'))
    parser.add_argument('--sha256')
    args=parser.parse_args()
    export(args) if args.mode=='export' else verify(args)

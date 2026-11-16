"""Authenticated report reader; paths are derived exclusively from registered hashes."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from threading import Lock
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from app.verified_financials import load_contracts
from app.persisted_comparison import SOURCE_SHA, CONTRACTS

SHA = re.compile(r'[0-9a-f]{64}\Z')
MAX_BYTES = 100 * 1024 * 1024
HEADERS = {'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Accept-Ranges':'bytes'}
PARSE_LOCK = Lock()


def persisted(engine, chunk_id=None, sha=None):
    if 'document_chunk_embeddings' not in inspect(engine).get_table_names():
        return []
    if 'provenance' not in {c['name'] for c in inspect(engine).get_columns('document_chunk_embeddings')}:
        return []
    where = 'chunk_id=:value' if chunk_id else "(provenance->>'document_sha256'=:value OR provenance->>'pdf_sha256'=:value)"
    with engine.connect() as conn:
        rows=conn.execute(text('SELECT chunk_id, provenance FROM document_chunk_embeddings WHERE '+where),{'value':chunk_id or sha}).mappings()
        result=[]
        for row in rows:
            p=row['provenance'];p=json.loads(p) if isinstance(p,str) else p
            if isinstance(p,dict):result.append({**p,'chunk_id':row['chunk_id'],'document_sha256':p.get('document_sha256',p.get('pdf_sha256'))})
        return result


def registrations(engine, chunk_id=None, sha=None):
    rows=persisted(engine,chunk_id,sha)
    if (sha==SOURCE_SHA and not chunk_id) or chunk_id in {c[k] for c in CONTRACTS.values() for k in ('metric','title')}:
        for contract in CONTRACTS.values():
            for kind in ('metric','title'):
                if chunk_id and contract[kind]!=chunk_id:continue
                if any(r.get('chunk_id')==contract[kind] for r in rows):continue
                rows.append(dict(chunk_id=contract[kind],document_sha256=SOURCE_SHA,document_id='002475-2026H1',company_code='002475',period='2026H1',page=contract['page' if kind=='metric' else 'title_page'],text=contract['label'] if kind=='title' else '应收账款\n'+'\n'.join(contract['values']),source_url=None))
    if not chunk_id:
        for report in load_contracts():
            if report['sha256']==sha:
                anchors=[a for metric in report['metrics'] for a in metric['evidence']]
                rows.append(dict(document_sha256=sha,document_id=report['document_id'],company_code=report['company_code'],period=report['report_period'],page=anchors[0]['page'],text=anchors[0]['text'],source_url=report['source_url']))
    return rows


def safe_path(path):
    # Reject symlinks/reparse points at every level, including configured roots.
    for part in (path,*path.parents):
        info=part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('unsafe')
    if not stat.S_ISREG(path.stat().st_mode):raise ValueError('unsafe')
    return path


def open_source(path):
    path=safe_path(path)
    if os.name=='posix':
        # Traverse through held directory descriptors, so parent replacement
        # cannot turn a previously checked directory into a symlink.
        descriptor=os.open(path.anchor,os.O_RDONLY|os.O_DIRECTORY)
        try:
            for component in path.parts[1:-1]:
                child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
                os.close(descriptor);descriptor=child
            source=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=descriptor)
        finally:os.close(descriptor)
        return os.fdopen(source,'rb')
    return path.open('rb')


def snapshot(sha):
    import pymupdf
    root=Path(os.getenv('INGESTION_ARTIFACT_ROOT','/var/lib/finsentinel/ingestion'))
    candidates=[root/'blobs'/(sha+'.pdf')]
    if sha==SOURCE_SHA:
        candidates.append(Path('/opt/finsentinel/data/source_pdfs/002475-2026H1.pdf'))
    for candidate in candidates:
        result=None
        try:
            candidate=safe_path(candidate.absolute())
            with open_source(candidate) as source:
                size=os.fstat(source.fileno()).st_size
                if not 0<size<=MAX_BYTES:continue
                result=tempfile.TemporaryFile();digest=hashlib.sha256();total=0
                while block:=source.read(1024*1024):
                    total+=len(block)
                    if total>MAX_BYTES:raise ValueError('too_large')
                    digest.update(block);result.write(block)
                if digest.hexdigest()!=sha:raise ValueError('hash_mismatch')
            result.seek(0)
            # Parse the immutable snapshot, then stream that same snapshot.
            with PARSE_LOCK:
                data=result.read()
                with pymupdf.open(stream=data,filetype='pdf') as pdf:
                    if pdf.needs_pass or not pdf.is_pdf or pdf.page_count<1:raise ValueError('invalid_pdf')
                    count=pdf.page_count
                del data
            result.seek(0)
            return result,total,count
        except Exception:
            if result:result.close()
    raise HTTPException(404,'document_unavailable',headers=HEADERS)


def byte_range(value,size):
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',value or '')
    if not match or not any(match.groups()):raise ValueError('range')
    left,right=match.groups()
    if not left:
        suffix=int(right)
        if suffix<=0:raise ValueError('range')
        return max(0,size-suffix),size-1
    start=int(left);end=min(int(right),size-1) if right else size-1
    if start>=size or start>end:raise ValueError('range')
    return start,end


def wire_report_reader(app,store):
    router=APIRouter(prefix='/api/v1/evidence')
    def authorize(request):
        if not getattr(app.state,'auth_enabled',False) or not getattr(request.state,'session',None):
            raise HTTPException(401,'authentication_required',headers=HEADERS)
    def registered(chunk_id=None,sha=None):
        try:return registrations(store.engine,chunk_id,sha)
        except (SQLAlchemyError,AttributeError,ValueError,TypeError,KeyError):raise HTTPException(503,'reader_unavailable',headers=HEADERS)
    @router.get('/reader')
    def metadata(request:Request,chunk_id:str|None=Query(None,max_length=200),document_sha256:str|None=Query(None,max_length=64),company_code:str|None=Query(None,max_length=100),period:str|None=Query(None,max_length=40),page:int|None=Query(None,ge=1)):
        authorize(request)
        if document_sha256 is not None and not SHA.fullmatch(document_sha256):raise HTTPException(422,'invalid_locator',headers=HEADERS)
        if not chunk_id and not document_sha256:raise HTTPException(422,'missing_locator',headers=HEADERS)
        rows=registered(chunk_id,document_sha256)
        if not rows:raise HTTPException(404,'document_unavailable',headers=HEADERS)
        if chunk_id and document_sha256 and any(r.get('document_sha256')!=document_sha256 for r in rows):raise HTTPException(409,'document_hash_mismatch',headers=HEADERS)
        if company_code:rows=[r for r in rows if r.get('company_code')==company_code]
        if period:rows=[r for r in rows if r.get('period')==period]
        identities={(r.get('document_sha256'),r.get('document_id'),r.get('company_code'),r.get('period')) for r in rows}
        if len(identities)!=1:raise HTTPException(404,'document_unavailable',headers=HEADERS)
        row=rows[0];sha=row.get('document_sha256')
        if not isinstance(sha,str) or not SHA.fullmatch(sha):raise HTTPException(404,'document_unavailable',headers=HEADERS)
        content,size,count=snapshot(sha);content.close()
        selected=page if page is not None else row.get('page',1)
        if type(selected) is not int or not 1<=selected<=count:raise HTTPException(422,'page_out_of_bounds',headers=HEADERS)
        excerpt=next((r.get('text','') for r in rows if r.get('page')==selected),'')
        return Response(content=json.dumps(dict(document_sha256=sha,document_id=row.get('document_id'),company_code=row.get('company_code'),period=row.get('period'),page=selected,page_count=count,text=excerpt,source_status='verified_pdf',source_url=row.get('source_url'),pdf_url=f'/api/v1/evidence/documents/{sha}/pdf')),media_type='application/json',headers=HEADERS)
    @router.api_route('/documents/{sha}/pdf',methods=['GET','HEAD'])
    def pdf(request:Request,sha:str):
        authorize(request)
        if not SHA.fullmatch(sha) or not registered(sha=sha):raise HTTPException(404,'document_unavailable',headers=HEADERS)
        content,size,_=snapshot(sha);start,end=0,size-1;status=200
        headers={**HEADERS,'Content-Disposition':f'inline; filename="{sha}.pdf"'}
        if request.headers.get('range'):
            try:start,end=byte_range(request.headers['range'],size)
            except (ValueError,OverflowError):
                content.close();raise HTTPException(416,'range_not_satisfiable',headers={**headers,'Content-Range':f'bytes */{size}'})
            status=206;headers['Content-Range']=f'bytes {start}-{end}/{size}'
        headers['Content-Length']=str(end-start+1)
        if request.method=='HEAD':
            content.close();return Response(status_code=status,media_type='application/pdf',headers=headers)
        def stream():
            try:
                content.seek(start);remaining=end-start+1
                while remaining:
                    block=content.read(min(65536,remaining))
                    if not block:break
                    remaining-=len(block);yield block
            finally:content.close()
        return StreamingResponse(stream(),status_code=status,media_type='application/pdf',headers=headers)
    app.include_router(router)

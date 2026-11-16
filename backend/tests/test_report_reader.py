import hashlib
import json
import pymupdf
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth.service import Accounts, migrate_accounts

@pytest.fixture
def reader(tmp_path,monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('AUTH_ORIGIN','http://testserver');monkeypatch.setenv('AUTH_COOKIE_SECURE','false')
    monkeypatch.setenv('INGESTION_ARTIFACT_ROOT',str(tmp_path))
    app=create_app('sqlite:///'+str(tmp_path/'db'))
    migrate_accounts(app.state.store.engine)
    s=Accounts(app.state.store.engine);u=s.create_user('admin','temporary password','admin','Admin')
    s.password(u['id'],'temporary password','permanent password')
    c=TestClient(app);c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'permanent password'})
    with pymupdf.open() as doc:
        doc.new_page().insert_text((20,20),'First');doc.new_page()
        payload=doc.tobytes()
    sha=hashlib.sha256(payload).hexdigest();blob=tmp_path/'blobs';blob.mkdir();(blob/(sha+'.pdf')).write_bytes(payload)
    p=dict(document_sha256=sha,document_id='report',company_code='000001',period='2024FY',page=2,text='Server excerpt',source_url='https://example.test/report.pdf')
    with app.state.store.engine.begin() as conn:
        conn.execute(text('CREATE TABLE document_chunk_embeddings (chunk_id TEXT, provenance TEXT)'))
        conn.execute(text('INSERT INTO document_chunk_embeddings VALUES (:id,:p)'),dict(id='chunk',p=json.dumps(p)))
    return c,sha,payload,tmp_path,app

def test_metadata_and_exact_binding(reader):
    c,sha,_,_,_=reader
    r=c.get('/api/v1/evidence/reader',params={'chunk_id':'chunk','document_sha256':sha})
    assert r.status_code==200
    assert r.json()['page_count']==2 and r.json()['text']=='Server excerpt'
    assert r.json()['pdf_url']==f'/api/v1/evidence/documents/{sha}/pdf'
    assert c.get('/api/v1/evidence/reader',params={'chunk_id':'chunk','document_sha256':'a'*64}).status_code==409
    assert c.get('/api/v1/evidence/reader',params={'document_sha256':sha,'page':3}).status_code==422
    assert c.get('/api/v1/evidence/reader').status_code==422

def test_pdf_ranges_head_and_unknown(reader):
    c,sha,data,_,_=reader;url=f'/api/v1/evidence/documents/{sha}/pdf'
    assert c.get(url).content==data
    for value,start,end in [('bytes=0-7',0,7),('bytes=-7',len(data)-7,len(data)-1),('bytes=7-',7,len(data)-1)]:
        r=c.get(url,headers={'Range':value});assert r.status_code==206 and r.content==data[start:end+1]
        assert r.headers['content-range']==f'bytes {start}-{end}/{len(data)}'
    assert c.head(url).content==b'' and int(c.head(url).headers['content-length'])==len(data)
    for value in ['bytes=999999-','bytes=0-1,3-4','garbage','bytes=-0']:
        r=c.get(url,headers={'Range':value});assert r.status_code==416 and r.headers['content-range']==f'bytes */{len(data)}'
    assert c.get('/api/v1/evidence/documents/'+'a'*64+'/pdf').status_code==404

def test_auth_corruption_and_no_path_leak(reader,monkeypatch):
    c,sha,_,root,app=reader;url=f'/api/v1/evidence/documents/{sha}/pdf'
    c.cookies.clear();assert c.get(url).status_code==401
    monkeypatch.setenv('AUTH_ENABLED','false')
    disabled=TestClient(create_app('sqlite:///'+str(root/'disabled.db')))
    assert disabled.get(url).status_code==401
    c.post('/api/v1/auth/login',headers={'Origin':'http://testserver'},json={'username':'admin','password':'permanent password'})
    (root/'blobs'/(sha+'.pdf')).write_bytes(b'%PDF-corrupted')
    r=c.get(url);assert r.status_code==404 and str(root) not in r.text

def test_page_excerpt_and_ambiguity(reader):
    c,sha,_,_,app=reader
    assert c.get('/api/v1/evidence/reader',params={'document_sha256':sha,'page':1}).json()['text']==''
    with app.state.store.engine.begin() as conn:
        conn.execute(text('INSERT INTO document_chunk_embeddings VALUES (:id,:p)'),dict(id='ambiguous',p=json.dumps(dict(document_sha256=sha,document_id='other',company_code='000001',period='2024FY',page=1))))
    assert c.get('/api/v1/evidence/reader',params={'document_sha256':sha}).status_code==404

def test_symlink_missing_oversized_and_encrypted(reader,monkeypatch):
    c,sha,data,root,app=reader;path=root/'blobs'/(sha+'.pdf');url=f'/api/v1/evidence/documents/{sha}/pdf'
    path.unlink();assert c.get(url).status_code==404
    other=root/'outside.pdf';other.write_bytes(data)
    try:path.symlink_to(other)
    except OSError:pass
    else:
        assert c.get(url).status_code==404
        path.unlink()
    path.write_bytes(data)
    monkeypatch.setattr('app.report_reader.MAX_BYTES',10)
    assert c.get(url).status_code==404
    monkeypatch.setattr('app.report_reader.MAX_BYTES',100*1024*1024)
    with pymupdf.open() as doc:
        doc.new_page();encrypted=doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='secret')
    encrypted_sha=hashlib.sha256(encrypted).hexdigest()
    (root/'blobs'/(encrypted_sha+'.pdf')).write_bytes(encrypted)
    with app.state.store.engine.begin() as conn:
        conn.execute(text('INSERT INTO document_chunk_embeddings VALUES (:id,:p)'),dict(id='encrypted',p=json.dumps(dict(document_sha256=encrypted_sha,document_id='encrypted',page=1))))
    assert c.get(f'/api/v1/evidence/documents/{encrypted_sha}/pdf').status_code==404

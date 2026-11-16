import test from 'node:test';
import assert from 'node:assert/strict';
import {readerHref,parseReaderQuery,parseReaderMetadata} from '../src/lib/reader.mjs';
const sha='a'.repeat(64);
const metadata={document_sha256:sha,document_id:'report',company_code:'002555',period:'2024FY',page:5,page_count:100,text:'source',source_status:'verified_pdf',source_url:null,pdf_url:`/api/v1/evidence/documents/${sha}/pdf`};
test('chunk locator encodes identifier and expected SHA',()=>{const href=readerHref({chunk_id:'proof/one?x=1',document_sha256:sha});assert.equal(new URL(href,'https://local').searchParams.get('chunk_id'),'proof/one?x=1');assert.ok(href.includes(sha));});
test('report locator requires full identity and positive integer page',()=>{assert.ok(readerHref({company_code:'002555',period:'2024FY',document_sha256:sha,page:5}));for(const page of [0,-1,1.5,'5',Infinity])assert.equal(readerHref({chunk_id:'proof',page}),null);assert.equal(readerHref({document_sha256:sha}),null);assert.equal(readerHref({chunk_id:'proof',document_sha256:'bad'}),null);});
test('query rejects arbitrary src, duplicates and malformed pages',()=>{for(const query of ['src=https://evil/pdf','chunk_id=p&chunk_id=q','chunk_id=p&page=1.5','chunk_id=p&page=01','chunk_id=','company_code=002555&period=2024FY'])assert.equal(parseReaderQuery(new URLSearchParams(query)),null);assert.ok(parseReaderQuery(new URLSearchParams('chunk_id=p')));});
test('metadata requires canonical same-origin PDF and expected identity',()=>{const locator=new URLSearchParams({company_code:'002555',period:'2024FY',document_sha256:sha,page:'5'});assert.equal(parseReaderMetadata(metadata,locator),metadata);for(const patch of [{pdf_url:'https://evil/pdf'},{pdf_url:'//evil/pdf'},{document_sha256:'b'.repeat(64)},{company_code:'002230'},{period:'2025FY'},{page:6},{page_count:4},{text:null},{source_status:null}])assert.throws(()=>parseReaderMetadata({...metadata,...patch},locator));});
test('saved source uses SHA without mutable current chunk',()=>{const href=readerHref({company_code:'002555',period:'2024FY',document_sha256:sha,page:5});assert.ok(href.includes(sha));assert.ok(!href.includes('chunk_id'));});

import {safeReturnPath} from '../src/lib/demo-profile.mjs';
test('reader login return preserves validated locator only',()=>{assert.equal(safeReturnPath('/reader?chunk_id=proof'),'/reader?chunk_id=proof');assert.equal(safeReturnPath('/reader?src=https://evil/pdf'),'/');assert.equal(safeReturnPath('//evil/reader?chunk_id=p'),'/');});

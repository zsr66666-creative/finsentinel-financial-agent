import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogSummary, catalogCompanies, catalogReports, filterCompanies, chooseCompany, evidenceContext, workbenchView } from '../src/lib/portal.mjs';
import { safeReturnPath } from '../src/lib/demo-profile.mjs';
const scopes=[{company_code:'002555',company_name:'三七互娱',industry:'互联网游戏',period:'2024FY',chunk_count:336,documents:[{document_id:'a',document_sha256:'a'.repeat(64),pages:[2,9],total_pages:203,chunk_count:336,coverage_kind:'selected_pages',source_statuses:['official_pdf_hash_verified_unreviewed']}]},{company_code:'002230',company_name:'科大讯飞',industry:'人工智能',period:'2024FY',chunk_count:372,documents:[{document_id:'b',document_sha256:'b'.repeat(64),pages:[1,7],total_pages:289,chunk_count:372,coverage_kind:'selected_pages',source_statuses:[]}]}];
test('portal derives counts only from actual catalog and deduplicates company reports',()=>{
 assert.deepEqual(catalogSummary(scopes),{companies:2,reports:2,chunks:708});
 assert.equal(catalogCompanies([...scopes,{...scopes[0],period:'2023FY',documents:[]}]).length,2);
 assert.deepEqual(catalogSummary([]),{companies:0,reports:0,chunks:0});
 assert.equal(catalogReports(scopes)[0].document_id,'a');
 assert.equal(catalogSummary([...scopes,scopes[0]]).reports,2);
});
test('industry and query filters combine without inventing company entries',()=>{
 const rows=catalogCompanies(scopes);
 assert.equal(filterCompanies(rows,'人工智能','002230').length,1);
 assert.equal(filterCompanies(rows,'互联网游戏','科大').length,0);
 assert.equal(filterCompanies(rows,'all','讯飞')[0].company_code,'002230');
 assert.equal(chooseCompany(rows,'002555')?.company_code,'002555');
 assert.equal(chooseCompany(rows,'不存在'),null);
});
test('evidence links require a complete existing company-period pair',()=>{
 assert.deepEqual(evidenceContext(scopes,'002230','2024FY'),{companyCode:'002230',period:'2024FY'});
 assert.equal(evidenceContext(scopes,'002230','2023FY'),null);
 assert.equal(evidenceContext(scopes,'../bad','2024FY'),null);
});
test('new destinations are safe login returns but arbitrary paths are refused',()=>{
 for(const path of ['/companies','/reports','/evidence','/workbench','/workbench/alerts','/workbench/review','/workbench/evals','/workbench/data','/workbench/companies']) assert.equal(safeReturnPath(path),path);
 for(const path of ['//evil.test','/workbench/unknown','/evidence?next=//evil','/reports/../../login','/companies/%2f%2fevil','/workbench/alerts/extra']) assert.equal(safeReturnPath(path),'/');
 assert.equal(workbenchView('review'),'review');assert.equal(workbenchView('unknown'),null);assert.equal(workbenchView(undefined),'overview');
});

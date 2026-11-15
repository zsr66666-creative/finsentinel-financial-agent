import test from 'node:test';
import assert from 'node:assert/strict';
import { parseFinancialComparison, formatFinancialNumber } from '../src/lib/verified-financials.mjs';

const refusal = () => ({ company_code:'002555',period:'2024FY',statement_scope:'parent',data_mode:'source_verified_financial_contract',review_status:'pending_human',status:'needs_review',items:[],total:0,reason:'unsupported_company_period_or_scope' });
test('financial responses bind company, report and scope without fallback values', () => {
  const body=refusal();assert.equal(parseFinancialComparison(body,'002555','2024FY','parent').status,'needs_review');
  for (const args of [['002230','2024FY','parent'],['002555','2023FY','parent'],['002555','2024FY','consolidated']]) assert.throws(()=>parseFinancialComparison(body,...args));
  assert.throws(()=>parseFinancialComparison({...body,data_mode:'synthetic_demo'},'002555','2024FY','parent'));
});
test('needs_review never carries monetary conclusions',()=>{
  const body={...refusal(),items:[{metric:'revenue',label:'营业收入',status:'needs_review',review_status:'pending_human',reason:'source_pdf_unavailable',evidence:[]}],total:1};
  assert.equal(parseFinancialComparison(body,'002555','2024FY','parent').items.length,1);
  for(const key of ['current_value','previous_value','difference','change_percent']) assert.throws(()=>parseFinancialComparison({...body,items:[{...body.items[0],[key]:'0.00'}]},'002555','2024FY','parent'));
});
test('format preserves decimal precision, sign, and real zero',()=>{
  assert.equal(formatFinancialNumber('23343093018.69'),'23,343,093,018.69');
  assert.equal(formatFinancialNumber('123456789012345678.99'),'123,456,789,012,345,678.99');
  assert.equal(formatFinancialNumber('-0.01'),'-0.01');assert.equal(formatFinancialNumber('0.00'),'0.00');
  assert.equal(formatFinancialNumber(null),'—');assert.equal(formatFinancialNumber('NaN'),'—');
});
test('supported claims require explicit numeric and source proofs',()=>{
  const base=refusal();
  const metric={metric:'revenue',label:'营业收入',status:'supported',review_status:'pending_human',current_value:'2.00',previous_value:'1.00',difference:'1.00',change_percent:'100.00',change_percent_reason:null,direction:'increase',company_code:'002555',report_period:'2024FY',statement_scope:'consolidated',unit:'CNY',period_kind:'flow',current_period:'2024-01-01/2024-12-31',previous_period:'2023-01-01/2023-12-31',current_column:'2024 年度',previous_column:'2023 年度',source_url:'https://static.cninfo.com.cn/finalpage/2025-04-19/1223144140.PDF',source_sha256:'a'.repeat(64),document_id:'b'.repeat(64),source_validation:'pdf_hash_and_statement_contract',extraction_method:'pymupdf_text_whitespace_normalized',evidence:['row','statement','columns','unit'].map(role=>({role,page:92,text:role,evidence_id:role,text_sha256:'c'.repeat(64),page_text_sha256:'d'.repeat(64)}))};
  const body={...base,statement_scope:'consolidated',items:[metric],total:1,status:'needs_review'};
  assert.equal(parseFinancialComparison(body,'002555','2024FY','consolidated').items[0].current_value,'2.00');
  for (const patch of [{company_code:'002230'},{statement_scope:'parent'},{unit:'万元'},{source_url:'javascript:alert(1)'},{evidence:[]},{current_value:null},{review_status:'reviewed'}]) assert.throws(()=>parseFinancialComparison({...body,items:[{...metric,...patch}]},'002555','2024FY','consolidated'));
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { parseReviewState, reviewStatusText } from '../src/lib/financial-review.mjs';
const comparison={company_code:'002555',period:'2024FY',statement_scope:'consolidated',items:[{metric:'revenue',status:'supported',current_value:'9007199254740993.01'}]};
const state=()=>({company_code:'002555',period:'2024FY',statement_scope:'consolidated',identity_assurance:'self_declared_operator',items:[{metric:'revenue',fingerprint:'a'.repeat(64),snapshot:comparison.items[0],review_status:'pending_human',latest:null,history:[]}]});
test('review state binds exact current source and preserves pending status',()=>{assert.equal(parseReviewState(state(),comparison).items[0].review_status,'pending_human');assert.equal(reviewStatusText('confirmed'),'维护者确认');});
test('reject wrong scope, changed amount, unknown status and mismatched latest fingerprint',()=>{for(const change of [s=>s.company_code='002230',s=>s.items[0].snapshot={...s.items[0].snapshot,current_value:'1.00'},s=>s.items[0].review_status='certified',s=>{s.items[0].latest={id:'id',fingerprint:'b'.repeat(64),decision:'confirmed'};s.items[0].review_status='confirmed';}]){const s=state();change(s);assert.throws(()=>parseReviewState(s,comparison));}});

test('authenticated reviews coexist with clearly marked legacy signatures',()=>{
 const s=state();s.identity_assurance='authenticated_user';const item=s.items[0];
 const record={id:'review-1',company_code:s.company_code,period:s.period,statement_scope:s.statement_scope,metric:'revenue',fingerprint:item.fingerprint,decision:'confirmed',identity_assurance:'authenticated_user',reason:'checked source',reviewer:'Alice',created_at:'2026-11-16T00:00:00Z'};
 item.history=[record,{...record,id:'legacy',identity_assurance:'self_declared_operator'}];item.latest=record;item.review_status='confirmed';
 assert.equal(parseReviewState(s,comparison).items[0].history.length,2);
 record.identity_assurance='forged_identity';assert.throws(()=>parseReviewState(s,comparison));
});

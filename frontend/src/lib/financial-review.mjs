const statuses={pending_human:'待人工复核',confirmed:'维护者确认',rejected:'已驳回',needs_evidence:'需补充证据',source_unavailable:'来源暂不可用'};
export function reviewStatusText(status){return statuses[status]??'未知状态';}
function stable(value){return JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);}
export function parseReviewState(body,comparison){
 const invalid=()=>{throw new Error('复核记录与当前来源不一致，请重新核对后加载。');};
 if(!body||body.company_code!==comparison.company_code||body.period!==comparison.period||body.statement_scope!==comparison.statement_scope||!['self_declared_operator','authenticated_user'].includes(body.identity_assurance)||!Array.isArray(body.items)||body.items.length!==comparison.items.length)invalid();
 const seen=new Set();
 for(const state of body.items){const row=comparison.items.find(r=>r.metric===state.metric);if(!row||seen.has(state.metric)||!Object.hasOwn(statuses,state.review_status)||!Array.isArray(state.history)||state.history.length>30)invalid();seen.add(state.metric);
 if(row.status==='supported'){if(!/^[a-f0-9]{64}$/.test(state.fingerprint??'')||stable(state.snapshot)!==stable(row)||state.review_status==='source_unavailable')invalid();}
 else if(state.fingerprint!==null||state.snapshot!==null||state.latest!==null||state.review_status!=='source_unavailable')invalid();
 for(const record of state.history){if(!record||typeof record.id!=='string'||record.metric!==state.metric||record.company_code!==comparison.company_code||record.period!==comparison.period||record.statement_scope!==comparison.statement_scope||!['confirmed','rejected','needs_evidence'].includes(record.decision)||!['self_declared_operator','authenticated_user'].includes(record.identity_assurance)||typeof record.reason!=='string'||typeof record.reviewer!=='string'||typeof record.created_at!=='string'||!/^[a-f0-9]{64}$/.test(record.fingerprint??''))invalid();}
 if(state.latest){if(state.latest.fingerprint!==state.fingerprint||state.latest.decision!==state.review_status||!state.history.some(r=>r.id===state.latest.id&&stable(r)===stable(state.latest)))invalid();}
 else if(!['pending_human','source_unavailable'].includes(state.review_status))invalid();
 }
 return body;
}

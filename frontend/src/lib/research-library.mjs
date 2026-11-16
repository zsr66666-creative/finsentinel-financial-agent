import {authFetch} from './accounts.mjs';
export function queryPrefill(value) { return typeof value==='string' && value.trim().length<=1000 ? value.trim() : ''; }
export function historyPayload(value) {
 const query=queryPrefill(value.query);
 if(!['search','compare'].includes(value.kind)||!query) throw new Error('研究记录格式无效。');
 const result={kind:value.kind,query};
 if(value.company_code!=null) {if(!/^\d{6}$/.test(value.company_code))throw new Error('公司代码无效。');result.company_code=value.company_code;}
 if(value.period!=null) {if(typeof value.period!=='string'||!value.period||value.period.length>40||/[\u0000-\u001f\u007f]/.test(value.period))throw new Error('报告期无效。');result.period=value.period;}
 return result;
}
export function reopenHref(value) {
 try {const entry=historyPayload(value);if(entry.kind==='search'&&(!entry.company_code||!entry.period))return null;const params=new URLSearchParams();if(entry.kind==='search'){params.set('company',entry.company_code);params.set('period',entry.period);}params.set('q',entry.query);return `${entry.kind==='search'?'/evidence':'/compare'}?${params}`;}catch{return null;}
}
export function parseResearchPage(value,collection) {
 if(!value||!Array.isArray(value.items)||!Number.isSafeInteger(value.total)||value.total<0)throw new Error('个人研究库响应格式无效。');
 for(const item of value.items){if(!item||typeof item.id!=='string'||!item.id||(typeof item.created_at!=='number'||!Number.isFinite(item.created_at)))throw new Error('研究记录格式无效。');if(collection==='favorites'){if(!['company','evidence'].includes(item.kind)||!/^\d{6}$/.test(item.company_code)||typeof item.note!=='string'||item.note.length>1000||!item.snapshot||typeof item.snapshot!=='object'||Array.isArray(item.snapshot)||item.snapshot.company_code!==item.company_code||typeof item.updated_at!=='number'||!Number.isFinite(item.updated_at))throw new Error('收藏格式无效。');if(item.kind==='company'&&typeof item.snapshot.company_name!=='string')throw new Error('公司快照无效。');if(item.kind==='evidence'&&(typeof item.chunk_id!=='string'||!item.chunk_id||typeof item.snapshot.text!=='string'||item.snapshot.period!==item.period||(item.snapshot.page!=null&&(!Number.isSafeInteger(item.snapshot.page)||item.snapshot.page<1))))throw new Error('证据快照无效。');}else {historyPayload(item);if(item.kind==='search'&&(!item.company_code||!item.period))throw new Error('研究范围缺失。');}}
 return value;
}
export async function researchRequest(path,init={}) {
 if(!/^\/(favorites|history)(\?|\/|$)/.test(path))throw new Error('研究库路径无效。');
 const controller=new AbortController();const external=init.signal;const cancel=()=>controller.abort();external?.addEventListener('abort',cancel,{once:true});if(external?.aborted)controller.abort();const timer=setTimeout(cancel,12000);
 try {const response=await authFetch('/api/v1/me/research'+path,{...init,signal:controller.signal});if(!response.ok)throw new Error(response.status===401?'请登录后使用个人研究库。':response.status===409?'收藏数量已达上限，请先移除部分收藏。':`个人研究库请求失败（${response.status}）。`);return response.status===204?null:await response.json();}catch(error){if(error.name==='AbortError')throw new Error('个人研究库请求超时或已取消，请重试。');throw error;}finally{clearTimeout(timer);external?.removeEventListener('abort',cancel);}
}
export function researchWrite(path,body,method='POST',signal){return researchRequest(path,{method,headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),signal});}

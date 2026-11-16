const mandatoryIds = ['nginx','backend','frontend','ingestion_worker','query_encoder','renewal_timer','backup_timer','restore_timer','renewal','database','https_health','https_login','https_static','encoder_health','disk','certificate','backup','restore'];
const statuses = ['ok','warning','critical','unknown'];
const invalid = () => { throw new Error('运行状态格式无效，请稍后刷新。'); };
const stamp = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value));
const safeText = value => typeof value === 'string' && value.length > 0 && value.length <= 240 && !/[\u0000-\u001f\u007f\\/]|(?:password|secret|token|credential|private_key)\s*[:=]/i.test(value);
export function groupStatus(checks) {
 if (!checks.length) return 'unknown';
 for (const state of ['critical','unknown','warning']) if (checks.some(c=>c.status===state)) return state;
 return 'ok';
}
export function parseOperations(value, now = Date.now()) {
 if (!value || value.schema_version!==1 || !stamp(value.checked_at) || !statuses.includes(value.status) || !Array.isArray(value.checks) || value.checks.length>100 || !Array.isArray(value.history) || value.history.length>200) return invalid();
 const ids=new Set();
 const checks=value.checks.map(c=>{
  if (!c || !/^[a-z][a-z0-9_]{0,63}$/.test(c.id) || ids.has(c.id) || !safeText(c.label) || !safeText(c.reason) || !statuses.includes(c.status) || !stamp(c.checked_at) || !Number.isFinite(c.duration_ms) || c.duration_ms<0 || c.duration_ms>120000) return invalid();
  const metadata={};
  if (['backup','restore'].includes(c.id) && c.last_success_at!==undefined) { if (!stamp(c.last_success_at)) return invalid(); metadata.last_success_at=c.last_success_at; }
  if (c.id==='certificate' && c.expires_at!==undefined) { if (!stamp(c.expires_at)) return invalid(); metadata.expires_at=c.expires_at; }
  if (c.id==='disk') {
   for (const key of ['free_bytes','total_bytes']) if (c[key]!==undefined) { if (!Number.isSafeInteger(c[key]) || c[key]<0) return invalid(); metadata[key]=c[key]; }
   if (c.free_bytes!==undefined && c.total_bytes!==undefined && c.free_bytes>c.total_bytes) return invalid();
  }
  ids.add(c.id);return {id:c.id,label:c.label,status:c.status,reason:c.reason,checked_at:c.checked_at,duration_ms:c.duration_ms,...metadata};
 });
 const history=value.history.map(h=>{
  if (!h || !stamp(h.at) || !/^[a-z][a-z0-9_]{0,63}$/.test(h.check_id) || !statuses.includes(h.status) || !safeText(h.reason)) return invalid();
  return {at:h.at,check_id:h.check_id,status:h.status,reason:h.reason};
 });
 const expired = at => now-Date.parse(at)>15*60000 || Date.parse(at)-now>60000;
 const stale = expired(value.checked_at) || checks.some(c=>expired(c.checked_at));
 const incomplete = mandatoryIds.some(id=>!ids.has(id));
 const status=groupStatus([{status:value.status},...checks,...(incomplete?[{status:'unknown'}]:[])]);
 return {schema_version:1,checked_at:value.checked_at,status:stale||!checks.length?(status==='critical'?'critical':'unknown'):status,checks:stale?checks.map(c=>({...c,status:'unknown',reason:'状态超过有效时间，请刷新确认。'})):checks,history,stale};
}

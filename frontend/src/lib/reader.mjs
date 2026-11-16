const shaPattern = /^[a-f0-9]{64}$/;
const companyPattern = /^\d{6}$/;
const periodPattern = /^\d{4}(?:FY|H1|Q[1-4])$/;
export function readerLocator(value) {
  if (!value || typeof value !== 'object') return null;
  const {chunk_id, document_sha256, company_code, period, page} = value;
  const sha = document_sha256 == null ? null : typeof document_sha256 === 'string' && shaPattern.test(document_sha256) ? document_sha256 : false;
  if (sha === false) return null;
  const physical = page == null ? null : typeof page === 'number' && Number.isSafeInteger(page) && page > 0 ? page : false;
  if (physical === false) return null;
  const params = new URLSearchParams();
  if (typeof chunk_id === 'string' && chunk_id.length > 0 && chunk_id.length <= 512 && !/[\x00-\x20]/.test(chunk_id)) params.set('chunk_id', chunk_id);
  else if (chunk_id != null) return null;
  else if (!(sha && companyPattern.test(company_code) && periodPattern.test(period))) return null;
  if (sha) params.set('document_sha256', sha);
  if (!params.has('chunk_id')) { params.set('company_code', company_code); params.set('period', period); }
  if (physical) params.set('page', String(physical));
  return params;
}
export function readerHref(value) { const params = readerLocator(value); return params ? `/reader?${params}` : null; }
export function parseReaderQuery(params) {
  const allowed = new Set(['chunk_id','document_sha256','company_code','period','page']);
  for (const key of params.keys()) if (!allowed.has(key) || params.getAll(key).length !== 1) return null;
  const raw = Object.fromEntries(params);
  if ('page' in raw && !/^[1-9]\d*$/.test(raw.page)) return null;
  return readerLocator({...raw, page: raw.page == null ? undefined : Number(raw.page)});
}
export function parseReaderMetadata(body, locator) {
  if (!body || typeof body !== 'object' || typeof body.document_sha256 !== 'string' || !shaPattern.test(body.document_sha256) || typeof body.company_code !== 'string' || !companyPattern.test(body.company_code) || typeof body.period !== 'string' || !periodPattern.test(body.period) || typeof body.document_id !== 'string' || !body.document_id || !Number.isSafeInteger(body.page_count) || body.page_count < 1 || !Number.isSafeInteger(body.page) || body.page < 1 || body.page > body.page_count || typeof body.text !== 'string' || typeof body.source_status !== 'string' || (body.source_url != null && typeof body.source_url !== 'string') || body.pdf_url !== `/api/v1/evidence/documents/${body.document_sha256}/pdf`) throw new Error('报告来源信息不完整，已停止打开。');
  for (const key of ['document_sha256','company_code','period']) if (locator.has(key) && locator.get(key) !== body[key]) throw new Error('报告来源与链接不一致，已停止打开。');
  if (locator.has('page') && Number(locator.get('page')) !== body.page) throw new Error('报告页码与链接不一致。');
  return body;
}

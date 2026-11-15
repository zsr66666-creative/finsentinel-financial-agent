const AMOUNT = /^-?\d{1,18}\.\d{2}$/;
const HASH = /^[a-f0-9]{64}$/;
const METRICS = new Set(['revenue','receivables','operating_cash_flow']);
export function formatFinancialNumber(value) {
  if (typeof value !== 'string' || !AMOUNT.test(value)) return '—';
  const [integer, fraction] = value.split('.');
  return `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
}
export function parseFinancialComparison(body, company, period, scope) {
  const invalid = () => { throw new Error('财务核对响应不完整或与当前研究范围不符，请重试。'); };
  if (!body || body.company_code !== company || body.period !== period || body.statement_scope !== scope || body.data_mode !== 'source_verified_financial_contract' || body.review_status !== 'pending_human' || !['supported','needs_review'].includes(body.status) || !Array.isArray(body.items) || body.total !== body.items.length || body.items.length > 3) invalid();
  const seen = new Set();
  for (const row of body.items) {
    if (!row || !METRICS.has(row.metric) || seen.has(row.metric) || typeof row.label !== 'string' || !row.label.trim() || row.review_status !== 'pending_human' || !Array.isArray(row.evidence)) invalid();
    seen.add(row.metric);
    if (row.status === 'needs_review') {
      if (typeof row.reason !== 'string' || !row.reason || row.evidence.length || ['current_value','previous_value','difference','change_percent'].some(k => k in row)) invalid();
      continue;
    }
    if (row.status !== 'supported' || row.company_code !== company || row.report_period !== period || row.statement_scope !== scope || row.unit !== 'CNY' || row.source_validation !== 'pdf_hash_and_statement_contract' || !HASH.test(row.source_sha256 ?? '') || !HASH.test(row.document_id ?? '') || typeof row.source_url !== 'string' || !/^https:\/\/static\.cninfo\.com\.cn\/finalpage\/\d{4}-\d{2}-\d{2}\/\d+\.PDF$/.test(row.source_url) || !['current_value','previous_value','difference'].every(k => typeof row[k] === 'string' && AMOUNT.test(row[k])) || !(row.change_percent === null && row.change_percent_reason === 'zero_comparison_base' || typeof row.change_percent === 'string' && /^-?\d+\.\d{2}$/.test(row.change_percent)) || !['increase','decrease','unchanged'].includes(row.direction) || !['flow','balance'].includes(row.period_kind) || !['current_column','previous_column','current_period','previous_period'].every(k => typeof row[k] === 'string' && row[k].trim())) invalid();
    const roles = new Set();
    for (const proof of row.evidence) {
      if (!proof || !Number.isInteger(proof.page) || proof.page < 1 || typeof proof.role !== 'string' || typeof proof.text !== 'string' || !proof.text.trim() || typeof proof.evidence_id !== 'string' || !proof.evidence_id || !HASH.test(proof.text_sha256 ?? '') || !HASH.test(proof.page_text_sha256 ?? '')) invalid();
      roles.add(proof.role);
    }
    if (!['row','statement','columns','unit'].every(role => roles.has(role))) invalid();
  }
  if (body.status === 'supported' && (body.items.length !== 3 || body.items.some(row => row.status !== 'supported'))) invalid();
  return body;
}

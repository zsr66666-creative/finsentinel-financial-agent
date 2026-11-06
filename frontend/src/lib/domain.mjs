export function normalizeCollection(payload, key = 'items') {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.[key])) return payload[key];
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}
export function normalizeAlert(row) {
  const status = row.status ?? row.review_status ?? 'pending';
  return {
    ...row,
    id: String(row.id ?? row.alert_id),
    company_id: String(row.company_id ?? ''),
    company_name: row.company_name ?? row.company?.name ?? row.company_id ?? '未知公司',
    severity: row.severity ?? row.risk_level ?? 'medium',
    status: ['pending_review', 'open', 'needs_review'].includes(status) ? 'pending' : status,
    evidence: row.evidence ?? row.evidence_spans ?? [],
    metrics: row.metrics ?? [],
    agent_steps: row.agent_steps ?? row.steps ?? [],
  };
}
export function filterAlerts(rows, filters) {
  const q = (filters.query ?? '').trim().toLowerCase();
  return rows.filter(row =>
    (!filters.severity || filters.severity === 'all' || row.severity === filters.severity) &&
    (!filters.company || filters.company === 'all' || row.company_name === filters.company) &&
    (!filters.status || filters.status === 'all' || row.status === filters.status) &&
    (!q || `${row.title} ${row.company_name} ${row.summary ?? ''}`.toLowerCase().includes(q))
  );
}
export function formatMetric(value, unit = '') {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value !== 'number') return String(value);
  return `${value.toLocaleString('zh-CN', { maximumFractionDigits: 1, minimumFractionDigits: unit === '%' ? 1 : 0 })}${unit}`;
}

export function connectionStatusLabel({ loading = false, connected = false, error = '' } = {}) {
  if (loading) return '正在连接数据服务…';
  if (connected) return '数据服务已连接';
  return error ? '数据服务暂时不可用，当前展示离线演示数据。' : '离线演示模式';
}

export function refreshLabel(refreshing = false) {
  return refreshing ? '刷新中…' : '刷新数据';
}

export function metricStateLabel({ loading = false, error = '', hasData = false } = {}) {
  if (loading) return '正在加载指标…';
  if (error) return '指标加载失败，请重试。';
  return hasData ? '' : '该公司暂无已入库指标。';
}

export function alertEmptyLabel({ total = 0, filtered = 0, review = false } = {}) {
  if (filtered > 0) return '';
  if (total === 0) return review ? '当前没有待复核告警。' : '当前没有风险告警。';
  return '没有匹配的告警，请调整筛选条件。';
}

export function evidenceStatusLabel(evidence = {}) {
  if (evidence.source_url && evidence.page != null) return '原文与页码已定位';
  if (evidence.page != null) return '页码已定位';
  if (evidence.source_url) return '已提供原文链接';
  return '需要补充来源定位';
}

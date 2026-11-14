import { QUERY_MODEL } from './query-package.mjs';

export function parseScopes(body) {
  if (!body || body.model !== QUERY_MODEL || !Array.isArray(body.items) || body.total !== body.items.length) throw new Error('检索范围目录格式不完整。');
  const keys = new Set();
  for (const scope of body.items) {
    if (!scope || typeof scope.company_code !== 'string' || !/^[A-Za-z0-9_-]{1,32}$/.test(scope.company_code) || typeof scope.period !== 'string' || !/^[A-Za-z0-9_-]{1,32}$/.test(scope.period) || typeof scope.company_name !== 'string' || !scope.company_name.trim() || !Number.isInteger(scope.chunk_count) || scope.chunk_count < 1 || !Array.isArray(scope.documents) || !scope.documents.length) throw new Error('检索范围缺少真实索引信息。');
    const key = JSON.stringify([scope.company_code, scope.period]);
    if (keys.has(key)) throw new Error('检索范围重复。');
    keys.add(key);
    for (const doc of scope.documents) {
      if (!doc || !Array.isArray(doc.pages) || !doc.pages.length || doc.pages.some(p => !Number.isInteger(p) || p < 1) || !Number.isInteger(doc.chunk_count) || doc.chunk_count < 1 || !['selected_pages', 'indexed_fragments', 'all_text_pages'].includes(doc.coverage_kind)) throw new Error('报告覆盖信息不完整。');
    }
    if (scope.documents.reduce((count, doc) => count + doc.chunk_count, 0) !== scope.chunk_count) throw new Error('索引数量不一致。');
  }
  return body.items;
}

export function selectScope(items, company, period) {
  const scopes = items.filter(item => item.company_code === company);
  return scopes.find(item => item.period === period) ?? scopes.at(-1) ?? null;
}

export function coverageText(scope) {
  return scope.documents.map(doc => `${doc.coverage_kind === 'indexed_fragments' ? '片段覆盖' : doc.coverage_kind === 'all_text_pages' ? '已索引文本页' : '选页覆盖'}：物理页 ${doc.pages.join('、')}${doc.total_pages ? ` / 报告共 ${doc.total_pages} 页` : ''}`).join('；') + '。仅检索已索引原文，不代表完整披露覆盖或金额已复核。';
}

export function createRequestGate() {
  let current;
  return {
    begin() {
      current?.controller.abort();
      current = { controller: new AbortController() };
      return current;
    },
    isCurrent(request) { return request === current; },
    cancel() { current?.controller.abort(); current = undefined; },
  };
}

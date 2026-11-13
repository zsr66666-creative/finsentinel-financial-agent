export const QUERY_MODEL = 'BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620';

/** Keep the natural-language question inseparable from its generated vector. */
export function parseQueryPackage(source) {
  const p = JSON.parse(source);
  if (!p || p.model !== QUERY_MODEL || p.query_prefix !== '为这个句子生成表示以用于检索相关文章：') throw new Error('查询模型或检索前缀不匹配，请重新导出。');
  for (const key of ['question', 'company_code', 'period']) {
    if (typeof p[key] !== 'string' || !p[key].trim() || p[key].length > (key === 'question' ? 500 : 32)) throw new Error('查询问题或研究范围不完整。');
  }
  if (!Array.isArray(p.embedding) || p.embedding.length !== 512 || p.embedding.some(x => typeof x !== 'number' || !Number.isFinite(x))) throw new Error('需要有效的 512 维真实查询向量。');
  const norm = p.embedding.reduce((s, x) => s + x * x, 0);
  if (norm < 0.99 || norm > 1.01) throw new Error('查询向量尚未归一化。');
  return { query: p.question, vector: p.embedding, model: p.model, company_code: p.company_code, period: p.period, top_k: 5 };
}

'use client';

import { useRef, useState } from 'react';
import { parseQueryPackage } from '@/lib/query-package.mjs';

type Query = { query: string; vector: number[]; model: string; company_code: string; period: string; top_k: number };
type Candidate = { chunk_id: string; provenance: { text?: string; page?: number; company_code?: string; period?: string; statement_scope?: string; document_sha256?: string; source_status?: string }; bm25_rank: number | null; vector_rank: number | null };
type SearchResult = { items: Candidate[]; retrieval_mode: string; warnings: string[]; duration_ms: number; encoding_ms?: number };

export function EvidenceSearch() {
  const [query, setQuery] = useState<Query | null>(null);
  const [question, setQuestion] = useState('立讯精密母公司期末应收账款是多少？');
  const [submitted, setSubmitted] = useState('');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const loadVersion = useRef(0);
  async function load(file?: File) {
    const version = ++loadVersion.current;
    setQuery(null); setResult(null); setError('');
    if (!file) return;
    try {
      if (file.size > 100000) throw new Error('查询包超过 100 KB，请选择单个问题的导出文件。');
      const parsed = parseQueryPackage(await file.text());
      if (version === loadVersion.current) setQuery(parsed);
    } catch (e) { if (version === loadVersion.current) setError(e instanceof Error ? e.message : '无法读取查询包。'); }
  }
  async function search(online = false) {
    if (busy || (online ? !question.trim() : !query)) return;
    setSubmitted(online ? question.trim() : query!.query);
    setBusy(true); setError(''); setResult(null);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const endpoint = online ? 'text' : 'vector';
      const payload = online ? { query: question.trim(), company_code: '002475', period: '2026H1', top_k: 5 } : query;
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/evidence/search/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 429 ? '编码服务繁忙，请稍后重试。' : response.status === 503 ? '编码或检索服务暂不可用，请稍后重试；未生成结论。' : `证据检索失败（${response.status}），请稍后重试。`);
      const body = await response.json();
      if (!Array.isArray(body.items) || !Array.isArray(body.warnings) || typeof body.retrieval_mode !== 'string' || typeof body.duration_ms !== 'number' || body.items.some((item: Candidate) => !item || typeof item.chunk_id !== 'string' || !item.provenance)) throw new Error('检索结果格式不完整。');
      setResult(body);
    } catch (e) { setError(e instanceof Error && e.name === 'AbortError' ? '检索超时，请重试。' : e instanceof Error ? e.message : '网络连接失败。'); }
    finally { clearTimeout(timer); setBusy(false); }
  }
  return <section className="panel comparison-card retrieval-card" aria-labelledby="retrieval-title">
    <div className="panel-heading"><div><h2 id="retrieval-title">候选证据检索 <span>RETRIEVE</span></h2><p>查找相关原文，与上方已复核的金额比较相互独立。</p></div><span className="badge warning">研究预览</span></div>
    <p>直接输入问题，系统使用固定 BGE 模型在线编码，再检索已入库原文。</p>
    <form onSubmit={event => { event.preventDefault(); void search(true); }}>
      <label htmlFor="evidence-question">研究问题</label>
      <textarea id="evidence-question" rows={3} maxLength={500} value={question} disabled={busy} onChange={event => { setQuestion(event.target.value); setResult(null); setError(''); }} />
      <div className="form-footer"><span>当前语料：立讯精密 · 2026H1 · 已入库片段</span><button className="primary-button" disabled={busy || !question.trim()} type="submit">{busy ? '检索中…' : '在线检索证据 →'}</button></div>
    </form>
    <details className="retrieval-advanced"><summary>高级选项：导入本地查询包</summary>
    <label htmlFor="query-package">导入问题查询包（JSON）</label>
    <input id="query-package" type="file" accept=".json,application/json" disabled={busy} onChange={e => { void load(e.target.files?.[0]); e.target.value = ''; }} />
    {query && <div className="review-callout"><strong>{query.query}</strong><p>{query.company_code} · {query.period} · BGE / 512 维</p></div>}
    <div className="form-footer"><span>仅检索已入库片段，不代表覆盖整份财报</span><button className="primary-button" disabled={!query || busy} onClick={() => void search()}>{busy ? '检索中…' : '检索候选证据 →'}</button></div>
    </details>
    <div aria-live="polite" aria-busy={busy}>{error && <p className="error" role="alert">{error}</p>}{result && <>
      <p className="submitted-question">{submitted}</p>
      <div className="result-meta">{typeof result.encoding_ms === 'number' && <span>查询编码 <strong>{result.encoding_ms.toFixed(1)} ms</strong></span>}<span>模式 <strong>{result.retrieval_mode}</strong></span><span>服务耗时 <strong>{result.duration_ms.toFixed(1)} ms</strong></span></div>
      <p className="review-callout">以下均为候选片段，排名不是置信度。未命中也不能据此断言财报未披露；金额、单位和报表口径仍需复核。</p>
      {result.warnings.length > 0 && <p role="status">检索提示：{result.warnings.join(' / ')}</p>}
      {!result.items.length && <p>当前范围未返回候选片段，请核对公司、报告期与入库覆盖范围。</p>}
      <ol className="retrieval-candidates">{result.items.map(item => <li key={item.chunk_id}><div className="section-title"><strong>物理页码：{item.provenance.page ?? '未知'}</strong><span>词法 #{item.bm25_rank ?? '—'} · 向量 #{item.vector_rank ?? '—'}</span></div><p className="retrieval-text">{item.provenance.text || '该片段未提供原文'}</p><small>{item.provenance.company_code} · {item.provenance.period} · {item.provenance.statement_scope === 'parent' ? '母公司' : item.provenance.statement_scope === 'consolidated' ? '合并' : '口径未标注'}</small><details><summary>来源标识与校验信息</summary><code>{item.chunk_id}</code><p>PDF SHA-256：{item.provenance.document_sha256 ?? '未提供'}</p><p>来源状态：{item.provenance.source_status ?? '未标注'}</p></details></li>)}</ol>
    </>}</div>
  </section>;
}

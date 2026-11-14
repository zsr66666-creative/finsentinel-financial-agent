'use client';

import { useEffect, useRef, useState } from 'react';
import { parseQueryPackage } from '@/lib/query-package.mjs';
import { parseScopes, selectScope, createRequestGate, coverageText, type EvidenceScope } from '@/lib/evidence-scopes.mjs';

type Query = { query: string; vector: number[]; model: string; company_code: string; period: string; top_k: number };
type Candidate = { chunk_id: string; provenance: { text?: string; page?: number; company_code?: string; period?: string; statement_scope?: string; document_sha256?: string; source_status?: string; source_url?: string }; bm25_rank: number | null; vector_rank: number | null };
type SearchResult = { items: Candidate[]; retrieval_mode: string; warnings: string[]; duration_ms: number; encoding_ms?: number };

export function EvidenceSearch() {
  const [query, setQuery] = useState<Query | null>(null);
  const [question, setQuestion] = useState('立讯精密母公司期末应收账款是多少？');
  const [submitted, setSubmitted] = useState('');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const loadVersion = useRef(0);
  const gate = useRef(createRequestGate());
  const [scopes, setScopes] = useState<EvidenceScope[]>([]);
  const [selected, setSelected] = useState('');
  const [catalogBusy, setCatalogBusy] = useState(true);
  const [catalogError, setCatalogError] = useState('');
  const [catalogRetry, setCatalogRetry] = useState(0);
  const scopeKey = (scope: EvidenceScope) => JSON.stringify([scope.company_code, scope.period]);
  const scope = scopes.find(item => scopeKey(item) === selected);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 10000);
    setCatalogBusy(true); setCatalogError('');
    void (async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/evidence/scopes`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(`范围目录暂不可用（${response.status}）。`);
        const items = parseScopes(await response.json());
        if (!active) return;
        setScopes(items);
        setSelected(previous => items.some(item => scopeKey(item) === previous) ? previous : items.length ? scopeKey(items.find(item => item.company_code === '002475' && item.period === '2026H1') ?? items[0]) : '');
      } catch (e) {
        if (active) { setScopes([]); setSelected(''); setCatalogError(timedOut ? '范围目录加载超时，请重试。' : e instanceof Error ? e.message : '无法加载范围目录。'); }
      } finally { clearTimeout(timer); if (active) setCatalogBusy(false); }
    })();
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [catalogRetry]);
  useEffect(() => () => { gate.current.cancel(); ++loadVersion.current; }, []);
  function invalidate() {
    gate.current.cancel(); ++loadVersion.current;
    setQuery(null); setResult(null); setError(''); setBusy(false); setSubmitted('');
  }
  function changeScope(next: EvidenceScope | null) {
    invalidate(); setSelected(next ? scopeKey(next) : '');
  }
  async function load(file?: File) {
    invalidate();
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
    if (busy || (online ? !question.trim() || !scope || catalogBusy : !query)) return;
    ++loadVersion.current;
    const request = gate.current.begin();
    setSubmitted(online ? `${scope!.company_name} · ${scope!.period}：${question.trim()}` : `${query!.company_code} · ${query!.period}：${query!.query}`);
    setBusy(true); setError(''); setResult(null);
    const controller = request.controller;
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const endpoint = online ? 'text' : 'vector';
      const payload = online ? { query: question.trim(), company_code: scope!.company_code, period: scope!.period, top_k: 5 } : query;
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/evidence/search/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 429 ? '编码服务繁忙，请稍后重试。' : response.status === 503 ? '编码或检索服务暂不可用，请稍后重试；未生成结论。' : `证据检索失败（${response.status}），请稍后重试。`);
      const body = await response.json();
      if (!Array.isArray(body.items) || !Array.isArray(body.warnings) || typeof body.retrieval_mode !== 'string' || typeof body.duration_ms !== 'number' || body.items.some((item: Candidate) => !item || typeof item.chunk_id !== 'string' || !item.provenance)) throw new Error('检索结果格式不完整。');
      if (gate.current.isCurrent(request)) setResult(body);
    } catch (e) { if (gate.current.isCurrent(request)) setError(e instanceof Error && e.name === 'AbortError' ? '检索超时，请重试。' : e instanceof Error ? e.message : '网络连接失败。'); }
    finally { clearTimeout(timer); if (gate.current.isCurrent(request)) setBusy(false); }
  }
  return <section className="panel comparison-card retrieval-card" aria-labelledby="retrieval-title">
    <div className="panel-heading"><div><h2 id="retrieval-title">候选证据检索 <span>RETRIEVE</span></h2><p>查找相关原文，与上方已复核的金额比较相互独立。</p></div><span className="badge warning">研究预览</span></div>
    <p>直接输入问题，系统使用固定 BGE 模型在线编码，再检索已入库原文。</p>
    <div className="evidence-scope-controls" aria-busy={catalogBusy}>
      <label htmlFor="evidence-company">公司<select id="evidence-company" value={scope?.company_code ?? ''} disabled={catalogBusy || !scopes.length} onChange={event => changeScope(selectScope(scopes, event.target.value, scope?.period ?? ''))}>
        {!scopes.length && <option value="">{catalogBusy ? '加载范围…' : '暂无可检索公司'}</option>}
        {Array.from(new Map(scopes.map(item => [item.company_code, item.company_name])).entries()).map(([code, name]) => <option key={code} value={code}>{name} · {code}</option>)}
      </select></label>
      <label htmlFor="evidence-period">报告期<select id="evidence-period" value={scope?.period ?? ''} disabled={catalogBusy || !scope} onChange={event => changeScope(selectScope(scopes, scope!.company_code, event.target.value))}>
        {!scope && <option value="">暂无可检索报告期</option>}
        {scopes.filter(item => item.company_code === scope?.company_code).map(item => <option key={item.period} value={item.period}>{item.period}</option>)}
      </select></label>
    </div>
    {catalogError && <div className="error" role="alert">{catalogError} <button type="button" className="secondary-button" onClick={() => { invalidate(); setCatalogRetry(value => value + 1); }}>重新加载范围</button></div>}
    {!catalogBusy && !catalogError && !scopes.length && <p role="status">当前还没有可检索的真实索引。采集完成的报告需建索引后才会出现在此处。</p>}
    {scope && <p className="evidence-coverage">{coverageText(scope)}</p>}
    <form onSubmit={event => { event.preventDefault(); void search(true); }}>
      <label htmlFor="evidence-question">研究问题</label>
      <textarea id="evidence-question" rows={3} maxLength={500} value={question} onChange={event => { invalidate(); setQuestion(event.target.value); }} />
      <div className="form-footer"><span>{scope ? `${scope.company_name} · ${scope.period} · ${scope.chunk_count} 个已入库片段` : '请选择实际已入库范围'}</span><button className="primary-button" disabled={busy || catalogBusy || !scope || !question.trim()} type="submit">{busy ? '检索中…' : '在线检索证据 →'}</button></div>
    </form>
    <details className="retrieval-advanced"><summary>高级选项：导入本地查询包</summary>
    <label htmlFor="query-package">导入问题查询包（JSON）</label>
    <input id="query-package" type="file" accept=".json,application/json" onChange={e => { void load(e.target.files?.[0]); e.target.value = ''; }} />
    {query && <div className="review-callout"><strong>{query.query}</strong><p>{query.company_code} · {query.period} · BGE / 512 维</p></div>}
    <div className="form-footer"><span>仅检索已入库片段，不代表覆盖整份财报</span><button className="primary-button" disabled={!query || busy} onClick={() => void search()}>{busy ? '检索中…' : '检索候选证据 →'}</button></div>
    </details>
    <div aria-live="polite" aria-busy={busy}>{error && <p className="error" role="alert">{error}</p>}{result && <>
      <p className="submitted-question">{submitted}</p>
      <div className="result-meta">{typeof result.encoding_ms === 'number' && <span>查询编码 <strong>{result.encoding_ms.toFixed(1)} ms</strong></span>}<span>模式 <strong>{result.retrieval_mode}</strong></span><span>服务耗时 <strong>{result.duration_ms.toFixed(1)} ms</strong></span></div>
      <p className="review-callout">以下均为候选片段，排名不是置信度。未命中也不能据此断言财报未披露；金额、单位和报表口径仍需复核。</p>
      {result.warnings.length > 0 && <p role="status">检索提示：{result.warnings.join(' / ')}</p>}
      {!result.items.length && <p>当前范围未返回候选片段，请核对公司、报告期与入库覆盖范围。</p>}
      <ol className="retrieval-candidates">{result.items.map(item => <li key={item.chunk_id}><div className="section-title"><strong>物理页码：{item.provenance.page ?? '未知'}</strong><span>词法 #{item.bm25_rank ?? '—'} · 向量 #{item.vector_rank ?? '—'}</span></div><p className="retrieval-text">{item.provenance.text || '该片段未提供原文'}</p><small>{item.provenance.company_code} · {item.provenance.period} · {item.provenance.statement_scope === 'parent' ? '母公司' : item.provenance.statement_scope === 'consolidated' ? '合并' : '口径未标注'}</small><details><summary>来源标识与校验信息</summary><code>{item.chunk_id}</code><p>PDF SHA-256：{item.provenance.document_sha256 ?? '未提供'}</p><p>来源状态：{item.provenance.source_status ?? '未标注'}</p><p>来源：{item.provenance.source_url?.startsWith('https://static.cninfo.com.cn/') ? <a href={item.provenance.source_url} target="_blank" rel="noopener noreferrer">官方 PDF ↗</a> : '本地 PDF，请结合哈希与物理页码核对'}</p></details></li>)}</ol>
    </>}</div>
  </section>;
}

'use client';

import Link from 'next/link';
import { ProfileLink } from '@/components/demo-session';
import { FormEvent, useState } from 'react';

const example = (scope: string, relation: string) => `立讯精密2026年6月30日${scope}应收账款较2025年12月31日是否${relation}？`;
type Result = { status: string; claim_true: boolean | null; reason?: string; current_period?: string; previous_period?: string; current_value?: string; previous_value?: string; difference?: string; statement_scope?: string; evidence_ids: string[]; evidence?: { chunk_id: string; page: number }[] };
const reasons: Record<string, string> = { unsupported_or_ambiguous_query: '问题不在当前支持范围内，或缺少明确的报表口径。', period_not_reviewed: '该日期组合尚未完成证据复核，暂不能给出结论。', missing_or_unverified_evidence: '所需证据缺失或来源校验未通过，暂不能给出结论。' };

export default function ComparePage() {
  const [question, setQuestion] = useState(example('母公司', '未增加'));
  const [submitted, setSubmitted] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [connection, setConnection] = useState<'idle' | 'pending' | 'connected' | 'error'>('idle');
  const connectionLabel = { idle: '待验证', pending: '核对中', connected: '已连接', error: '请求失败' }[connection];
  const bannerLabel = { idle: '待请求 · API 待验证', pending: '核对中 · API 请求中', connected: 'API 已连接', error: 'API 请求失败' }[connection];
  function change(value: string) { setQuestion(value); setResult(null); setError(''); }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy || !question.trim()) return;
    const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), 10000);
    setBusy(true); setConnection('pending'); setResult(null); setError(''); setSubmitted(question.trim());
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? '';
      const response = await fetch(`${base}/api/v1/evidence/compare`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: question.trim() }), signal: controller.signal });
      if (!response.ok) throw new Error(response.status === 503 ? '证据服务暂不可用，请稍后重试。' : `请求失败（${response.status}），请稍后重试。`);
      const body: Result = await response.json();
      if (!['supported', 'needs_review'].includes(body.status) || !Array.isArray(body.evidence_ids) || (body.status === 'supported' && (typeof body.claim_true !== 'boolean' || !body.evidence_ids.length))) throw new Error('返回结果不完整，请稍后重试。');
      setResult(body); setConnection('connected');
    } catch (cause) { setConnection('error'); setError(cause instanceof Error && cause.name === 'AbortError' ? '请求超时，请重试。' : cause instanceof Error ? cause.message : '网络连接失败，请重试。'); }
    finally { clearTimeout(timeout); setBusy(false); }
  }
  return <div className="shell comparison-shell">
    <aside className="sidebar"><Link className="brand" href="/"><span className="brand-mark">F<span /></span><span>FinSentinel<small>金融证据链研判平台</small></span></Link><div className="workspace"><span className="workspace-icon">研</span><span>消费电子研究组<small>RESEARCH WORKSPACE</small></span></div><div className="nav-caption">工作台</div><nav><Link className="nav-item" href="/">◈ 监控总览</Link><Link className="nav-item active" href="/compare">⇄ 证据比较</Link></nav><div className="sidebar-bottom"><div className={`health ${connection}`}><i />证据服务<span>{connectionLabel}</span></div><ProfileLink /></div></aside>
    <main className="main comparison-main"><header className="topbar"><div className="breadcrumb"><Link href="/">研究工作台</Link> <span>/</span> <strong>证据比较</strong></div><div className="topbar-right"><span className="live-dot" />真实财报证据<span className="vertical-rule" /><span>立讯精密 · 2026 半年度报告</span><ProfileLink compact /></div></header><div className="content">
      <div className="page-heading"><div><div className="eyebrow">REVIEWED FINANCIAL EVIDENCE</div><h1>应收账款变动核对</h1><p>用已复核的真实财报证据，比较期间、口径与金额变化。</p></div><Link className="secondary-button" href="/">返回总览</Link></div>
      <div className={`mode-banner connection-banner ${connection}`} role="status"><span>● {bannerLabel}</span><strong>真实公开材料</strong><span>当前支持母公司或合并口径的应收账款期间比较。</span></div>
      <section className="panel comparison-card comparison-form-card"><div className="panel-heading"><div><h2>提出比较问题 <span>COMPARE</span></h2><p>请写清公司、日期、报表口径和“增加／未增加”判断。</p></div><span className="subtle-chip">已复核数据</span></div><div className="comparison-examples">{[['母公司', '未增加'], ['合并', '增加']].map(([scope, relation]) => <button type="button" key={scope} disabled={busy} onClick={() => change(example(scope, relation))}>{scope} · 是否{relation}</button>)}</div><form onSubmit={submit}><label htmlFor="comparison-question">比较问题</label><textarea id="comparison-question" rows={4} maxLength={500} value={question} disabled={busy} onChange={e => change(e.target.value)} /><div className="form-footer"><span>{question.length}/500 字</span><button className="primary-button" type="submit" disabled={busy || !question.trim()}>{busy ? '正在核对证据…' : '核对并比较 →'}</button></div></form></section>
      <div aria-live="polite" aria-busy={busy}>{error && <p className="error" role="alert">{error} 未生成比较结论。</p>}{result && <section className="panel comparison-card result-card"><div className="result-header"><div><div className="eyebrow">{result.status === 'supported' ? 'EVIDENCE SUPPORTED' : 'REVIEW REQUIRED'}</div><h2>{result.status === 'supported' ? '证据支持的比较结果' : '需要人工复核'}</h2></div><span className={`badge ${result.status === 'supported' ? 'success' : 'warning'}`}>{result.status === 'supported' ? '已支持' : '待复核'}</span></div><p className="submitted-question">{submitted}</p>{result.status === 'needs_review' ? <div className="review-callout"><strong>暂不输出数值结论</strong><p>{reasons[result.reason ?? ''] ?? '证据尚不足，暂不能给出结论。'}</p></div> : <><div className={`comparison-verdict ${result.claim_true ? 'positive' : 'negative'}`}><span>{result.claim_true ? '✓' : '×'}</span>{result.claim_true ? '是，该问题中的判断成立。' : '否，该问题中的判断不成立。'}</div><div className="result-meta"><span>报表口径 <strong>{result.statement_scope === 'parent' ? '母公司' : '合并'}</strong></span><span>单位 <strong>CNY</strong></span></div><dl className="comparison-values"><div><dt>对比期 · {result.previous_period}</dt><dd>{result.previous_value} 元</dd></div><div><dt>本期 · {result.current_period}</dt><dd>{result.current_value} 元</dd></div><div><dt>本期 − 对比期</dt><dd className={String(result.difference).startsWith('-') ? 'down' : 'up'}>{result.difference} 元</dd></div></dl><div className="evidence-section"><div className="section-title"><h3>证据定位</h3><span>{result.evidence_ids.length} 处来源</span></div><p>《立讯精密：2026年半年度报告》 · 以下为 PDF 阅读器物理页码</p><ul>{result.evidence_ids.map((id, index) => <li key={id}><span className="source-index">[{index + 1}]</span><code>{id}</code><small>{result.evidence?.find(item => item.chunk_id === id) ? `第 ${result.evidence.find(item => item.chunk_id === id)!.page} 页` : '已复核'}</small></li>)}</ul></div><p className="result-footnote">本结果基于指定报告的已复核日期、单位及口径，不代表未来预测。</p></>}</section>}</div><footer className="page-footer"><span>FinSentinel / Evidence before conclusions.</span><span>公开材料研究辅助 · 非投资建议</span></footer>
    </div></main></div>;
}

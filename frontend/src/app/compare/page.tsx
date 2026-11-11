'use client';

import Link from 'next/link';
import { FormEvent, useState } from 'react';

const example = (scope: string, relation: string) => `立讯精密2026年6月30日${scope}应收账款较2025年12月31日是否${relation}？`;
type Result = {
  status: string; claim_true: boolean | null; reason?: string;
  current_period?: string; previous_period?: string; current_value?: string;
  previous_value?: string; difference?: string; statement_scope?: string;
  evidence_ids: string[]; evidence?: { chunk_id: string; page: number }[];
};
const reasons: Record<string, string> = {
  unsupported_or_ambiguous_query: '问题不在当前支持范围内，或缺少明确的报表口径。请参考上方示例。',
  period_not_reviewed: '该日期组合尚未完成证据复核，暂不能给出结论。',
  missing_or_unverified_evidence: '所需证据缺失或来源校验未通过，暂不能给出结论。',
};

export default function ComparePage() {
  const [question, setQuestion] = useState(example('母公司', '未增加'));
  const [submitted, setSubmitted] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  function change(value: string) { setQuestion(value); setResult(null); setError(''); }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !question.trim()) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    setBusy(true); setResult(null); setError(''); setSubmitted(question.trim());
    try {
      // An empty production base uses the same-origin Nginx API route.
      const base = process.env.NEXT_PUBLIC_API_URL ?? '';
      const response = await fetch(`${base}/api/v1/evidence/compare`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }), signal: controller.signal,
      });
      if (!response.ok) throw new Error(response.status === 503 ? '证据服务暂不可用，请稍后重试。' : `请求失败（${response.status}），请稍后重试。`);
      const body: Result = await response.json();
      if (!['supported', 'needs_review'].includes(body.status) || !Array.isArray(body.evidence_ids) ||
          (body.status === 'supported' && (typeof body.claim_true !== 'boolean' || !body.evidence_ids.length))) {
        throw new Error('返回结果不完整，请稍后重试。');
      }
      setResult(body);
    } catch (cause) {
      setError(cause instanceof Error && cause.name === 'AbortError' ? '请求超时，请重试。' : cause instanceof Error ? cause.message : '网络连接失败，请重试。');
    } finally { clearTimeout(timeout); setBusy(false); }
  }

  return <main className="comparison-page">
    <Link href="/">← 返回研究工作台</Link>
    <header><p className="eyebrow">真实财报 · 证据比较</p><h1>应收账款是否增加？</h1>
      <p>立讯精密 · 2026 年半年度报告 · 金额单位：元</p></header>
    <div className="comparison-note">本页读取已复核的真实财报证据，与工作台演示数据分开展示。目前支持 2026年6月30日与2025年12月31日、母公司或合并应收账款的“增加／未增加”判断。</div>
    <section className="comparison-card">
      <h2>选择示例或输入问题</h2>
      <div className="comparison-examples">{[['母公司', '未增加'], ['合并', '增加']].map(([scope, relation]) =>
        <button type="button" key={scope} disabled={busy} onClick={() => change(example(scope, relation))}>{scope} · 是否{relation}</button>)}</div>
      <form onSubmit={submit}><label htmlFor="comparison-question">比较问题</label>
        <textarea id="comparison-question" rows={4} maxLength={500} value={question} disabled={busy} onChange={e => change(e.target.value)} />
        <button className="primary-button" type="submit" disabled={busy || !question.trim()}>{busy ? '正在核对证据…' : '核对并比较'}</button></form>
    </section>
    <div aria-live="polite" aria-busy={busy}>
      {error && <p className="error" role="alert">{error} 未生成比较结论。</p>}
      {result && <section className="comparison-card"><h2>{result.status === 'supported' ? '证据支持的比较结果' : '待复核'}</h2><p>{submitted}</p>
        {result.status === 'needs_review' ? <p>{reasons[result.reason ?? ''] ?? '证据尚不足，暂不能给出结论。'}</p> : <>
          <p className="comparison-verdict">{result.claim_true ? '是，该问题中的判断成立。' : '否，该问题中的判断不成立。'}</p>
          <p>报表口径：{result.statement_scope === 'parent' ? '母公司' : '合并'}</p>
          <dl className="comparison-values"><div><dt>{result.previous_period}</dt><dd>{result.previous_value} 元</dd></div>
            <div><dt>{result.current_period}</dt><dd>{result.current_value} 元</dd></div>
            <div><dt>本期 − 对比期</dt><dd>{result.difference} 元</dd></div></dl>
          <h3>证据定位</h3><p>《立讯精密：2026年半年度报告》；以下为 PDF 阅读器物理页码。</p>
          <ul>{result.evidence_ids.map(id => <li key={id}><code>{id}</code> · {id.includes('fulltext') || id.endsWith('s8') ? '报表标题' : '数值行'}
            {result.evidence?.find(item => item.chunk_id === id) && ` · 第 ${result.evidence.find(item => item.chunk_id === id)!.page} 页`}</li>)}</ul>
          <p>本结果基于指定报告的已复核日期、单位及口径，不代表未来预测。原始 PDF 尚未提供在线预览。</p>
        </>}
      </section>}
    </div>
  </main>;
}

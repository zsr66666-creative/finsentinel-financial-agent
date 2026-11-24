'use client';
import { useEffect, useState } from 'react';
import { authFetch } from '@/lib/accounts.mjs';
import { normalizeFinancialAnalysis } from '@/lib/domain.mjs';

type Row = Record<string, any>;

function Chart({ chart }: { chart: Row }) {
  const series = chart.series ?? [];
  const values = series.flatMap((item: Row) => (item.points ?? [{ value: item.value }]).map((point: Row) => point.value == null ? null : Math.abs(Number(point.value)))).filter((value: number | null): value is number => value !== null);
  const max = Math.max(1, ...values);
  return <section className="panel padded financial-analysis-chart"><h3>{chart.title}</h3><p>{chart.unit === '%' ? '同比变化（%）' : '经营现金流 / 归母净利润'}</p><div className="financial-analysis-bars" role="img" aria-label={chart.title}>
    {series.flatMap((item: Row) => (item.points ?? [{ period: chart.to_period, value: item.value }]).map((point: Row) => <div className="financial-analysis-row" key={`${item.name}-${point.period}`}><span>{item.name} · {point.period}</span><div className="financial-analysis-track"><span className={Number(point.value) < 0 ? 'negative' : ''} style={{ width: point.value == null ? 0 : `${Math.max(2, Math.abs(Number(point.value)) / max * 100)}%` }} /></div><b>{point.value == null ? '—' : `${point.value}${chart.unit === 'ratio' ? '倍' : chart.unit}`}</b></div>))}
  </div><small>数据由确定性公式生成；缺失年度不插补。</small></section>;
}

export function FinancialAnalysisPanel({ companyId, defaultFrom = '2023FY', defaultTo = '2024FY' }: { companyId: string; defaultFrom?: string; defaultTo?: string }) {
  const [fromPeriod, setFromPeriod] = useState(defaultFrom); const [toPeriod, setToPeriod] = useState(defaultTo);
  const [result, setResult] = useState<Row | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  useEffect(() => { setResult(null); setError(''); }, [companyId]);
  async function run() { setLoading(true); setError(''); try { const response = await authFetch(`/api/v1/companies/${encodeURIComponent(companyId)}/financial-analysis?from_period=${encodeURIComponent(fromPeriod)}&to_period=${encodeURIComponent(toPeriod)}`, { cache: 'no-store' }); if (!response.ok) throw new Error(`财务分析接口返回 ${response.status}`); setResult(normalizeFinancialAnalysis(await response.json())); } catch (e) { setError(e instanceof Error ? e.message : '财务分析失败'); } finally { setLoading(false); } }
  return <section className="financial-analysis-panel"><div className="panel comparison-card"><div className="panel-heading"><div><h2>现金流与净利润背离分析</h2><p>仅使用已人工核验、口径一致且可回溯到年报页码的数据。</p></div><span className="financial-review-tag">确定性公式</span></div><div className="financial-analysis-controls"><label>起始年度<select value={fromPeriod} onChange={e => setFromPeriod(e.target.value)}>{Array.from({ length: 11 }, (_, i) => `${2026 - i}FY`).map(period => <option key={period}>{period}</option>)}</select></label><label>截止年度<select value={toPeriod} onChange={e => setToPeriod(e.target.value)}>{Array.from({ length: 11 }, (_, i) => `${2026 - i}FY`).map(period => <option key={period}>{period}</option>)}</select></label><button type="button" className="primary-button" disabled={loading} onClick={run}>{loading ? '计算中…' : '运行可审计分析'}</button></div>{error && <p className="portal-state error" role="alert">{error}</p>}</div>{result && <><div className={`panel comparison-card financial-analysis-conclusion ${result.status === 'completed' ? 'verified' : 'review'}`}><span>{result.status === 'completed' ? '结构化规则结论' : '需人工复核'}</span><h2>{result.classification}</h2><p>{result.reason ?? '确定性公式计算；不构成投资建议。'}</p></div><div className="financial-analysis-chart-grid">{result.charts.map((chart: Row) => <Chart chart={chart} key={chart.id} />)}</div><section className="panel comparison-card"><h2>计算输入与证据</h2>{Object.entries(result.metrics).length ? Object.entries(result.metrics).map(([name, metric]: [string, any]) => <article className="financial-analysis-metric" key={name}><strong>{name}</strong><b>{metric.value} {metric.unit}</b><code>{metric.formula}</code><small>输入：{metric.input_ids?.join('、')} · PDF 页码：{metric.pages?.join('、')}</small></article>) : <p className="empty">缺少完整且已核验的输入，当前不生成数值结论。</p>}{result.evidence.map((item: Row) => <blockquote className="financial-proof" key={item.evidence_id}><strong>{item.metric} · {item.period} · PDF 第 {item.page ?? '—'} 页</strong><p>{item.excerpt ?? '缺少原文摘录'}</p><small>SHA256 {item.document_sha256 ?? '未核验'}</small>{item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer">打开年报 PDF ↗</a>}</blockquote>)}</section></>}</section>;
}

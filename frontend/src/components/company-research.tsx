'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ProfileLink } from '@/components/demo-session';
import { EvidenceSearch } from '@/components/evidence-search';
import { formatMetric, normalizeCollection } from '@/lib/domain.mjs';
type Row = Record<string, any>;
export function CompanyResearch({ companyId }: { companyId: string }) {
  const [company, setCompany] = useState<Row | null>(null);
  const [metrics, setMetrics] = useState<Row[]>([]);
  const [alerts, setAlerts] = useState<Row[]>([]);
  const [period, setPeriod] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    let active = true;
    setLoading(true); setError(''); setWarning(''); setCompany(null); setMetrics([]); setAlerts([]); setPeriod('all');
    async function get(path: string, optional = false) {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}${path}`, { signal: controller.signal });
      if (optional && response.status === 404) return { items: [] };
      if (!response.ok) throw new Error(response.status === 404 ? '未找到该公司，请从研究库重新选择。' : `数据服务返回 ${response.status}`);
      return response.json();
    }
    async function load() {
      try {
        const item = await get(`/api/v1/companies/${encodeURIComponent(companyId)}`);
        if (!active) return;
        if (!item || item.id !== companyId) throw new Error('公司数据标识不匹配。');
        setCompany(item);
        if (item.data_mode === 'real_pdf_candidates') return;
        const results = await Promise.allSettled([get(`/api/v1/companies/${encodeURIComponent(companyId)}/metrics`, true), get('/api/v1/alerts')]);
        if (!active) return;
        const notes = [];
        if (results[0].status === 'fulfilled') setMetrics(normalizeCollection(results[0].value)); else notes.push('财务指标加载失败');
        if (results[1].status === 'fulfilled') setAlerts(normalizeCollection(results[1].value).filter((row: Row) => row.company_id === companyId)); else notes.push('风险告警加载失败');
        setWarning(notes.join('；'));
      } catch (e) { if (active) setError(e instanceof Error && e.name === 'AbortError' ? '请求超时，请重试。' : e instanceof Error ? e.message : '加载失败'); }
      finally { clearTimeout(timer); if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [companyId, retry]);
  const periods = Array.from(new Set([...metrics, ...alerts].map(row => String(row.period ?? '')).filter(Boolean))).sort().reverse();
  const shownMetrics = metrics.filter(row => period === 'all' || row.period === period);
  const shownAlerts = alerts.filter(row => period === 'all' || row.period === period);
  const indexedOnly = company?.data_mode === 'real_pdf_candidates';
  const demo = company && !['real', 'reviewed_real_pdf', 'real_pdf_candidates'].includes(company.data_mode);
  return <div className="shell"><aside className="sidebar"><Link href="/" className="brand"><span className="brand-mark">F</span><span>FinSentinel<small>金融证据链研判平台</small></span></Link><div className="nav-caption">研究工作台</div><nav><Link className="nav-item" href="/">◈ 监控总览</Link><Link className="nav-item active" href="/" aria-current="page">▦ 公司研究</Link><Link className="nav-item" href="/compare">⇄ 证据比较</Link></nav><div className="sidebar-bottom"><ProfileLink /></div></aside><main className="main"><header className="topbar"><div className="breadcrumb"><Link href="/">研究工作台</Link><span>/</span><strong>公司详情</strong></div><ProfileLink compact /></header><div className="content company-research">
    <div className="page-heading"><div><div className="eyebrow">COMPANY RESEARCH</div><h1>{company?.name ?? '公司研究'}</h1><p>{companyId} · {company?.industry ?? company?.sector ?? '行业待标注'}</p></div><Link className="secondary-button" href="/">返回监控总览</Link></div>
    {loading && <p role="status">正在加载公司数据…</p>}
    {error && <div className="notice error" role="alert">{error}<button onClick={() => setRetry(v => v + 1)}>重新加载</button></div>}
    {company && <><div className={`mode-banner ${demo ? 'synthetic-banner' : ''}`}><strong>{demo ? '演示 / 未验证真实来源' : '真实公开材料'}</strong><span>数据模式：{company.data_mode ?? '未标注'}。接入 API 不代表财务数据已经真实来源复核。</span></div>
    {warning && <div className="notice error" role="alert">{warning}<button onClick={() => setRetry(v => v + 1)}>重试</button></div>}
    {!indexedOnly && <EvidenceSearch key={companyId} companyCode={companyId} />}
    {indexedOnly ? <><p className="review-callout">本公司已接入真实报告原文，尚未建立已复核财务指标或风险结论。下方仅检索实际已索引页，不以缺失值代替零。</p><EvidenceSearch key={companyId} companyCode={companyId} /></> : <>
    <section className="panel comparison-card"><div className="panel-heading"><div><h2>研究范围</h2><p>各报告期分别展示，币种和单位以原记录为准。</p></div><label>报告期 <select aria-label="公司报告期" value={period} onChange={e => setPeriod(e.target.value)}><option value="all">全部报告期</option>{periods.map(p => <option key={p}>{p}</option>)}</select></label></div><p>市场：{company.market ?? company.exchange ?? '未标注'} · 行业：{company.industry ?? company.sector ?? '未标注'}</p></section>
    <section className="panel comparison-card"><div className="panel-heading"><h2>财务指标与来源</h2><span>{shownMetrics.length} 条</span></div><div className="metric-grid">{shownMetrics.map((row, index) => <article className="metric-detail" key={row.id ?? index}><span>{row.metric ?? row.name}</span><strong>{formatMetric(row.value, row.unit)}</strong><small>报告期：{row.period ?? '未标注'} · 单位：{row.unit ?? '未标注'}</small><small>口径：{row.statement_scope ?? '未标注'} · 币种：{row.currency ?? '未标注'}</small><details><summary>证据定位</summary><p>物理页码：{row.source_page ?? '未提供'}</p><p>来源标识：{(row.source_ids ?? row.source_evidence_ids ?? []).join('、') || '未提供'}</p>{typeof row.source_url === 'string' && /^https?:\/\//.test(row.source_url) && <a href={row.source_url} target="_blank" rel="noreferrer">查看来源 ↗</a>}</details></article>)}</div>{!loading && !shownMetrics.length && <p className="empty">该报告期暂无已接入指标；缺失值不按零展示。</p>}</section>
    <section className="panel comparison-card"><div className="panel-heading"><h2>公司风险告警</h2><span>{shownAlerts.length} 条</span></div>{shownAlerts.map((row, index) => <article className="evidence-card" key={row.id ?? index}><h3>{row.title ?? row.rule_name ?? row.id}</h3><p>{row.summary ?? row.description ?? '请回到工作台查看告警详情与人工复核记录。'}</p><small>{row.period} · 等级 {row.severity ?? '未标注'} · 状态 {row.status ?? '待复核'}</small></article>)}{!loading && !shownAlerts.length && <p className="empty">当前报告期未返回告警，不代表没有财务风险。</p>}<Link className="secondary-button" href="/">前往工作台复核</Link></section>
    </>}
    </>}
  </div></main></div>;
}

'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { alertEmptyLabel, connectionStatusLabel, evidenceStatusLabel, filterAlerts, formatMetric, metricStateLabel, normalizeAlert, normalizeCollection, refreshLabel } from '@/lib/domain.mjs';
import { riskCategory, workflowStages } from '@/lib/workflow';
import { fixtureAlerts, fixtureCompanies, fixtureTrend } from '@/lib/fixtures';

type Row = Record<string, any>;
type View = 'overview' | 'alerts' | 'companies' | 'review' | 'evals' | 'data';
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
const severityLabel: Record<string, string> = { high: '高风险', medium: '中风险', low: '低风险' };
const statusLabel: Record<string, string> = { pending: '待复核', confirmed: '已确认', rejected: '已驳回', modified: '已修订' };
const nav = [{ id: 'overview', icon: '◈', label: '监控总览' }, { id: 'alerts', icon: '◇', label: '风险告警' }, { id: 'companies', icon: '▦', label: '公司研究' }, { id: 'review', icon: '✓', label: '人工复核' }, { id: 'evals', icon: '⌁', label: '评测与版本' }, { id: 'data', icon: '▤', label: '数据质量' }];

async function request(path: string, init?: RequestInit) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 7000);
  try {
    const response = await fetch(`${apiUrl}${path}`, { ...init, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...init?.headers } });
    if (!response.ok) throw new Error(`接口返回 ${response.status}`);
    return await response.json();
  } finally { clearTimeout(timeout); }
}

function Badge({ severity, children }: { severity?: string; children?: React.ReactNode }) {
  return <span className={`badge ${severity ?? 'neutral'}`}>{children ?? severityLabel[severity ?? ''] ?? severity}</span>;
}

function Sparkline({ values, accent = false }: { values: number[]; accent?: boolean }) {
  const max = Math.max(...values, 1); const min = Math.min(...values, 0);
  const points = values.map((v, i) => `${i * 100 / Math.max(values.length - 1, 1)},${38 - (v - min) / (max - min || 1) * 33}`).join(' ');
  return <svg viewBox="0 0 100 42" className={`spark ${accent ? 'accent' : ''}`} preserveAspectRatio="none" role="img" aria-label="合成样例趋势图"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" /></svg>;
}

export default function Workbench() {
  const [view, setView] = useState<View>('overview');
  const [alerts, setAlerts] = useState<Row[]>(fixtureAlerts.map(normalizeAlert));
  const [companies, setCompanies] = useState<Row[]>(fixtureCompanies);
  const [selectedId, setSelectedId] = useState(fixtureAlerts[0].id);
  const [tab, setTab] = useState('evidence');
  const [severity, setSeverity] = useState('all');
  const [company, setCompany] = useState('all');
  const [query, setQuery] = useState('');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [errorType, setErrorType] = useState('citation_error');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [evalSummary, setEvalSummary] = useState<Row | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysisCompany, setAnalysisCompany] = useState('');
  const [question, setQuestion] = useState('请分析本报告期的现金流质量与潜在经营风险，并给出证据。');
  const [run, setRun] = useState<Row | null>(null);
  const [companyMetrics, setCompanyMetrics] = useState<Row[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState('');
  const [metricsRetry, setMetricsRetry] = useState(0);
  const [selectedCompany, setSelectedCompany] = useState('');
  const [dataStatus, setDataStatus] = useState<Row | null>(null);
  const [feedbackHistory, setFeedbackHistory] = useState<Row[]>([]);
  const [reviewCandidates, setReviewCandidates] = useState<Row[]>([]);

  async function loadDashboard({ refresh = false } = {}) {
    if (refresh) setRefreshing(true); else setLoading(true);
    setLoadError('');
    try {
      const [a, c] = await Promise.all([request('/api/v1/alerts'), request('/api/v1/companies')]);
      const rows = normalizeCollection(a).map(normalizeAlert); const cs = normalizeCollection(c);
      setAlerts(rows); setCompanies(cs); setSelectedId(rows[0]?.id ?? ''); setAnalysisCompany(cs[0]?.id ?? ''); setSelectedCompany(cs[0]?.id ?? ''); setConnected(true);
      request('/api/v1/evals/summary').then(value => setEvalSummary(value)).catch(() => {});
      request('/api/v1/data/quality').then(value => setDataStatus(value)).catch(() => {});
      request('/api/v1/review/candidates').then(value => setReviewCandidates(normalizeCollection(value))).catch(() => {});
    } catch (error) {
      setConnected(false); setLoadError(error instanceof Error ? error.message : '网络错误'); setAnalysisCompany(fixtureCompanies[0].id); setSelectedCompany(fixtureCompanies[0].id);
    } finally { setLoading(false); setRefreshing(false); }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  useEffect(() => {
    if (!connected || !selectedCompany) { setCompanyMetrics([]); setMetricsError(''); setMetricsLoading(false); return; }
    let active = true;
    setMetricsLoading(true); setMetricsError('');
    request(`/api/v1/companies/${encodeURIComponent(selectedCompany)}/metrics`).then(value => { if (active) setCompanyMetrics(normalizeCollection(value)); }).catch(error => { if (active) { setCompanyMetrics([]); setMetricsError(error instanceof Error ? error.message : '网络错误'); } }).finally(() => active && setMetricsLoading(false));
    return () => { active = false; };
  }, [connected, selectedCompany, metricsRetry]);

  const selected = alerts.find(a => a.id === selectedId) ?? alerts[0];
  const filtered = useMemo(() => filterAlerts(alerts, { severity, company, query, status: view === 'review' ? 'pending' : 'all' }), [alerts, severity, company, query, view]);
  const pending = alerts.filter(a => a.status === 'pending').length;
  const high = alerts.filter(a => a.severity === 'high').length;
  const isFixture = !connected || companies.some(c => c.data_mode === 'synthetic' || c.data_mode === 'demo');

  async function review(action: string) {
    if (!selected || busy) return;
    if (action !== 'confirm' && !feedback.trim()) { setNotice('请填写复核说明，以便将问题回流到评测集。'); return; }
    setBusy(true);
    try {
      if (connected) await request(`/api/v1/alerts/${encodeURIComponent(selected.id)}/feedback`, { method: 'POST', body: JSON.stringify({ action, comment: feedback, reason: feedback, modification: action === 'modify' ? { comment: feedback } : null, error_type: action === 'confirm' ? null : errorType, idempotency_key: `${selected.id}-${action}-${Date.now()}` }) });
      const status = action === 'confirm' ? 'confirmed' : action === 'reject' ? 'rejected' : 'modified';
      setAlerts(rows => rows.map(row => row.id === selected.id ? { ...row, status } : row));
      setNotice(connected ? '复核已保存，反馈已回流。' : '已在当前演示会话记录复核；未写入服务器。'); setFeedback('');
    } catch (error) { setNotice(`保存失败：${error instanceof Error ? error.message : '网络错误'}。复核状态未改变。`); }
    finally { setBusy(false); }
  }

  async function startAnalysis() {
    if (busy || !analysisCompany || !question.trim()) return;
    setBusy(true); setRun(null);
    try {
      if (!connected) { setNotice('当前为离线演示，未执行模型分析。请启动后端后刷新。'); return; }
      const result = await request('/api/v1/analysis/runs', { method: 'POST', body: JSON.stringify({ company_id: analysisCompany, question, period: '2025', mode: 'workflow' }) });
      setRun(result); setNotice('分析运行已完成，可查看证据与节点记录。');
    } catch (error) { setNotice(`分析失败：${error instanceof Error ? error.message : '网络错误'}`); }
    finally { setBusy(false); }
  }

  async function ingest() {
    if (!connected) { setNotice('当前为离线演示，未创建采集任务。'); return; }
    setBusy(true);
    try { const result = await request('/api/v1/admin/ingestion/jobs', { method: 'POST', body: JSON.stringify({ company_ids: companies.map(c => c.id), source: 'demo' }) }); setNotice(`采集任务已创建：${result.id ?? result.job_id ?? result.status ?? '已接受'}`); }
    catch (error) { setNotice(`创建失败：${error instanceof Error ? error.message : '网络错误'}`); }
    finally { setBusy(false); }
  }

  async function chooseAlert(row: Row) { setSelectedId(row.id); setTab('evidence'); setFeedback(''); if (connected) { try { const value = await request(`/api/v1/alerts/${encodeURIComponent(row.id)}/feedback`); setFeedbackHistory(normalizeCollection(value)); } catch { setFeedbackHistory([]); } } }

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); setView('overview'); }}><span className="brand-mark">F<span /></span><span>FinSentinel<small>金融证据链研判平台</small></span></a>
      <div className="workspace"><span className="workspace-icon">研</span><span>消费电子研究组<small>RESEARCH WORKSPACE</small></span><span className="chevron">⌄</span></div>
      <div className="nav-caption">工作台</div>
      <nav>{nav.map(n => <button key={n.id} className={`nav-item ${view === n.id ? 'active' : ''}`} onClick={() => { setView(n.id as View); setNotice(''); }}><span className="nav-icon">{n.icon}</span>{n.label}{n.id === 'review' && pending > 0 && <span className="nav-count">{pending}</span>}</button>)}<Link className="nav-item" href="/compare"><span className="nav-icon">⇄</span>证据比较 · 真实财报</Link></nav>
      <div className="sidebar-bottom"><div className="health"><i />工作流引擎<span>{connected ? '已连接' : '演示'}</span></div><div className="profile"><span className="avatar">研</span><span>研究员<small>个人研究工作区</small></span><span>⌘</span></div></div>
    </aside>

    <main className="main">
      <header className="topbar"><div className="breadcrumb">研究工作台 <span>/</span> <strong>{nav.find(n => n.id === view)?.label}</strong></div><div className="topbar-right"><span className="live-dot" />日级监测<span className="vertical-rule" /><span>消费电子 / 电子制造</span><button className="icon-button" onClick={() => setNotice('告警通知集中显示在风险告警与人工复核页面。')} aria-label="通知">♧</button><span className="avatar small">研</span></div></header>
      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">EVIDENCE-DRIVEN RESEARCH</div><h1>{view === 'overview' ? '行业风险监控总览' : nav.find(n => n.id === view)?.label}</h1><p>{view === 'overview' ? '从财务变化到公告事件，让每一条研判都有据可循。' : '查看来源、计算过程与复核记录，形成可追溯的研究闭环。'}</p></div><button className="primary-button" onClick={() => { setAnalysisOpen(true); setRun(null); }}>＋ 新建分析</button></div>
        <div className={`mode-banner ${connected ? 'connected' : ''} ${isFixture ? 'synthetic-banner' : ''}`}><span>{loading ? '◌ ' : connected ? '● ' : '◈ '}{connectionStatusLabel({ loading, connected, error: loadError })}</span><strong>{isFixture ? 'DEMO / 合成数据' : '真实公开材料'}</strong><span>{loadError ? `连接失败：${loadError}。` : isFixture ? '页面中的公司、数字、页码和证据均为合成样例，不能作为真实财报结论。' : '公开材料研究辅助 · 结论需人工复核'}</span><button className="banner-action" onClick={() => loadDashboard({ refresh: true })} disabled={loading || refreshing}>{refreshLabel(refreshing)}</button><span className="banner-end">{connected ? 'API ONLINE' : 'FIXTURE DATA'}</span></div>
        {loadError && !loading && <div className="notice error" role="alert">数据服务暂时不可用，当前展示离线演示数据。<button onClick={() => loadDashboard({ refresh: true })} disabled={refreshing}>{refreshLabel(refreshing)}</button></div>}
        {notice && <div className="notice" role="status">{notice}<button aria-label="关闭提示" onClick={() => setNotice('')}>×</button></div>}

        {view === 'overview' && <>
          <section className="stats-grid">
            {[{ title: '监测公司', value: companies.length, unit: '家', foot: '消费电子 / 电子制造', trend: false }, { title: '待人工复核', value: pending, unit: '条', foot: '证据完整后进入复核队列', trend: true }, { title: '高风险告警', value: high, unit: '条', foot: '优先核实现金流与经营异常', trend: false }, { title: '证据定位', value: alerts.reduce((n, a) => n + a.evidence.length, 0), unit: '处', foot: '来源页码与段落可追溯', trend: true }].map((s, i) => <article className="stat-card" key={s.title}><div className="stat-title">{s.title}<span>{['▦', '◷', '◇', '▤'][i]}</span></div><div className="stat-value">{s.value}<span>{s.unit}</span></div><div className="stat-foot"><span>{s.foot}</span><span className={`tiny-line ${s.trend ? 'green' : ''}`} /></div></article>)}
          </section>
          <div className="overview-grid"><section className="panel risk-summary"><div className="panel-heading"><div><h2>风险分布 <span>RISK DISTRIBUTION</span></h2><p>按待跟踪事项类型划分 · 与当前告警列表同步</p></div><span className="subtle-chip">{alerts.length} 条告警</span></div><div className="risk-bars">{[{ label: '营运与现金流质量', color: 'var(--accent)' }, { label: '业绩与盈利能力', color: 'var(--accent-bright)' }, { label: '重大公告事件', color: 'var(--warning)' }].map(r => { const count = alerts.filter(a => riskCategory(a) === r.label).length; return <div className="risk-bar-row" key={r.label}><div><span>{r.label}</span><strong>{count}<small> 条</small></strong></div><div className="bar-track"><span style={{ width: `${Math.max(count ? 4 : 0, count / Math.max(alerts.length, 1) * 100)}%`, background: r.color }} /></div></div>})}</div><div className="risk-note"><span>ⓘ</span>统计直接来自当前告警；规则触发是研究线索，风险等级需结合原文与人工判断。</div></section><section className="panel pipeline-panel"><div className="panel-heading"><div><h2>证据链工作流 <span>WORKFLOW</span></h2><p>六个阶段与运行记录一一对应</p></div><span className="status-text"><i />{run ? `最近运行：${run.status ?? 'completed'}` : '等待运行'}</span></div><div className="pipeline">{workflowStages.map((stage, i) => <div className="pipeline-node" key={stage.id}><span>{i + 1}</span><strong>{stage.label}</strong><small>{run?.agent_steps?.find((s: Row) => (s.node ?? s.name) === stage.id)?.status ?? '未运行'}</small>{i !== workflowStages.length - 1 && <i />}</div>)}</div><div className="pipeline-bottom"><div><span className="pill-square">ƒ</span><span>确定性工具计算<small>数值、单位、期间统一校验</small></span></div><div><span className="pill-square">✓</span><span>人工复核闭环<small>确认 / 驳回 / 修订 → 回归集</small></span></div></div></section></div>
        </>}

        {['overview', 'alerts', 'review'].includes(view) && <div className="research-grid"><section className="panel alerts-panel"><div className="panel-heading"><div><h2>{view === 'review' ? '人工复核队列' : '最新风险告警'} <span>ALERTS</span></h2><p>选中事项，检查公式与原始证据</p></div><span className="count-chip">{filtered.length} 条</span></div><div className="filters"><label className="search"><span>⌕</span><input aria-label="搜索公司或告警" placeholder="搜索公司或风险关键词" value={query} onChange={e => setQuery(e.target.value)} /></label><select aria-label="风险等级" value={severity} onChange={e => setSeverity(e.target.value)}><option value="all">全部等级</option><option value="high">高风险</option><option value="medium">中风险</option><option value="low">低风险</option></select><select aria-label="公司筛选" value={company} onChange={e => setCompany(e.target.value)}><option value="all">全部公司</option>{Array.from(new Set(alerts.map(a => String(a.company_name)))).map(c => <option key={c}>{c}</option>)}</select></div><div className="table-head"><span>风险事项 / 公司</span><span>风险等级</span><span>复核状态</span></div><div className="alert-list">{filtered.length ? filtered.map(a => <button className={`alert-row ${selected?.id === a.id ? 'selected' : ''}`} key={a.id} onClick={() => chooseAlert(a)}><div className="alert-row-main"><span className={`risk-dot ${a.severity}`} /><div><strong>{a.title}</strong><div className="row-meta"><span>{a.company_name}</span><span>{a.period}</span><span>{a.category}</span></div></div></div><Badge severity={a.severity} /><span className={`review-status ${a.status}`}>{statusLabel[a.status] ?? a.status}</span></button>) : <div className="empty">{alertEmptyLabel({ total: alerts.length, filtered: filtered.length, review: view === 'review' })}</div>}</div><div className="table-footer"><span>共 {filtered.length} 条事项 · {pending} 条待复核</span><button onClick={() => { setSeverity('all'); setCompany('all'); setQuery(''); }}>重置筛选 ↗</button></div></section>
        <section className="panel detail-panel">{selected ? <><div className="detail-heading"><div className="detail-eyebrow">研判详情 <span>{selected.id}</span></div><h2>{selected.title}</h2><div className="detail-meta"><Badge severity={selected.severity} /><span>{selected.company_name}</span><span>{selected.period}</span></div><p>{selected.summary}</p></div><div className="detail-tabs" role="tablist">{[{ id: 'evidence', label: '原始证据', count: selected.evidence.length }, { id: 'metrics', label: '指标与公式' }, { id: 'trace', label: '执行轨迹' }, { id: 'review', label: '人工复核' }].map(t => <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'active' : ''} onClick={() => setTab(t.id)}>{t.label}{t.count !== undefined && <small>{t.count}</small>}</button>)}</div><div className="detail-body">{tab === 'evidence' && <>{selected.evidence.length ? selected.evidence.map((e: Row, i: number) => <article className="evidence-card" key={e.id ?? i}><div className="evidence-top"><span className="doc-icon">▤</span><div><strong>{e.title ?? `来源文件 ${e.filing_id ?? i + 1}`}</strong><small>{isFixture ? `示例页号 ${e.page ?? '—'} · 示例段落 ${e.paragraph ?? '—'}` : `第 ${e.page ?? '—'} 页 · 第 ${e.paragraph ?? '—'} 段`}</small></div><span className="source-index">[{i + 1}]</span></div><blockquote>{e.text}</blockquote><div className="evidence-bottom"><span>{evidenceStatusLabel(e)}</span>{e.source_url && /^https?:\/\//.test(e.source_url) ? <a href={e.source_url} target="_blank" rel="noreferrer">查看原文 ↗</a> : <span>合成测试证据</span>}</div></article>) : <div className="empty">暂无可核验引用，结论需补充证据。</div>}<div className="confidence-note">ⓘ 引用支持研究结论；财务判断需结合完整报告上下文。</div></>}{tab === 'metrics' && <>{selected.metrics.length ? selected.metrics.map((m: Row, i: number) => <div className="metric-detail" key={i}><span>{m.name ?? m.metric}</span><strong>{formatMetric(m.value, m.unit)}</strong><code>{m.formula ?? selected.calculation ?? '见工具调用记录'}</code>{m.inputs && <small>{m.inputs}</small>}{m.threshold && <small>{m.threshold}</small>}</div>) : <div className="empty">该事项为公告事件，暂无结构化计算结果。</div>}</>}{tab === 'trace' && <>{selected.agent_steps.length ? <div className="trace-list">{selected.agent_steps.map((s: Row, i: number) => <div className="trace-step" key={i}><span>✓</span><div><strong>{s.name ?? s.node}</strong><p>{s.detail ?? s.status}</p></div><code>{Number(s.duration_ms ?? 0).toFixed(1)} ms</code></div>)}</div> : <div className="empty">此告警暂无运行轨迹。新建分析后可查看完整节点记录。</div>}</>}{tab === 'review' && <div className="review-form"><label>错误分类<select value={errorType} onChange={e => setErrorType(e.target.value)}><option value="citation_error">引用不支持结论</option><option value="data_error">数据错误</option><option value="calculation_error">计算错误</option><option value="period_error">时间范围错误</option><option value="overstatement">结论夸大</option><option value="other">其他</option></select></label><label>复核说明<textarea rows={4} placeholder="记录你的判断、修订意见或缺失的证据…" value={feedback} onChange={e => setFeedback(e.target.value)} /></label><p>驳回或修订必须填写说明。反馈用于错误归因与回归评测。</p><div className="review-history"><h3>反馈历史</h3>{feedbackHistory.length ? feedbackHistory.map((item: Row) => <div className="review-history-item" key={item.id}><strong>{item.action}</strong><span>{item.reason ?? item.comment ?? '无说明'}</span><small>{item.created_at}</small></div>) : <p>暂无已保存反馈。</p>}<p>待审核回归候选：{reviewCandidates.filter((c: Row) => c.alert_id === selected.id).length} 条</p></div><div className="review-actions"><button disabled={busy} className="primary-button" onClick={() => review('confirm')}>确认告警</button><button disabled={busy} className="secondary-button" onClick={() => review('modify')}>提交修订</button><button disabled={busy} className="danger-button" onClick={() => review('reject')}>驳回</button></div></div>}</div><div className="detail-footer"><span className="live-dot" />{statusLabel[selected.status] ?? selected.status}<button onClick={() => setTab('review')}>进入人工复核 →</button></div></> : <div className="empty">暂无告警。先创建分析任务。</div>}</section></div>}

        {view === 'companies' && <section className="panel"><div className="panel-heading"><div><h2>公司研究池</h2><p>选择公司查看结构化财务指标与来源</p></div><Badge>消费电子 / 电子制造</Badge></div><div className="company-grid">{companies.map(c => <button key={c.id} className={`company-card ${selectedCompany === c.id ? 'selected' : ''}`} onClick={() => setSelectedCompany(c.id)}><span className="company-logo">{c.name?.slice(0, 1)}</span><h3>{c.name}</h3><small>{c.code ?? c.ticker ?? c.id} · {c.industry ?? c.sector}</small><span>{selectedCompany === c.id ? '正在查看 →' : '查看财务指标 →'}</span></button>)}</div><div className="company-metrics"><h3>报告期指标 <small>{connected ? '数据库记录' : '合成样例'}</small></h3>{connected ? <div className="metric-grid">{metricsLoading ? <div className="empty">{metricStateLabel({ loading: true })}</div> : metricsError ? <div className="empty">{metricStateLabel({ error: metricsError })}<button onClick={() => setMetricsRetry(value => value + 1)}>重试</button></div> : companyMetrics.length ? companyMetrics.map((m, i) => <div className="metric-detail" key={i}><span>{m.metric ?? m.name}</span><strong>{formatMetric(m.value, m.unit)}</strong><small>{m.period} · 来源 {m.source_id ?? m.evidence_id ?? '查看记录'}</small></div>) : <div className="empty">{metricStateLabel({ hasData: false })}</div>}</div> : <div className="metric-grid">{[{ name: '营业收入', value: companies.find(c => c.id === selectedCompany)?.revenue, unit: '亿元' }, { name: '综合毛利率', value: companies.find(c => c.id === selectedCompany)?.margin, unit: '%' }, { name: '现金利润比', value: companies.find(c => c.id === selectedCompany)?.cash_ratio, unit: '倍' }].map(m => <div className="metric-detail" key={m.name}><span>{m.name}</span><strong>{formatMetric(m.value, m.unit)}</strong><Sparkline values={fixtureTrend} accent /><small>2025FY · 合成样例</small></div>)}</div>}</div></section>}

        {view === 'evals' && <><section className="panel"><div className="panel-heading"><div><h2>质量评测与回归</h2><p>只有实际运行结果才记录为已达成；目标值用于验收比较。</p></div><span className="subtle-chip">PROMPT / MODEL / RETRIEVAL</span></div><div className="eval-table"><div className="eval-row heading"><span>评测指标</span><span>验收目标</span><span>实测值</span><span>状态</span></div>{[{ label: '确定性财务计算正确率', target: '≥ 98%', key: 'numeric_accuracy' }, { label: '引用覆盖率', target: '≥ 95%', key: 'citation_coverage' }, { label: '黄金证据 Recall@5', target: '≥ 90%', key: 'recall_at_5' }, { label: '工具调用成功率', target: '≥ 98%', key: 'tool_success_rate' }, { label: '未缓存证据分析 p95', target: '≤ 12 秒', key: 'p95_latency_ms' }, { label: '失败重试后恢复率', target: '≥ 95%', key: 'recovery_rate' }].map(m => { const val = evalSummary?.metrics?.[m.key] ?? evalSummary?.[m.key]; return <div className="eval-row" key={m.key}><strong>{m.label}</strong><span>{m.target}</span><code>{val === undefined || val === null ? 'N/A' : typeof val === 'number' ? val.toFixed(3) : String(val)}</code><Badge>{val === undefined || val === null ? '待运行' : '已有记录'}</Badge></div>; })}</div></section><div className="two-column"><section className="panel padded"><h2>对照实验</h2><p>使用同一批黄金问题、相同数据快照与相同模型，比较基线和多 Agent 工作流。</p><div className="experiment"><span>A</span><div><strong>单 Agent RAG baseline</strong><small>检索 → 生成</small></div><Badge>待评测</Badge></div><div className="experiment"><span>B</span><div><strong>多 Agent evidence workflow</strong><small>规划 → 检索 + 计算 → 复核 → 报告</small></div><Badge>待评测</Badge></div></section><section className="panel padded"><h2>反馈回流</h2><p>人工反馈经过错误归因后进入回归样本库，版本变更需重新评测。</p><div className="feedback-flow">人工复核 <span>→</span> 错误分类 <span>→</span> 回归样本 <span>→</span> 版本对比</div><div className="info-box">尚未加载完整 benchmark 结果。不得将验收目标或合成测试结果作为真实业务表现。</div></section></div></>}

        {view === 'data' && <section className="panel"><div className="panel-heading"><div><h2>数据管道与质量</h2><p>公开材料采集、文档解析、指标入库与证据定位</p></div><button disabled={busy} className="secondary-button" onClick={ingest}>＋ 创建采集任务</button></div><div className="data-stages">{['材料采集', '文档解析', '指标标准化', '质量校验', '检索索引'].map((stage, i) => <div key={stage}><span>{String(i + 1).padStart(2, '0')}</span><h3>{stage}</h3><p>{['保留来源 URL 与快照版本', '页码、段落与表格位置', '统一期间、单位与口径', '缺失、重复和异常检测', '全文与向量索引'][i]}</p></div>)}</div><div className="quality-list">{['来源可追溯', '期间与单位校验', '重复文档检查', '缺失指标检查'].map(item => <div key={item}><span>{item}</span><Badge>{dataStatus ? '见服务端质量记录' : '待真实材料验收'}</Badge></div>)}</div><div className="info-box">{isFixture ? '当前为合成数据快照，用于验证功能与接口。尚未完成 50–100 份真实公开财报/公告的采集验收。' : '数据质量结果以服务端任务与检查记录为准。'}</div></section>}
        <footer className="page-footer"><span>FinSentinel / Evidence before conclusions.</span><span>公开材料研究辅助 · 非投资建议</span></footer>
      </div>
    </main>

    {analysisOpen && <div className="modal-backdrop" onClick={() => !busy && setAnalysisOpen(false)}><section className="modal" role="dialog" aria-modal="true" aria-label="新建分析" onClick={e => e.stopPropagation()}><div className="panel-heading"><div><h2>新建证据分析</h2><p>运行规划、检索、计算与证据复核工作流</p></div><button className="icon-button" aria-label="关闭" onClick={() => setAnalysisOpen(false)}>×</button></div><div className="modal-body"><label>分析公司<select value={analysisCompany} onChange={e => setAnalysisCompany(e.target.value)}>{companies.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>分析问题<textarea rows={4} value={question} onChange={e => setQuestion(e.target.value)} /></label><div className="info-box">报告期：2025 · 所有计算通过白名单工具执行 · 结果需人工复核</div>{run && <div className="run-result"><Badge>{run.status}</Badge><h3>运行 {run.id ?? run.run_id}</h3><p>{run.summary}</p>{(run.agent_steps ?? []).map((s: Row, i: number) => <div className="run-step" key={i}><span>✓ {s.node ?? s.name}</span><code>{Number(s.duration_ms ?? 0).toFixed(1)} ms</code></div>)}{run.evidence?.map((e: Row, i: number) => <blockquote key={i}>{e.text}<small>{isFixture ? `示例页号 ${e.page}` : `第 ${e.page} 页`}</small></blockquote>)}</div>}</div><div className="modal-footer"><span>{connected ? '已连接 API' : '离线演示 · 不会伪造分析结果'}</span><button disabled={busy || !question.trim() || !analysisCompany} className="primary-button" onClick={startAnalysis}>{busy ? '分析运行中…' : '运行分析 →'}</button></div></section></div>}
  </div>;
}






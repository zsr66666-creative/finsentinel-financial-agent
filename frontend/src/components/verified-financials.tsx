'use client';
import { ReaderLink } from '@/components/reader-link';
import { authFetch } from '@/lib/accounts.mjs';
import { FinancialReviewPanel } from '@/components/financial-review-panel';
import { useEffect, useState } from 'react';
import { formatFinancialNumber, parseFinancialComparison, type FinancialComparison } from '@/lib/verified-financials.mjs';

const reasonText: Record<string, string> = {
  unsupported_company_period_or_scope: '当前仅支持三七互娱、科大讯飞 2024 年合并口径，请选择已覆盖范围。',
  official_artifact_unavailable: '官方报告尚未就绪或文档身份不匹配，暂不展示金额。',
  source_pdf_unavailable: '报告原件暂不可读取，暂不展示金额，请稍后重试。',
  source_pdf_hash_mismatch: '报告原件校验未通过，暂不展示金额，请联系维护人员核查。',
  source_pdf_contract_mismatch: '报告结构与来源契约不符，暂不展示金额。',
  source_contract_mismatch: '金额、报表口径或期间证据不完整，需进一步核对原文。',
};
const roleText: Record<string, string> = { row: '金额原文', statement: '报表口径', unit: '金额单位', columns: '比较列', balance_date: '报表日期' };
export function VerifiedFinancials({ companyCode }: { companyCode: string }) {
  const [scope, setScope] = useState('consolidated');
  const [retry, setRetry] = useState(0);
  const [result, setResult] = useState<FinancialComparison | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const period = '2024FY';
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    const timer = setTimeout(() => controller.abort(), 15000);
    setLoading(true); setError(''); setResult(null);
    void (async () => {
      try {
        const query = new URLSearchParams({ period, statement_scope: scope });
        const response = await authFetch(`/api/v1/companies/${encodeURIComponent(companyCode)}/financial-comparison?${query}`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(`财务来源服务返回 ${response.status}，请重试。`);
        const parsed = parseFinancialComparison(await response.json(), companyCode, period, scope);
        if (active) setResult(parsed);
      } catch (e) {
        if (active) setError(e instanceof Error && e.name === 'AbortError' ? '核对请求超时，请重试。' : e instanceof Error ? e.message : '财务核对加载失败，请重试。');
      } finally { clearTimeout(timer); if (active) setLoading(false); }
    })();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [companyCode, scope, retry]);
  const shown = result?.company_code === companyCode && result?.statement_scope === scope ? result : null;
  return <section className="panel comparison-card verified-financials" aria-labelledby="financial-check-title" aria-busy={loading}>
    <div className="panel-heading"><div><h2 id="financial-check-title">真实财务核对</h2><p>同一公司、同一报表口径，比较金额与来源一起呈现。</p></div><span className="financial-review-tag">来源与人工复核分开</span></div>
    <div className="evidence-scope-controls"><label>报告期<select aria-label="财务核对报告期" value={period} disabled><option value="2024FY">2024 年年度报告</option></select></label><label>报表口径<select aria-label="财务核对报表口径" value={scope} onChange={e => { setResult(null); setScope(e.target.value); }}><option value="consolidated">合并口径 · 已覆盖</option><option value="parent">母公司口径 · 待覆盖</option></select></label></div>
    <p className="evidence-coverage">金额单位：人民币元。来源校验通过表示金额与指定原文一致，不自动等于人工复核，详见下方记录；增加或减少本身不等于风险结论。</p>
    {loading && <p role="status">正在核对官方报告原件、报表口径与期间…</p>}
    {error && <div className="notice error" role="alert">{error}<button className="secondary-button" onClick={() => setRetry(v => v + 1)}>重新核对</button></div>}
    {!loading && !error && shown && <>
      {shown.reason && <p className="review-callout" role="status">待复核：{reasonText[shown.reason] ?? '证据尚未完整，暂不展示金额。'}</p>}
      <div className="financial-check-grid">{shown.items.map(row => <article className="financial-check-item" key={row.metric}>
        <div className="financial-check-heading"><h3>{row.label}</h3><span>{row.status === 'supported' ? '来源校验通过' : '待复核'}</span></div>
        {row.status === 'needs_review' ? <p className="review-callout">{reasonText[row.reason ?? ''] ?? '证据不完整，暂不展示金额。'}</p> : <>
          <dl className="financial-amounts"><div><dt>本期 · {row.current_column}</dt><dd>{formatFinancialNumber(row.current_value)}</dd></div><div><dt>比较期 · {row.previous_column}</dt><dd>{formatFinancialNumber(row.previous_value)}</dd></div></dl>
          <div className="financial-change"><span>{row.direction === 'increase' ? '增加' : row.direction === 'decrease' ? '减少' : '持平'} · 差额 <strong>{formatFinancialNumber(row.difference)}</strong> 元</span><span>变化率 <strong>{row.change_percent === null ? '不适用（比较基数为零）' : `${row.change_percent}%`}</strong></span></div>
          <p className="evidence-coverage">{row.period_kind === 'flow' ? '全年发生额对比' : '期末与期初余额对比'} · 合并口径<br />原始期间：{row.current_period} ／ {row.previous_period === 'opening_balance_2024' ? '2024 年报期初余额（原表未单列日期）' : row.previous_period}</p>
          <details><summary>查看原文与来源定位</summary><p>来源：2024 年官方年度报告 · 物理页码（从 PDF 第 1 页起计）</p>{row.evidence.map(proof => <div className="financial-proof" key={proof.evidence_id}><strong>{roleText[proof.role] ?? proof.role} · 第 {proof.page} 页</strong><pre>{proof.text}</pre><ReaderLink locator={{company_code:companyCode,period,document_sha256:row.source_sha256,page:proof.page}}/><a href={`${row.source_url}#page=${proof.page}`} target="_blank" rel="noreferrer">打开官方 PDF 第 {proof.page} 页 ↗</a></div>)}<p>文档 SHA-256：<code>{row.source_sha256}</code></p><p>变化率计算：(本期 − 比较期) ÷ |比较期| × 100%，四舍五入至两位小数。</p></details>
        </>}
      </article>)}</div>
      {['002555','002230'].includes(companyCode) && scope === 'consolidated' && <FinancialReviewPanel key={`${companyCode}-${scope}`} comparison={shown} onSourceRefresh={()=>setRetry(v=>v+1)}/> }
      {!shown.items.length && !shown.reason && <p className="empty">该研究范围暂无可核对的财务指标。</p>}
    </>}
  </section>;
}

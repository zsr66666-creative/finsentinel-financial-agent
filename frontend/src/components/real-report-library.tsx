'use client';

import Link from 'next/link';
import { groupScopedCompanies } from '@/lib/evidence-scopes.mjs';
import { useResearchCatalog } from '@/components/research-catalog';

export function RealReportLibrary() {
  const {items,loading,error,refresh} = useResearchCatalog();
  const companies = groupScopedCompanies(items);
  return <section className="panel real-report-library" aria-labelledby="real-library-title" aria-busy={loading}>
    <div className="panel-heading"><div><h2 id="real-library-title">真实报告研究库 <span>REAL REPORTS</span></h2><p>来自实际索引的报告原文；与演示监控指标分开标注。当前为选页 / 片段覆盖。</p></div><span className="count-chip">{companies.length} 家已索引</span></div>
    {loading && <p className="empty" role="status">正在核对可检索报告…</p>}
    {error && <div className="notice error" role="alert">{error}<button type="button" onClick={() => refresh()}>重新加载</button></div>}
    {!loading && !error && !companies.length && <p className="empty">尚无已索引报告；计划中的企业不会作为现有数据展示。</p>}
    <div className="company-grid">{companies.map(company => <Link key={company.company_code} className="company-card" href={`/companies/${encodeURIComponent(company.company_code)}`}>
      <span className="company-logo">{company.company_name.slice(0, 1)}</span><h3>{company.company_name}</h3>
      <small>{company.company_code} · {company.industry}</small><small>{company.periods.join(' / ')} · {company.chunk_count} 个原文片段</small><span>进入公司研究 →</span>
    </Link>)}</div>
  </section>;
}

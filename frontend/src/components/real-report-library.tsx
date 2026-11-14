'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { groupScopedCompanies, parseScopes, type EvidenceScope } from '@/lib/evidence-scopes.mjs';

export function RealReportLibrary() {
  const [items, setItems] = useState<EvidenceScope[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timer = setTimeout(() => controller.abort(), 12000);
    setLoading(true); setError('');
    void (async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? ''}/api/v1/evidence/scopes`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error(`真实报告目录暂不可用（${response.status}）。`);
        const scopes = parseScopes(await response.json());
        if (active) setItems(scopes);
      } catch (e) {
        if (active) { setItems([]); setError(e instanceof Error && e.name === 'AbortError' ? '真实报告目录加载超时。' : e instanceof Error ? e.message : '真实报告目录加载失败。'); }
      } finally { clearTimeout(timer); if (active) setLoading(false); }
    })();
    return () => { active = false; clearTimeout(timer); controller.abort(); };
  }, [retry]);
  const companies = groupScopedCompanies(items);
  return <section className="panel real-report-library" aria-labelledby="real-library-title" aria-busy={loading}>
    <div className="panel-heading"><div><h2 id="real-library-title">真实报告研究库 <span>REAL REPORTS</span></h2><p>来自实际索引的报告原文；与演示监控指标分开标注。当前为选页 / 片段覆盖。</p></div><span className="count-chip">{companies.length} 家已索引</span></div>
    {loading && <p className="empty" role="status">正在核对可检索报告…</p>}
    {error && <div className="notice error" role="alert">{error}<button type="button" onClick={() => setRetry(value => value + 1)}>重新加载</button></div>}
    {!loading && !error && !companies.length && <p className="empty">尚无已索引报告；计划中的企业不会作为现有数据展示。</p>}
    <div className="company-grid">{companies.map(company => <Link key={company.company_code} className="company-card" href={`/companies/${encodeURIComponent(company.company_code)}`}>
      <span className="company-logo">{company.company_name.slice(0, 1)}</span><h3>{company.company_name}</h3>
      <small>{company.company_code} · {company.industry}</small><small>{company.periods.join(' / ')} · {company.chunk_count} 个原文片段</small><span>进入公司研究 →</span>
    </Link>)}</div>
  </section>;
}

'use client';
import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { PortalShell } from '@/components/portal-shell';
import { EvidenceSearch } from '@/components/evidence-search';
import { CatalogStatus, useResearchCatalog } from '@/components/research-catalog';
import { SourceRail } from '@/components/research-portal';
import { evidenceContext } from '@/lib/portal.mjs';
function EvidencePage(){const params=useSearchParams();const catalog=useResearchCatalog();const company=params.get('company');const period=params.get('period');const requested=company!==null||period!==null;const context=evidenceContext(catalog.items,company,period);return <PortalShell title="原文检索"><div className="content portal-content"><section className="portal-page-title"><span className="portal-kicker">SOURCE EXPLORER</span><h1>原文检索</h1><p>在实际已索引的公司与报告期内，查找可追溯的候选证据。</p></section><div className="portal-columns"><div>{requested&&!context?<><CatalogStatus/>{!catalog.loading&&!catalog.error&&catalog.items.length>0&&<p className="portal-state error" role="alert">链接中的公司或报告期不在当前索引范围内。请从报告库重新选择；未切换至其他范围。</p>}</>:<EvidenceSearch key={`${company}-${period}`} companyCode={context?.companyCode} initialPeriod={context?.period}/>}</div><SourceRail/></div></div></PortalShell>;}
export default function Page(){return <Suspense fallback={<p role="status">正在打开原文检索…</p>}><EvidencePage/></Suspense>;}

'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ProfileLink } from '@/components/demo-session';
import { useResearchCatalog } from '@/components/research-catalog';
import { PortalIcon } from '@/components/portal-icon';
import { catalogCompanies, chooseCompany, filterCompanies } from '@/lib/portal.mjs';
const groups=[
 {label:'研究',items:[['/','home','研究首页'],['/companies','companies','公司研究'],['/reports','reports','报告库'],['/evidence','search','原文检索'],['/compare','compare','证据比较']]},
 {label:'演示工作台',items:[['/workbench','dashboard','监控总览'],['/workbench/alerts','alerts','风险告警'],['/workbench/review','review','告警复核'],['/workbench/evals','evals','评测与版本'],['/workbench/data','data','数据质量'],['/workbench/companies','companies','演示公司库']]},
 {label:'个人',items:[['/my-research','reports','我的研究'],['/settings','settings','个人设置']]},
];
function SidebarContent({close}:{close?:()=>void}){
 const pathname=usePathname();return <>
  <Link href="/" className="brand portal-brand" onClick={close}><span className="portal-brand-mark">f<span>.</span></span><span>FinSentinel<small>金融证据研究</small></span></Link>
  <Link className="portal-new" href="/evidence" onClick={close}><span>＋</span> 开始研究</Link>
  <nav aria-label="功能导航">{groups.map(g=><div className="portal-nav-group" key={g.label}><div className="nav-caption">{g.label}</div>{g.items.map(([href,icon,label])=>{const active=pathname===href||(href==='/companies'&&pathname.startsWith('/companies/'));return <Link key={href} href={href} onClick={close} className={`nav-item ${active?'active':''}`} aria-current={active?'page':undefined}><PortalIcon name={icon}/><span>{label}</span></Link>;})}</div>)}</nav>
  <div className="sidebar-bottom"><p className="portal-sidebar-note">公开材料 · 来源可追溯<br/>研究辅助，不构成投资建议</p><ProfileLink/></div>
 </>;
}
export function PortalShell({children,title}:{children:React.ReactNode;title:string}){
 const pathname=usePathname();const router=useRouter();const dialog=useRef<HTMLDialogElement>(null);const menu=useRef<HTMLButtonElement>(null);
 const {items,loading,error}=useResearchCatalog();const companies=catalogCompanies(items);
 const [query,setQuery]=useState('');const [open,setOpen]=useState(false);
 const matches=query.trim()?filterCompanies(companies,'all',query).slice(0,6):[];
 useEffect(()=>{dialog.current?.close();setOpen(false);setQuery('');},[pathname]);
 function close(){dialog.current?.close();}
 return <div className="shell portal-shell">
  <a className="portal-skip" href="#portal-main">跳到主要内容</a>
  <aside className="sidebar portal-sidebar"><SidebarContent/></aside>
  <dialog className="portal-nav-dialog" ref={dialog} aria-label="功能导航菜单" onClick={e=>{if(e.target===e.currentTarget)close();}} onClose={()=>menu.current?.focus()}><button type="button" className="portal-menu-close" aria-label="关闭导航" onClick={close}><PortalIcon name="close"/></button><SidebarContent close={close}/></dialog>
  <main className="main portal-main" id="portal-main" tabIndex={-1}><header className="topbar portal-topbar">
    <button type="button" className="portal-menu-button" ref={menu} aria-label="打开导航" onClick={()=>dialog.current?.showModal()}><PortalIcon name="menu"/></button>
    <form className="portal-global-search" role="search" onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget))setOpen(false);}} onSubmit={e=>{e.preventDefault();if(!query.trim())return;const company=chooseCompany(companies,query);setOpen(false);router.push(company?`/companies/${encodeURIComponent(company.company_code)}`:`/companies?q=${encodeURIComponent(query.trim())}`);}}>
      <PortalIcon name="search"/><input type="search" aria-label="搜索已索引公司名称或代码" placeholder={loading?'正在加载研究范围…':'搜索公司名称或股票代码'} value={query} onFocus={()=>setOpen(true)} onKeyDown={e=>{if(e.key==='Escape')setOpen(false);}} onChange={e=>{setQuery(e.target.value);setOpen(true);}}/>
      <button type="submit" aria-label="搜索公司" disabled={loading||!!error||!query.trim()}>搜索</button>
      {open&&query.trim()&&<div className="portal-search-results">{loading?<p role="status">正在加载目录…</p>:error?<p role="status">目录暂不可用，请在研究首页重试。</p>:matches.length?<><small>实际已索引公司</small>{matches.map(c=><Link key={c.company_code} href={`/companies/${c.company_code}`} onClick={()=>setOpen(false)}><span>{c.company_name}</span><small>{c.company_code} · {c.industry}</small></Link>)}</>:<p role="status">没有匹配的已索引公司。</p>}</div>}
    </form>
    <div className="portal-topbar-right"><span className={`portal-catalog-status ${error?'error':''}`}><i/>{loading?'目录加载中':error?'目录未连接':'研究目录已连接'}</span><ProfileLink compact/></div>
  </header><div className="portal-breadcrumb"><Link href="/">研究首页</Link>{pathname!=='/'&&<><span>/</span><span>{title}</span></>}</div>{children}</main>
 </div>;
}

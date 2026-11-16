'use client';
import { useSession } from '@/components/demo-session';
import { authFetch } from '@/lib/accounts.mjs';
import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { parseScopes, type EvidenceScope } from '@/lib/evidence-scopes.mjs';
type Catalog = {items:EvidenceScope[];loading:boolean;error:string;refresh:()=>void};
const Context=createContext<Catalog|null>(null);
export function ResearchCatalogProvider({children}:{children:React.ReactNode}) {
  const {user}=useSession();
  const enabled=usePathname()!=='/login' && !!user && !user.must_change_password;
  const [items,setItems]=useState<EvidenceScope[]>([]);
  const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [retry,setRetry]=useState(0);
  useEffect(()=>{
    if(!enabled){setLoading(false);return;}
    const controller=new AbortController();let active=true;
    const timeout=setTimeout(()=>controller.abort(),12000);
    setLoading(true);setError('');setItems([]);
    void(async()=>{try{
      const r=await authFetch(`/api/v1/evidence/scopes`,{signal:controller.signal,cache:'no-store'});
      if(!r.ok)throw new Error(`真实报告目录暂不可用（${r.status}）。`);
      const scopes=parseScopes(await r.json());if(active)setItems(scopes);
    }catch(e){if(active)setError(e instanceof Error&&e.name==='AbortError'?'真实报告目录加载超时，请重试。':e instanceof Error?e.message:'真实报告目录加载失败。');}
    finally{clearTimeout(timeout);if(active)setLoading(false);}})();
    return()=>{active=false;controller.abort();clearTimeout(timeout);};
  },[enabled,retry]);
  return <Context.Provider value={{items,loading,error,refresh:()=>setRetry(v=>v+1)}}>{children}</Context.Provider>;
}
export function useResearchCatalog(){const value=useContext(Context);if(!value)throw new Error('ResearchCatalogProvider required');return value;}
export function CatalogStatus(){const {loading,error,items,refresh}=useResearchCatalog();return loading?<p className="portal-state" role="status">正在加载实际已索引的研究范围…</p>:error?<div className="portal-state error" role="alert"><p>{error}</p><button type="button" className="secondary-button" onClick={refresh}>重新加载目录</button></div>:!items.length?<p className="portal-state" role="status">尚无已索引报告。采集完成的材料建立索引后才会出现在这里。</p>:null;}

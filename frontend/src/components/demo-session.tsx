 'use client';
import Link from 'next/link';
import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { safeReturnPath } from '@/lib/demo-profile.mjs';
import { accountRequest, setCsrfToken, secureAccountOrigin } from '@/lib/accounts.mjs';
export type Account = { id:string; username:string; nickname:string; avatar:string|null; role:'viewer'|'reviewer'|'admin'; enabled:boolean; must_change_password:boolean };
type Profile = {nickname:string;avatar:string|null};
type Session = {user:Account|null; profile:Profile; signIn:(username:string,password:string)=>Promise<Account>; signOut:()=>Promise<void>; saveProfile:(profile:Profile)=>Promise<void>; changePassword:(current:string,next:string)=>Promise<void>};
const Context = createContext<Session|null>(null);
export function SessionProvider({children}:{children:React.ReactNode}) {
 const [httpsLink,setHttpsLink]=useState('');
 const [user,setUser]=useState<Account|null>(null);const [ready,setReady]=useState(false);const [error,setError]=useState('');const [retry,setRetry]=useState(0);
 const pathname=usePathname();const router=useRouter();
 useEffect(()=>{let active=true;setReady(false);setError('');
 if(!secureAccountOrigin(window.location)){const url=new URL(window.location.href);url.protocol='https:';url.port='';setHttpsLink(url.href);return;}
 const expired=()=>{setCsrfToken('');setUser(null);setReady(true);};window.addEventListener('finsentinel-session-expired',expired);
 void accountRequest('/session').then(data=>{if(active){setUser(data.user);setCsrfToken(data.csrf_token);}}).catch(cause=>{if(active && cause.status!==401)setError(cause.message);}).finally(()=>{if(active)setReady(true);});
 return()=>{active=false;window.removeEventListener('finsentinel-session-expired',expired);};},[retry]);
 useEffect(()=>{if(ready&&!user&&!error&&pathname!=='/login')router.replace(`/login?next=${encodeURIComponent(safeReturnPath(pathname))}`);if(ready&&user?.must_change_password&&pathname!=='/settings')router.replace('/settings');},[ready,user,error,pathname,router]);
 const session:Session={user,profile:user??{nickname:'研究员',avatar:''},
 async signIn(username,password){const data=await accountRequest('/login',{username,password});setCsrfToken(data.csrf_token);setUser(data.user);setError('');return data.user;},
 async signOut(){await accountRequest('/logout',{});setCsrfToken('');setUser(null);setError('');router.replace('/login');router.refresh();},
 async saveProfile(profile){setUser(await accountRequest('/profile',{...profile,avatar:profile.avatar||null}));},
 async changePassword(current,next){await accountRequest('/password',{current_password:current,new_password:next});setCsrfToken('');setUser(null);setError('');router.replace('/login');router.refresh();}};
 const blocked=!ready||(!user&&pathname!=='/login')||(user?.must_change_password&&pathname!=='/settings');
 return <Context.Provider value={session}>{httpsLink?<main className="session-loading"><h1>请使用 HTTPS 安全连接</h1><p>账号密码仅在安全连接下输入。</p><a className="primary-button" href={httpsLink}>打开 HTTPS 页面</a></main>:blocked?<div className="session-loading" role="status">{error?<><p role="alert">{error}</p><button className="secondary-button" onClick={()=>setRetry(v=>v+1)}>重试</button><Link href="/login">返回登录</Link></>:'正在验证账号会话…'}</div>:children}</Context.Provider>;
}
export function useSession(){const session=useContext(Context);if(!session)throw new Error('Session provider is required');return session;}
export function UserAvatar({profile}:{profile:Profile}){return <span className="avatar user-avatar">{profile.avatar?<img src={profile.avatar} alt=""/>:Array.from(profile.nickname)[0]}</span>;}
export function ProfileLink({compact=false}:{compact?:boolean}){const {profile,user}=useSession();return <Link href="/settings" className={compact?'profile-shortcut':'profile profile-link'} aria-label={`${profile.nickname}，个人设置`}><UserAvatar profile={profile}/>{!compact&&<><span>{profile.nickname}<small>个人设置 · {user?.role==='admin'?'管理员':user?.role==='reviewer'?'复核员':'研究用户'}</small></span><span aria-hidden="true">⚙</span></>}</Link>;}

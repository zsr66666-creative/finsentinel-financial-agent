'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from '@/components/demo-session';
import { safeReturnPath } from '@/lib/demo-profile.mjs';

export default function LoginPage() {
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const [busy,setBusy]=useState(false);
  const { signIn } = useSession();
  const router = useRouter();
  async function submit(event: FormEvent) {
    event.preventDefault(); if(busy)return; setBusy(true);setError('');
    try {const user=await signIn(account.trim(),password);setPassword('');router.replace(user.must_change_password?'/settings':safeReturnPath(new URLSearchParams(window.location.search).get('next')));}
    catch(cause){setError(cause instanceof Error?cause.message:'登录失败，请重试。');}finally{setBusy(false);}
  }
  return <main className="login-screen shell"><section className="login-story"><div className="brand"><span className="brand-mark">F</span><span>FinSentinel<small>金融证据链研判平台</small></span></div><div><span className="login-kicker">你的研究，从证据开始</span><h1>让每一次判断，<br />都有据可循。</h1><p>连接财报、风险与原文证据，建立清晰、可追溯的研究过程。</p><div className="login-capabilities"><span>财报监控</span><span>证据比较</span><span>人工复核</span></div></div><small>公开材料研究辅助 · 非投资建议</small></section><section className="login-form-area"><form className="panel login-card" onSubmit={submit}><span className="subtle-chip">账号登录</span><h2>欢迎回到研究台</h2><p>使用管理员为你创建的账号登录。</p><label htmlFor="demo-account">账号</label><input id="demo-account" autoComplete="username" value={account} maxLength={32} onChange={e => setAccount(e.target.value)} placeholder="输入用户名" required /><label htmlFor="demo-password">密码</label><div className="password-field"><input id="demo-password" type={visible ? 'text' : 'password'} autoComplete="current-password" value={password} maxLength={128} onChange={e => setPassword(e.target.value)} placeholder="输入账号密码" required /><button type="button" aria-label={visible ? '隐藏密码' : '显示密码'} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? '隐藏' : '显示'}</button></div>{error && <p className="error form-message" role="alert">{error}</p>}<button className="primary-button login-submit" type="submit" disabled={busy}>{busy?'正在验证…':'进入研究工作台 →'}</button><p className="login-note">不开放注册。忘记密码请联系管理员重置。</p></form></section></main>;
}

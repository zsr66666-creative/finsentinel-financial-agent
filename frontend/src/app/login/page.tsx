'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useDemoSession } from '@/components/demo-session';
import { demoCredentialsValid, safeReturnPath } from '@/lib/demo-profile.mjs';

export default function LoginPage() {
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false);
  const [error, setError] = useState('');
  const { signIn } = useDemoSession();
  const router = useRouter();
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!demoCredentialsValid(account, password)) { setError('请输入任意非空账号和密码。'); return; }
    try {
      signIn(); setPassword('');
      router.replace(safeReturnPath(new URLSearchParams(window.location.search).get('next')));
    } catch { setError('浏览器存储不可用，请允许此网站使用浏览器存储后重试。'); }
  }
  return <main className="login-screen shell"><section className="login-story"><div className="brand"><span className="brand-mark">F</span><span>FinSentinel<small>金融证据链研判平台</small></span></div><div><span className="login-kicker">你的研究，从证据开始</span><h1>让每一次判断，<br />都有据可循。</h1><p>连接财报、风险与原文证据，建立清晰、可追溯的研究过程。</p><div className="login-capabilities"><span>财报监控</span><span>证据比较</span><span>人工复核</span></div></div><small>公开材料研究辅助 · 非投资建议</small></section><section className="login-form-area"><form className="panel login-card" onSubmit={submit}><span className="subtle-chip">演示登录</span><h2>欢迎回到研究台</h2><p>填写任意非空账号和密码，即可体验工作台。</p><label htmlFor="demo-account">账号</label><input id="demo-account" autoComplete="off" value={account} maxLength={100} onChange={e => setAccount(e.target.value)} placeholder="输入演示账号" required /><label htmlFor="demo-password">密码</label><div className="password-field"><input id="demo-password" type={visible ? 'text' : 'password'} autoComplete="off" value={password} maxLength={100} onChange={e => setPassword(e.target.value)} placeholder="输入任意演示密码" required /><button type="button" aria-label={visible ? '隐藏密码' : '显示密码'} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? '隐藏' : '显示'}</button></div>{error && <p className="error form-message" role="alert">{error}</p>}<button className="primary-button login-submit" type="submit">进入研究工作台 →</button><p className="login-note">这是演示入口，不验证身份，也不提供账户权限隔离。请勿填写真实密码。</p></form></section></main>;
}
